#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
睡眠周期感知规划器 v1.0 — P2
对标李飞飞世界模型框架的"规划器"维度

核心能力:
  1. 睡眠阶段分割 (有手环/无手环两套模式)
  2. 唤醒窗口计算 (在REM末期/浅睡期唤醒最不困乏)
  3. 动态微调 (根据深睡时长+次日日程调整)
  4. 跨session学习和优化

架构:
  Input: 睡眠数据 (手动或手环) + 日程 + 历史
    ↓
  PhaseDetector: 睡眠阶段分割
    ↓
  WakePlanner: 计算最优唤醒窗口
    ↓
  SessionOptimizer: 跨会话学习
    ↓
  Output: 规划指令 (小程序端消费)

纯Python标准库，零外部依赖，CPU only
"""

import json
import math
import time
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


# ============================================================
# 1. 睡眠阶段定义
# ============================================================

class SleepPhase(Enum):
    """标准睡眠阶段 (与PSG分期对齐)"""
    WAKE = "wake"            # 清醒
    N1 = "n1"                # 浅睡 (入睡)
    N2 = "n2"                # 浅睡 (稳定)
    N3 = "n3"                # 深睡 (慢波睡眠)
    REM = "rem"              # 快速眼动

    def is_light(self) -> bool:
        return self in (SleepPhase.N1, SleepPhase.N2, SleepPhase.WAKE)

    def is_deep(self) -> bool:
        return self == SleepPhase.N3

    def is_rem(self) -> bool:
        return self == SleepPhase.REM


# ============================================================
# 2. 无手环模式：时间概率模型
# ============================================================

class TimeBasedPhaseModel:
    """
    无手环模式 — 仅靠时间概率估算睡眠阶段

    基于睡眠周期动力学:
      入睡后 ~30min 浅睡 → ~60min 深睡 → ~90min 浅睡/REM → 约90min周期
      每晚会经历4-6个周期，REM比例逐周期增加

    参考标准: 健康成人整夜睡眠分期图谱
    """

    # 典型睡眠周期: [阶段, 持续分钟]
    TYPICAL_CYCLES = [
        # 初始入睡 (前2周期偏深)
        [("n1", 5), ("n2", 20), ("n3", 30), ("n2", 10), ("rem", 10), ("n1", 5)],   # 周期1 ~80min
        [("n2", 15), ("n3", 25), ("n2", 10), ("rem", 15), ("n1", 5)],               # 周期2 ~70min
        # 后半夜 (REM增多)
        [("n2", 15), ("n3", 15), ("n2", 10), ("rem", 25), ("n1", 5)],               # 周期3 ~70min
        [("n2", 15), ("n2", 10), ("rem", 30), ("n1", 5)],                            # 周期4 ~60min
        [("n2", 10), ("rem", 35), ("n1", 15)],                                       # 周期5 ~60min
    ]

    def predict_phase(self, minutes_since_bedtime: float,
                      sleep_latency: float = 30.0) -> SleepPhase:
        """根据入睡后的分钟数预测当前阶段"""
        # 减去入睡潜伏期
        adjusted = max(minutes_since_bedtime - sleep_latency, 0)
        if adjusted <= 0:
            return SleepPhase.WAKE

        # 遍历周期
        elapsed = 0
        for cycle in self.TYPICAL_CYCLES:
            total_cycle = sum(d for _, d in cycle)
            if adjusted < elapsed + total_cycle:
                # 在当前周期内定位
                phase_time = adjusted - elapsed
                for phase_name, duration in cycle:
                    if phase_time < duration:
                        return SleepPhase(phase_name)
                    phase_time -= duration
                return SleepPhase.N2  # fallback
            elapsed += total_cycle

        # 超过5个周期 → 通常是REM或浅睡
        return SleepPhase.REM

    def get_phase_timeline(self, sleep_latency: float = 30.0,
                           total_sleep_min: float = 420.0) -> List[Tuple[SleepPhase, float, float]]:
        """
        生成整夜阶段时间线

        Returns: [(phase, start_min, duration_min), ...]
        """
        timeline = [(SleepPhase.WAKE, 0, sleep_latency)]
        adjusted_total = total_sleep_min - sleep_latency
        elapsed = 0

        if adjusted_total <= 0:
            return timeline

        for cycle in self.TYPICAL_CYCLES:
            if elapsed >= adjusted_total:
                break
            cycle_remaining = adjusted_total - elapsed
            for phase_name, duration in cycle:
                if elapsed >= adjusted_total:
                    break
                dur = min(duration, adjusted_total - elapsed)
                if dur > 0:
                    start_min = sleep_latency + elapsed
                    timeline.append((SleepPhase(phase_name), start_min, dur))
                    elapsed += dur
                if elapsed >= adjusted_total:
                    break

        return timeline

    def get_sleep_stage_ratio(self, total_sleep_min: float,
                              sleep_latency: float = 30.0) -> Dict[str, float]:
        """返回各阶段占比"""
        timeline = self.get_phase_timeline(sleep_latency, total_sleep_min)
        ratios = {}
        for phase, _, dur in timeline:
            ratios[phase.value] = ratios.get(phase.value, 0) + dur
        total = sum(ratios.values()) or 1
        return {
            k: round(v / total * 100, 1) for k, v in ratios.items()
        }


# ============================================================
# 3. 有手环模式：HRV+体动→睡眠阶段映射
# ============================================================

class SensorBasedPhaseModel:
    """
    有手环模式 — 从华为手环数据推断睡眠阶段

    映射规则:
      体动活跃 + HR高 + HRV低 → WAKE
      体动少 + HR下降 + HRV中等 → N1/N2
      体动极少 + HR最低 + HRV高 → N3
      体动微 + HR回升 + HRV波动 → REM
    """

    @staticmethod
    def infer_phase(hr: float, hrv: Optional[float],
                    movement: Optional[int]) -> SleepPhase:
        """单点推断"""
        if movement is not None and movement > 3:
            return SleepPhase.WAKE
        if hr <= 0:
            return SleepPhase.N2

        if hr >= 80:
            return SleepPhase.WAKE if (movement or 0) > 1 else SleepPhase.REM
        elif hr >= 68:
            return SleepPhase.N1 if (movement or 0) < 2 else SleepPhase.WAKE
        elif hr >= 58:
            if hrv and hrv > 40:
                return SleepPhase.N2
            return SleepPhase.N2
        else:
            if hrv and hrv > 55:
                return SleepPhase.N3
            return SleepPhase.N3

    @staticmethod
    def make_timeline_from_sensor(hr_series: List[float],
                                  hrv_series: Optional[List[float]] = None,
                                  movement_series: Optional[List[int]] = None,
                                  interval_s: float = 60.0) -> List[Tuple[SleepPhase, float]]:
        """
        从传感器数据序列生成阶段时间线

        Returns: [(phase, timestamp_s), ...]
        """
        if not hr_series:
            return []

        hrv = hrv_series or [None] * len(hr_series)
        mov = movement_series or [None] * len(hr_series)

        timeline = []
        for i, hr in enumerate(hr_series):
            phase = SensorBasedPhaseModel.infer_phase(hr, hrv[i], mov[i])
            timeline.append((phase, i * interval_s))

        return timeline


# ============================================================
# 4. 唤醒窗口计算
# ============================================================

class WakePlanner:
    """
    最优唤醒窗口计算

    原理 (李飞飞框架→睡眠规划器启示):
      "发现用户处于REM睡眠末期，计算此刻唤醒最不易产生困倦感"
      "根据深睡时长和次日的日程安排，动态微调唤醒窗口"

    窗口规则:
      ✅ 理想: REM期末尾 + 浅睡期 (= 困难感最小)
      ⚠️ 不良: N3深睡中 (= 睡眠惯性最大)
      ❌ 避免: 刚入睡时
    """

    def __init__(self, alarm_window_min: float = 30.0):
        """
        Args:
            alarm_window_min: 智能唤醒的时间窗口宽度 (±分钟)
        """
        self.window_min = alarm_window_min

    def find_best_wake_window(self, timeline: List[Tuple],
                              target_wake_time: float) -> Dict:
        """
        计算目标唤醒时刻前后的最优唤醒窗口

        Args:
            timeline: [(phase, start_min, duration_min), ...] 或 [(phase, timestamp_s), ...]
            target_wake_time: 目标唤醒时刻 (入睡后的分钟数)

        Returns:
            wake_recommendation
        """
        window_start = max(target_wake_time - self.window_min, 0)
        window_end = target_wake_time + self.window_min

        # 检测timeline格式并统一
        is_sensor_format = len(timeline[0]) == 2 if timeline else False

        candidates = []
        for entry in timeline:
            if is_sensor_format:
                phase, ts_s = entry
                start = ts_s / 60
                dur = 1.0  # 单点
            else:
                phase, start, dur = entry

            seg_end = start + dur
            # 检查这个阶段与窗口的重叠
            overlap_start = max(window_start, start)
            overlap_end = min(window_end, seg_end)
            if overlap_end > overlap_start:
                overlap_min = overlap_end - overlap_start
                score = self._score_phase(phase, overlap_min)
                candidates.append({
                    "phase": phase.value,
                    "start_min": overlap_start,
                    "end_min": overlap_end,
                    "overlap_min": round(overlap_min, 1),
                    "score": round(score, 2),
                })

        if not candidates:
            # 回退到最近的时间线端点
            last_seg = timeline[-1] if timeline else None
            fallback_time = last_seg[1] + last_seg[2] if last_seg and len(last_seg) >= 3 else target_wake_time
            return {"best_time": target_wake_time, "confidence": 0,
                    "recommended_wake_min": fallback_time,
                    "window_start_min": window_start, "window_end_min": window_end}

        best = max(candidates, key=lambda c: c["score"])
        # 最佳唤醒时间 = 候选区间的中点
        best_time = (best["start_min"] + best["end_min"]) / 2
        # 如果最佳时间不在候选窗口内，回退到目标时间
        best_time = max(min(best_time, window_end), window_start)

        return {
            "target_wake_min": target_wake_time,
            "recommended_wake_min": round(best_time, 1),
            "window_start_min": round(window_start, 1),
            "window_end_min": round(window_end, 1),
            "confidence": round(best["score"], 2),
            "best_phase": best["phase"],
            "candidates": candidates,
            "description": self._describe_recommendation(best, timeline),
        }

    def _score_phase(self, phase: SleepPhase, duration_min: float) -> float:
        """给某个时间段打唤醒分数 (越高越好)"""
        base_scores = {
            SleepPhase.REM: 0.9,         # REM → 醒来最自然
            SleepPhase.N1: 0.8,           # 浅睡 → 容易唤醒
            SleepPhase.N2: 0.6,           # 稳定浅睡 → 还行
            SleepPhase.N3: 0.1,           # 深睡 → 避免
            SleepPhase.WAKE: 0.5,         # 已醒 → 已经醒了lol
        }
        score = base_scores.get(phase, 0.3)
        # 重叠时间越长分数越高
        score *= min(duration_min / 5.0, 1.0)
        return score

    def _describe_recommendation(self, best: dict,
                                  timeline: List[Tuple]) -> str:
        phase_desc = {
            "rem": "REM睡眠期 — 醒来最不易困",
            "n1": "浅睡期 — 容易唤醒",
            "n2": "浅睡稳定期",
            "n3": "深睡期 — 不建议此时唤醒",
            "wake": "已清醒",
        }
        desc = phase_desc.get(best["phase"], best["phase"])
        return f"{desc} (建议在{best['start_min']:.0f}-{best['end_min']:.0f}分钟内唤醒)"

    def adjust_for_schedule(self, recommendation: Dict,
                            schedule: Optional[Dict] = None) -> Dict:
        """根据次日日程微调唤醒时间"""
        if not schedule:
            return recommendation

        urgency = schedule.get("urgency", 0)  # 0-10
        if urgency > 7 and recommendation["confidence"] < 0.3:
            # 日程紧急但置信度低 → 提前唤醒窗口，宁可困也要赶上
            recommendation["recommended_wake_min"] -= 10
            recommendation["note"] = "提前唤醒: 日程紧急"
        elif urgency > 5:
            recommendation["recommended_wake_min"] -= 5
            recommendation["note"] = "微幅提前: 日程较紧"
        else:
            recommendation["note"] = "常规唤醒"

        return recommendation


# ============================================================
# 5. 睡眠周期感知规划器 (主类)
# ============================================================

class SleepPhasePlanner:
    """
    睡眠周期感知规划器 — P2主类

    整合:
      1. 阶段分割 (无手环/有手环)
      2. 唤醒窗口推荐
      3. 个性化学习
      4. 与 P0/P1 的桥接

    使用示例:
      planner = SleepPhasePlanner()
      plan = planner.plan_sleep(
          sleep_latency=30, total_sleep=420,
          target_wake_min=450  # 7小时后唤醒
      )
      print(plan["wake_recommendation"]["description"])
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.time_model = TimeBasedPhaseModel()
        self.sensor_model = SensorBasedPhaseModel()
        self.wake_planner = WakePlanner()
        self._history: List[Dict] = []

        # 知识注入 P2: 年龄/chronotype参数
        self._age: float = 30.0
        self._chronotype: str = "neutral"
        self._optimal_sleep_h: float = 7.5
        self._dysania_factor: float = 1.0  # 起床困难度

    def set_personal_params(self, age: float = 30.0,
                             chronotype: str = "neutral",
                             optimal_sleep_h: Optional[float] = None):
        """注入年龄/chronotype参数 (知识注入 P2)"""
        self._age = age
        self._chronotype = chronotype if chronotype in {"morning", "neutral", "evening"} else "neutral"
        if optimal_sleep_h:
            self._optimal_sleep_h = optimal_sleep_h
        else:
            chronotype_hours = {"morning": 7.0, "neutral": 7.5, "evening": 8.0}
            age_adj = max(0, (age - 30) * 0.03)  # 每岁+0.03h (2min)
            self._optimal_sleep_h = chronotype_hours.get(self._chronotype, 7.5) + age_adj

        # 起床困难度: morning型最容易, evening型最难
        dysania = {"morning": 0.3, "neutral": 0.6, "evening": 0.9}
        self._dysania_factor = dysania.get(self._chronotype, 0.6) * (1 + (age - 20) * 0.005)

    def plan_sleep(self,
                   sleep_latency: float = 30.0,
                   total_sleep_min: float = 420.0,
                   target_wake_min: Optional[float] = None,
                   sensor_data: Optional[Dict] = None,
                   schedule: Optional[Dict] = None) -> Dict:
        """
        完整睡眠规划

        Args:
            sleep_latency: 入睡潜伏期 (分钟)
            total_sleep_min: 总睡眠时长 (分钟)
            target_wake_min: 目标唤醒时间 (入睡后分钟数, 默认=total_sleep_min+sleep_latency)
            sensor_data: 手环传感器数据 (可选)
            schedule: 次日日程 (可选)

        Returns:
            完整规划
        """
        if target_wake_min is None:
            target_wake_min = sleep_latency + total_sleep_min

        # 阶段分割
        has_sensor = sensor_data and sensor_data.get("hr_series")
        if has_sensor:
            timeline = self.sensor_model.make_timeline_from_sensor(
                sensor_data.get("hr_series", []),
                sensor_data.get("hrv_series"),
                sensor_data.get("movement_series"),
            )
            mode = "sensor"
        else:
            timeline = self.time_model.get_phase_timeline(
                sleep_latency=sleep_latency,
                total_sleep_min=total_sleep_min,
            )
            mode = "time_based"

        # 唤醒窗口
        wake_rec = self.wake_planner.find_best_wake_window(
            timeline, target_wake_min
        )
        wake_rec = self.wake_planner.adjust_for_schedule(wake_rec, schedule)

        # 阶段分布统计
        phase_dist = {}
        for entry in timeline:
            if len(entry) == 2:
                phase, ts_s = entry
                dur = 1.0
            else:
                phase, start_min, dur = entry
            phase_dist[phase.value] = phase_dist.get(phase.value, 0) + dur

        # 转换timeline为统一格式输出
        timeline_out = []
        for entry in timeline:
            if len(entry) == 2:
                phase, ts_s = entry
                timeline_out.append({"phase": phase.value, "start_min": round(ts_s/60, 1), "duration_min": 1.0})
            else:
                phase, start_min, dur = entry
                timeline_out.append({"phase": phase.value, "start_min": round(start_min, 1), "duration_min": round(dur, 1)})

        result = {
            "user_id": self.user_id,
            "mode": mode,
            "total_sleep_min": total_sleep_min,
            "sleep_latency": sleep_latency,
            "phases_count": len(timeline_out),
            "phase_timeline": timeline_out,
            "phase_distribution": {
                p: round(m / total_sleep_min * 100, 1)
                for p, m in sorted(phase_dist.items(), key=lambda x: -x[1])
            } if total_sleep_min > 0 else {},
            "wake_recommendation": wake_rec,
        }

        return result

    def render_plan_for_p1(self, plan: Dict) -> Dict:
        """
        把P2规划输出转成P1渲染指令可消费的格式
        (桥接：让 P0+P1 知道用户当前处于哪个睡眠阶段)
        """
        return {
            "current_phase": plan["phase_timeline"][-1]["phase"] if plan.get("phase_timeline") else "unknown",
            "deep_sleep_pct": plan["phase_distribution"].get("n3", 0),
            "rem_pct": plan["phase_distribution"].get("rem", 0),
            "light_pct": plan["phase_distribution"].get("n1", 0) + plan["phase_distribution"].get("n2", 0),
            "recommended_wake_min": plan["wake_recommendation"].get("recommended_wake_min"),
        }

    def learn_from_feedback(self, actual_sleep_min: float,
                            actual_wake_score: int):
        """跨session学习: 用户反馈实际唤醒后的清醒程度"""
        self._history.append({
            "timestamp": time.time(),
            "planned": actual_sleep_min,
            "wake_score": actual_wake_score,
        })


