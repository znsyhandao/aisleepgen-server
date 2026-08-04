#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
闭环神经反馈渲染器 v1.1 — 离线指令模式
专注CPU可运行，输出小程序端可消费的渲染指令

设计哲学 (至尊宝框架启示):
  "渲染器输出 = 基于生理状态的神经反馈刺激指令集"
  渲染器本身在本地CPU跑，音频在播放端按指令执行

架构:
  Input: 用户睡眠数据 (心率/呼吸/HRV/压力)
    ↓
  Estimator: 状态估计 → 唤醒状态序列
    ↓
  Strategy: 策略表 → 状态→参数映射
    ↓
  Output: 渲染指令集 (JSON, 小程序前端消费)

指令集字段 (小程序播放器引擎使用):
  tempo_bpm:     呼吸引导节奏 (bpm)
  text_speed:    引导语语速 (0.7-1.0)
  silence_s:     引导句间隔 (秒)
  fade_in_s:     淡入时长
  fade_out_s:    淡出时长
  volume_db:     音量基准
  modulation:    环境音起伏调制
  envelope:      包络 (plateau/decay/sine/sleep)
  breathing_ratio: 吸:呼比例 (默认1:2)
"""

import json
import math
import os
import sys
import io
import time
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Tuple
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# ============================================================
# 1. 生理唤醒状态
# ============================================================

class ArousalState(Enum):
    ANXIOUS = "anxious"
    ALERT = "alert"
    CALM = "calm"
    DROWSY = "drowsy"
    SLEEPING = "sleeping"


# ============================================================
# 2. 渲染指令 — 核心输出结构
# ============================================================

@dataclass
class RenderInstruction:
    """
    渲染指令 — 小程序音频播放器直接消费

    使用场景:
      1. 全会话指令集 (session_plan): 预先算好整个睡眠过程的参数变化
      2. 实时指令 (realtime): 根据最新数据逐条返回
    """
    tempo_bpm: float = 6.0          # 呼吸引导节奏 (4-7)
    text_speed: float = 0.85        # 语速 (0.7-1.0)
    silence_s: float = 3.0          # 引导句间隔 (秒)
    fade_in_s: float = 5.0          # 淡入 (秒)
    fade_out_s: float = 30.0        # 淡出 (秒)
    volume_db: float = -2.0         # 音量基准 (dB)
    modulation_hz: float = 0.0      # 环境音起伏频率
    modulation_depth: float = 0.0   # 起伏深度
    envelope: str = "plateau"       # 包络: plateau/decay/sine/sleep
    breathing_in_s: float = 4.0     # 吸气时长 (秒)
    breathing_out_s: float = 8.0    # 呼气时长 (秒)
    phase: str = "onset"            # onset/middle/ending/sleep
    next_check_after_s: float = 60.0  # 多久后检查是否需要更新

    def to_dict(self) -> dict:
        return {
            "tempo_bpm": self.tempo_bpm,
            "text_speed": self.text_speed,
            "silence_s": self.silence_s,
            "fade_in_s": self.fade_in_s,
            "fade_out_s": self.fade_out_s,
            "volume_db": self.volume_db,
            "modulation": {
                "freq_hz": self.modulation_hz,
                "depth": self.modulation_depth,
            },
            "envelope": self.envelope,
            "breathing": {
                "in_s": self.breathing_in_s,
                "out_s": self.breathing_out_s,
                "ratio": f"1:{self.breathing_out_s/self.breathing_in_s:.0f}" if self.breathing_in_s > 0 else "0",
            },
            "phase": self.phase,
            "next_check_s": self.next_check_after_s,
        }


# ============================================================
# 3. 渲染策略表
# ============================================================

STRATEGIES = {
    ArousalState.ANXIOUS: {
        "desc": "高唤醒 → 慢呼吸、深低频、强引导",
        "instruction": RenderInstruction(
            tempo_bpm=4.0,
            text_speed=0.72,
            silence_s=5.0,
            fade_in_s=8.0,
            fade_out_s=60.0,
            volume_db=-3.0,
            modulation_hz=0.05,
            modulation_depth=0.25,
            envelope="decay",
            breathing_in_s=4.0,
            breathing_out_s=8.0,
            phase="onset",
            next_check_after_s=300.0,
        ),
        "auto_transition_s": 300,  # 5分钟后自动切换
        "auto_transition_to": ArousalState.ALERT,
    },
    ArousalState.ALERT: {
        "desc": "较高唤醒 → 温和引导、减速",
        "instruction": RenderInstruction(
            tempo_bpm=5.0,
            text_speed=0.78,
            silence_s=4.0,
            fade_in_s=5.0,
            fade_out_s=45.0,
            volume_db=-2.0,
            modulation_hz=0.08,
            modulation_depth=0.2,
            envelope="plateau",
            breathing_in_s=4.0,
            breathing_out_s=8.0,
            phase="onset",
            next_check_after_s=240.0,
        ),
        "auto_transition_s": 240,
        "auto_transition_to": ArousalState.CALM,
    },
    ArousalState.CALM: {
        "desc": "平稳 → 维持、自然引导",
        "instruction": RenderInstruction(
            tempo_bpm=6.0,
            text_speed=0.85,
            silence_s=3.0,
            fade_in_s=3.0,
            fade_out_s=60.0,
            volume_db=-1.5,
            modulation_hz=0.1,
            modulation_depth=0.15,
            envelope="plateau",
            breathing_in_s=4.0,
            breathing_out_s=8.0,
            phase="middle",
            next_check_after_s=180.0,
        ),
        "auto_transition_s": 180,
        "auto_transition_to": ArousalState.DROWSY,
    },
    ArousalState.DROWSY: {
        "desc": "低唤醒 → 减少言语、转向环境音",
        "instruction": RenderInstruction(
            tempo_bpm=6.0,
            text_speed=0.90,
            silence_s=8.0,
            fade_in_s=5.0,
            fade_out_s=120.0,
            volume_db=-4.0,
            modulation_hz=0.12,
            modulation_depth=0.1,
            envelope="sine",
            breathing_in_s=4.0,
            breathing_out_s=8.0,
            phase="ending",
            next_check_after_s=120.0,
        ),
        "auto_transition_s": 120,
        "auto_transition_to": ArousalState.SLEEPING,
    },
    ArousalState.SLEEPING: {
        "desc": "已入睡 → 停止引导、缓慢淡出",
        "instruction": RenderInstruction(
            tempo_bpm=0,
            text_speed=1.0,
            silence_s=999,
            fade_in_s=0,
            fade_out_s=300.0,
            volume_db=-10.0,
            modulation_hz=0.0,
            modulation_depth=0.0,
            envelope="sleep",
            breathing_in_s=0,
            breathing_out_s=0,
            phase="sleep",
            next_check_after_s=600.0,
        ),
        "auto_transition_s": None,
        "auto_transition_to": None,
    },
}


def get_instruction(state: ArousalState) -> RenderInstruction:
    s = STRATEGIES.get(state, STRATEGIES[ArousalState.CALM])
    return s["instruction"]


# ============================================================
# 4. 闭环渲染引擎
# ============================================================

class BiofeedbackRenderer:
    """
    闭环神经反馈渲染器

    三种使用模式:
      1. session_plan(hr=72, stress=6): 一键生成完整会话指令集
      2. tick(hr=72): 逐帧更新，返回当前指令
      3. from_audio_features(bpm=65, hrv=42): 从音频分析特征输入

    接入点:
      - POST /api/sleep/render-plan (deepseek_proxy.py)
      - POST /api/sleep/render-tick (实时更新)
    """

    def __init__(self, openid: str = "default"):
        self.openid = openid
        self.state: ArousalState = ArousalState.CALM
        self.instruction: RenderInstruction = get_instruction(ArousalState.CALM)
        self._state_start: float = time.time()
        self._transitions: List[Dict] = []
        self._session_id: str = datetime.now().strftime("%Y%m%d_%H%M%S")

    def estimate_state(self, hr: Optional[float] = None,
                       stress: Optional[int] = None,
                       sleep_data: Optional[Dict] = None) -> ArousalState:
        """从多种数据源推断生理唤醒状态"""
        # 如果有原始用户输入
        if stress is not None:
            if stress >= 8:
                return ArousalState.ANXIOUS
            elif stress >= 5:
                return ArousalState.ALERT
            elif stress >= 3:
                return ArousalState.CALM
            else:
                return ArousalState.DROWSY

        if hr is not None:
            if hr >= 85:
                return ArousalState.ANXIOUS
            elif hr >= 70:
                return ArousalState.ALERT
            elif hr >= 55:
                return ArousalState.CALM
            else:
                return ArousalState.DROWSY

        # 从睡眠数据推断
        if sleep_data:
            latency = sleep_data.get("sleep_latency", 0) or 0
            awake = sleep_data.get("awake_times", 0) or 0
            stress_l = sleep_data.get("stress_level", 5) or 5

            if latency > 60 or stress_l >= 8:
                return ArousalState.ANXIOUS
            elif latency > 30 or awake >= 3 or stress_l >= 5:
                return ArousalState.ALERT
            elif awake <= 1 or stress_l <= 3:
                return ArousalState.CALM

        return ArousalState.CALM

    def tick(self, hr: Optional[float] = None,
             stress: Optional[int] = None,
             sleep_data: Optional[Dict] = None) -> RenderInstruction:
        """
        逐帧更新渲染指令

        调用方: 前端定时轮询 (每60s)
        """
        new_state = self.estimate_state(hr, stress, sleep_data)

        # 检查自动状态转换 (时间驱动)
        elapsed = time.time() - self._state_start
        strategy = STRATEGIES.get(self.state)
        if strategy and strategy["auto_transition_s"]:
            if elapsed >= strategy["auto_transition_s"]:
                new_state = strategy["auto_transition_to"]

        self._transition_to(new_state)
        self.instruction = get_instruction(self.state)
        return self.instruction

    def _transition_to(self, new_state: ArousalState):
        if new_state != self.state:
            elapsed = time.time() - self._state_start
            self._transitions.append({
                "from": self.state.value,
                "to": new_state.value,
                "duration_s": round(elapsed, 1),
                "t": datetime.now().isoformat(),
            })
            self.state = new_state
            self._state_start = time.time()

    def session_plan(self, stress_level: int = 5,
                     sleep_latency: int = 30,
                     expected_duration_h: float = 7.0) -> Dict:
        """
        一键生成完整会话指令集

        输出: 带时间戳的指令序列，前端按时间播放
        """
        state = self.estimate_state(stress=stress_level)
        plan = {
            "session_id": self._session_id,
            "openid": self.openid,
            "generated_at": datetime.now().isoformat(),
            "estimated_duration_s": expected_duration_h * 3600,
            "initial_assessment": {
                "stress_level": stress_level,
                "sleep_latency": sleep_latency,
                "initial_state": state.value,
            },
            "phases": self._build_phases(state, expected_duration_h),
            "meta": {
                "renderer_version": "1.1",
                "framework": "biofeedback-closed-loop",
            },
        }
        return plan

    def _build_phases(self, start_state: ArousalState,
                      total_hours: float) -> List[Dict]:
        """构建会话阶段的指令序列"""
        stages = self._compute_stage_timeline(start_state, total_hours)
        phases = []
        cumulative = 0.0

        for stage_state, stage_dur_s in stages:
            instr = get_instruction(stage_state)
            d = instr.to_dict()
            d["start_at_s"] = round(cumulative, 1)
            d["duration_s"] = round(stage_dur_s, 1)
            d["state"] = stage_state.value
            d["desc"] = STRATEGIES[stage_state]["desc"]
            phases.append(d)
            cumulative += stage_dur_s

        return phases

    def _compute_stage_timeline(self, start_state: ArousalState,
                                total_hours: float) -> List[Tuple[ArousalState, float]]:
        """计算状态变化的时间线"""
        state_chain = [start_state]
        current = start_state

        # 沿着策略表的 auto_transition 走
        visited = set()
        while current and current != ArousalState.SLEEPING:
            if current in visited:
                break
            visited.add(current)
            s = STRATEGIES.get(current)
            if s and s["auto_transition_to"]:
                state_chain.append(s["auto_transition_to"])
                current = s["auto_transition_to"]
            else:
                break

        total_plan_s = total_hours * 3600

        if len(state_chain) == 1:
            return [(state_chain[0], total_plan_s)]

        # 分配各阶段时长: 第一段按策略的transition_after_s，其余均分
        phases = []
        first_strategy = STRATEGIES.get(state_chain[0])
        first_dur = min(first_strategy["auto_transition_s"], total_plan_s * 0.4)
        phases.append((state_chain[0], first_dur))
        remaining = total_plan_s - first_dur

        remaining_states = state_chain[1:]
        if not remaining_states:
            remaining_states = [ArousalState.DROWSY, ArousalState.SLEEPING]

        chunk = remaining / len(remaining_states)
        for st in remaining_states:
            dur = chunk if st != remaining_states[-1] else (remaining - (len(remaining_states)-1)*chunk)
            phases.append((st, max(dur, 60)))

        return phases

    def get_summary(self) -> Dict:
        return {
            "session_id": self._session_id,
            "current_state": self.state.value,
            "transition_count": len(self._transitions),
            "transitions": self._transitions[-10:],
        }

    def reset(self):
        self.state = ArousalState.CALM
        self.instruction = get_instruction(ArousalState.CALM)
        self._state_start = time.time()
        self._transitions = []
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")


# ============================================================
# 5. API 输出格式化
# ============================================================

def format_render_api_response(plan: Dict) -> Dict:
    """格式化API响应 (便于小程序消费)"""
    phases_compact = []
    for p in plan["phases"]:
        phases_compact.append({
            "state": p["state"],
            "start_s": p["start_at_s"],
            "dur_s": p["duration_s"],
            "bpm": p["tempo_bpm"],
            "vol": p["volume_db"],
            "spd": p["text_speed"],
            "silence": p["silence_s"],
            "fade_in": p["fade_in_s"],
            "fade_out": p["fade_out_s"],
            "env": p["envelope"],
            "breath": p["breathing"],
            "mod": p["modulation"],
            "desc": p["desc"],
        })

    return {
        "session_id": plan["session_id"],
        "generated_at": plan["generated_at"],
        "estimate_h": round(plan["estimated_duration_s"] / 3600, 1),
        "initial": plan["initial_assessment"],
        "phases": phases_compact,
        "version": plan["meta"]["renderer_version"],
    }


# ============================================================
# 6. 演示
# ============================================================

def run_demo():
    r = BiofeedbackRenderer()

    print("方案A: 一键生成会话指令集 (压力=7, 入睡困难)")
    plan = r.session_plan(stress_level=7, sleep_latency=45)
    summary = format_render_api_response(plan)
    print(f"  会话: {summary['session_id']}")
    print(f"  预估时长: {summary['estimate_h']}h")
    print(f"  初始评估: 压力={summary['initial']['stress_level']}, "
          f"初始状态={summary['initial']['initial_state']}")
    print(f"  阶段数: {len(summary['phases'])}")
    for p in summary['phases']:
        start_min = p['start_s'] / 60
        dur_min = p['dur_s'] / 60
        print(f"    [{start_min:.0f}-{start_min+dur_min:.0f}min] "
              f"{p['state']}: {p['bpm']}bpm vol={p['vol']}dB "
              f"inhale={p['breath']['in_s']}s exhale={p['breath']['out_s']}s "
              f"silence={p['silence']}s envelope={p['env']}")

    print("\n方案B: 逐帧更新 (模拟焦虑→平静→困倦)")
    for tick_hr, tick_stress in [(78, 6), (72, 5), (65, 4), (58, 3), (55, 2)]:
        instr = r.tick(hr=tick_hr, stress=tick_stress)
        print(f"  HR={tick_hr} stress={tick_stress} → "
              f"状态={r.state.value} "
              f"呼吸={instr.tempo_bpm}bpm "
              f"语速={instr.text_speed}x "
              f"吸/呼={instr.breathing_in_s}s/{instr.breathing_out_s}s")


if __name__ == "__main__":
    run_demo()