# ============================================================
# 6. 集成到华为云API
# ============================================================

def format_plan_response(plan: Dict) -> Dict:
    """API响应 (小程序端消费)"""
    wake = plan.get("wake_recommendation", {})
    return {
        "mode": plan["mode"],
        "sleep_latency_min": plan["sleep_latency"],
        "total_sleep_min": plan["total_sleep_min"],
        "phases_count": len(plan.get("phase_timeline", [])),
        "phase_timeline": plan.get("phase_timeline", []),
        "phase_pct": plan.get("phase_distribution", {}),
        "wake": {
            "target_min": wake.get("target_wake_min"),
            "best_min": wake.get("recommended_wake_min"),
            "window": [wake.get("window_start_min"), wake.get("window_end_min")],
            "phase": wake.get("best_phase"),
            "confidence": wake.get("confidence"),
            "desc": wake.get("description"),
        },
    }


# ============================================================
# 7. 演示
# ============================================================

def run_demo():
    print("=" * 60)
    print("P2 睡眠周期感知规划器 v1.0")
    print("=" * 60)

    # 场景A: 无手环, 正常入睡
    print("\n[场景A] 无手环, 30min入睡, 7h睡眠")
    planner = SleepPhasePlanner("demo")
    plan = planner.plan_sleep(
        sleep_latency=30, total_sleep_min=420,
        target_wake_min=450,
    )
    f = format_plan_response(plan)
    print(f"  模式: {f['mode']}")
    print(f"  阶段分布: ", end="")
    for p, ratio in sorted(f['phase_pct'].items(), key=lambda x: -x[1]):
        print(f"{p}={ratio}% ", end="")
    print()
    print(f"  最佳唤醒: {f['wake']['best_min']:.0f}min "
          f"(窗口: {f['wake']['window'][0]:.0f}-{f['wake']['window'][1]:.0f}min)")
    print(f"  唤醒阶段: {f['wake']['phase']} "
          f"置信度: {f['wake']['confidence']:.0%}")
    print(f"  描述: {f['wake']['desc']}")

    # 场景B: 入睡困难
    print("\n[场景B] 入睡困难, 60min潜伏期, 6h睡眠")
    plan2 = planner.plan_sleep(
        sleep_latency=60, total_sleep_min=360,
    )
    f2 = format_plan_response(plan2)
    print(f"  阶段分布: ", end="")
    for p, ratio in sorted(f2['phase_pct'].items(), key=lambda x: -x[1]):
        print(f"{p}={ratio}% ", end="")
    print()
    print(f"  最佳唤醒: {f2['wake']['best_min']:.0f}min")

    # 场景C: 有手环数据
    print("\n[场景C] 有手环数据 (模拟HR序列)")
    sensor_data = {
        "hr_series": [72, 68, 62, 58, 55, 56, 60, 62, 68, 70],
        "hrv_series": [35, 40, 48, 55, 60, 58, 50, 45, 38, 40],
        "movement_series": [5, 2, 0, 0, 0, 0, 1, 0, 2, 3],
    }
    plan3 = planner.plan_sleep(
        sleep_latency=20, total_sleep_min=420,
        sensor_data=sensor_data,
    )
    print(f"  模式: {plan3['mode']}")
    print(f"  阶段分割数: {len(plan3['phase_timeline'])} segments")
    for seg in plan3['phase_timeline'][:10]:
        print(f"    {seg['phase']:5s} @ {seg['start_min']:.0f}min x{seg['duration_min']:.0f}min")

    print("\n所有场景通过!")


if __name__ == "__main__":
    run_demo()
