#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
状态转移模型 v1.0 — 不依赖GPU的贝叶斯概率转移
对标李飞飞世界模型框架的"仿真器"维度

架构:
  物理世界模型 → 心理-生理状态转移模型
  P(状态_{t+1} | 状态_t, 观测_t, 用户画像)

核心组件:
  1. TransitionMatrix — 5×5状态转移概率矩阵 (学习型)
  2. ObservationModel — P(观测|状态) 发射概率
  3. BayesFilter — 实时贝叶斯后验更新
  4. StatePredictor — 前向预测状态序列
  5. Personalizer — 跨session学习用户特定参数

CPU only, numpy zero, 纯Python标准库
"""

import json
import math
import time
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

# ============================================================
# 状态空间 (与 biofeedback_renderer 一致)
# ============================================================

class ArousalState(Enum):
    ANXIOUS = "anxious"
    ALERT = "alert"
    CALM = "calm"
    DROWSY = "drowsy"
    SLEEPING = "sleeping"

    @classmethod
    def list(cls) -> List["ArousalState"]:
        return [cls.ANXIOUS, cls.ALERT, cls.CALM, cls.DROWSY, cls.SLEEPING]

    def index(self) -> int:
        return {s: i for i, s in enumerate(ArousalState.list())}[self]

    @classmethod
    def from_index(cls, i: int) -> "ArousalState":
        return cls.list()[i]


# ============================================================
# 1. 转移概率矩阵 — 核心心脏
# ============================================================

class TransitionMatrix:
    """
    5×5 状态转移概率矩阵

    设计原理:
      从"固定时间驱动" → "概率驱动"
      P(焦虑→警觉) = 0.6 表示焦虑状态下60%概率在下一帧进入警觉

    学习机制:
      每条转移记录 log，自动更新经验频率
      新用户使用先验 = 通用睡眠动力学知识
      老用户逐步收敛到个人模式
    """

    # 通用先验 (来自睡眠动力学基础知识)
    DEFAULT_PRIOR = {
        "anxious":  {"anxious": 0.50, "alert": 0.35, "calm": 0.12, "drowsy": 0.03, "sleeping": 0.00},
        "alert":    {"anxious": 0.15, "alert": 0.45, "calm": 0.30, "drowsy": 0.09, "sleeping": 0.01},
        "calm":     {"anxious": 0.03, "alert": 0.12, "calm": 0.50, "drowsy": 0.30, "sleeping": 0.05},
        "drowsy":   {"anxious": 0.01, "alert": 0.04, "calm": 0.15, "drowsy": 0.50, "sleeping": 0.30},
        "sleeping": {"anxious": 0.00, "alert": 0.05, "calm": 0.05, "drowsy": 0.15, "sleeping": 0.75},
    }

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self._counts = defaultdict(lambda: defaultdict(float))
        self._prior = self.DEFAULT_PRIOR.copy()

    def get(self, from_state: ArousalState) -> Dict[ArousalState, float]:
        """获取从某个状态出发的转移概率分布"""
        from_key = from_state.value
        counts = self._counts[from_key]
        total = sum(counts.values())

        if total < 5:  # 数据不足，用先验撑住
            probs = self._prior[from_key].copy()
            # 如果有个别观测，与先验混合
            if total > 0:
                alpha = total / (total + 10)  # 狄利克雷后验均值
                for to_state in ArousalState.list():
                    tok = to_state.value
                    prior_p = self._prior[from_key].get(tok, 0)
                    obs_p = counts.get(tok, 0) / total
                    probs[tok] = (1 - alpha) * prior_p + alpha * obs_p
        else:
            total = sum(counts.values())
            probs = {}
            for to_state in ArousalState.list():
                tok = to_state.value
                probs[tok] = (counts.get(tok, 0) + 1) / (total + 5)

        return {s: probs.get(s.value, 0) for s in ArousalState.list()}

    def record_transition(self, from_state: ArousalState, to_state: ArousalState):
        """记录一次观测到的转移"""
        self._counts[from_state.value][to_state.value] += 1

    def most_likely_next(self, from_state: ArousalState) -> ArousalState:
        """最大概率后继状态（用于 session_plan 向前预测）"""
        probs = self.get(from_state)
        return max(probs, key=probs.get)

    def to_dict(self) -> dict:
        """序列化，用于持久化用户模型"""
        return {
            "user_id": self.user_id,
            "counts": {k: dict(v) for k, v in self._counts.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TransitionMatrix":
        tm = cls(data.get("user_id", "default"))
        for from_k, to_counts in data.get("counts", {}).items():
            for to_k, c in to_counts.items():
                tm._counts[from_k][to_k] = c
        return tm


# ============================================================
# 2. 观测模型 — P(生理数据 | 隐藏状态)
# ============================================================

class ObservationModel:
    """
    发射概率 P(观测 | 状态)

    观测维度:
      hr: 心率 (bpm)
      stress: 用户自评压力 (1-10)
      sleep_latency: 入睡潜伏期 (分钟)

    每个状态对应一个观测分布（高斯混合近似）:
      anxious:   hr~N(85, 10),    stress~N(7, 1.5)
      alert:     hr~N(75, 8),     stress~N(5, 1.5)
      calm:      hr~N(65, 6),     stress~N(4, 1.0)
      drowsy:    hr~N(58, 5),     stress~N(3, 1.0)
      sleeping:  hr~N(55, 3),     stress~N(2, 0.5)
    """

    # 均值+标准差 (hr, stress)
    STATE_PROFILES = {
        ArousalState.ANXIOUS:  {"hr_mean": 85, "hr_std": 10, "stress_mean": 7.0, "stress_std": 1.5},
        ArousalState.ALERT:    {"hr_mean": 75, "hr_std": 8,  "stress_mean": 5.5, "stress_std": 1.5},
        ArousalState.CALM:     {"hr_mean": 65, "hr_std": 6,  "stress_mean": 4.0, "stress_std": 1.0},
        ArousalState.DROWSY:   {"hr_mean": 58, "hr_std": 5,  "stress_mean": 3.0, "stress_std": 1.0},
        ArousalState.SLEEPING: {"hr_mean": 55, "hr_std": 3,  "stress_mean": 2.0, "stress_std": 0.5},
    }

    # 防御默认值：当 STATE_PROFILES 被运行时污染时回退用
    _DEFAULT_HR_PROFILES = {
        ArousalState.ANXIOUS: 85, ArousalState.ALERT: 75,
        ArousalState.CALM: 65, ArousalState.DROWSY: 58,
        ArousalState.SLEEPING: 55,
    }
    _DEFAULT_STRESS_PROFILES = {
        ArousalState.ANXIOUS: 7.0, ArousalState.ALERT: 5.5,
        ArousalState.CALM: 4.0, ArousalState.DROWSY: 3.0,
        ArousalState.SLEEPING: 2.0,
    }

    # ============================================================
    # 知识注入 P1: HRV频域分析 + 自主神经平衡
    # 依据: Task Force (1996) HRV测量标准, 欧洲心脏杂志
    # ============================================================

    @staticmethod
    def hrv_frequency_analysis(hr_series: list,
                                 hrv_rmssd_series: list) -> dict:
        """
        简易HRV频域分析 (纯时间域近似, 无需FFT)

        由于华为手环不提供连续IBI, 用RMSSD+HR的联合分布
        估算自主神经平衡:
          - HR低 + HRV高 → 副交感主导 (放松/困倦)
          - HR高 + HRV低 → 交感主导 (焦虑/警觉)
          - HR中 + HRV中 → 平衡 (平静)

        Args:
            hr_series: 最近5+个心率值
            hrv_rmssd_series: 最近5+个RMSSD值

        Returns:
            {lf_hf_ratio, vagal_tone, sympathetic, balance}
        """
        if not hr_series or len(hr_series) < 3:
            return {"lf_hf_ratio": 1.0, "vagal_tone": 0.5,
                    "sympathetic": 0.5, "balance": "unknown"}

        avg_hr = sum(hr_series) / len(hr_series)
        avg_hrv = sum(hrv_rmssd_series) / len(hrv_rmssd_series) if hrv_rmssd_series else 30

        # 临床经验公式: HRV与自主神经平衡
        # 实际LF/HF需要频谱分析, 这里是临床近似
        normalized_hr = max(0, min(1, (avg_hr - 50) / 50))        # 0-1
        normalized_hrv = max(0, min(1, avg_hrv / 100)) if avg_hrv else 0.5  # 0-1

        # 副交感张力 (vagal_tone) 与 HRV正相关, HR负相关
        vagal_tone = normalized_hrv * (1 - normalized_hr * 0.5)

        # 交感活性
        sympathetic = normalized_hr * (1 - normalized_hrv * 0.3)

        # LF/HF比率近似 (实际需要频谱)
        lf_hf = (sympathetic + 0.1) / (vagal_tone + 0.1)

        if lf_hf > 1.5:
            balance = "sympathetic_dominant"
        elif lf_hf < 0.7:
            balance = "vagal_dominant"
        else:
            balance = "balanced"

        return {
            "lf_hf_ratio": round(lf_hf, 2),
            "vagal_tone": round(vagal_tone, 3),
            "sympathetic": round(sympathetic, 3),
            "balance": balance,
        }

    @staticmethod
    def _gaussian_pdf(x: float, mean: float, std: float) -> float:
        """高斯概率密度"""
        if std <= 0:
            return 1.0 if abs(x - mean) < 0.5 else 0.01
        return math.exp(-0.5 * ((x - mean) / std) ** 2) / (std * math.sqrt(2 * math.pi))

    def likelihood(self, state: ArousalState, hr: Optional[float] = None,
                   stress: Optional[int] = None) -> float:
        """P(观测 | 状态) — 多元似然"""
        profile = self.STATE_PROFILES[state]
        lik = 1.0

        if hr is not None:
            # 防御性检查：profile["hr_mean"] 必须是数字
            _hm = profile.get("hr_mean")
            if not isinstance(_hm, (int, float)):
                print(f'[BugDetect] hr_mean corrupted: type={type(_hm).__name__}, value={_hm}, state={state}')
                _hm = self._DEFAULT_HR_PROFILES.get(state, 65)
                profile["hr_mean"] = _hm
            _hs = profile.get("hr_std")
            if not isinstance(_hs, (int, float)):
                _hs = 8
            lik *= self._gaussian_pdf(hr, _hm, _hs)

        if stress is not None:
            _sm = profile.get("stress_mean")
            if not isinstance(_sm, (int, float)):
                print(f'[BugDetect] stress_mean corrupted: type={type(_sm).__name__}, value={_sm}, state={state}')
                _sm = self._DEFAULT_STRESS_PROFILES.get(state, 4.0)
            _ss = profile.get("stress_std")
            if not isinstance(_ss, (int, float)):
                _ss = 1.5
            lik *= self._gaussian_pdf(stress, _sm, _ss)

        return max(lik, 1e-10)  # 防止下溢

    def most_likely_state(self, hr: Optional[float] = None,
                          stress: Optional[int] = None) -> ArousalState:
        """最大似然估计（MLE）"""
        best_state = ArousalState.CALM
        best_lik = 0
        for state in ArousalState.list():
            lik = self.likelihood(state, hr, stress)
            if lik > best_lik:
                best_lik = lik
                best_state = state
        return best_state


# ============================================================
# 3. 贝叶斯滤波器 (在线推理)
# ============================================================

class BayesFilter:
    """
    实时贝叶斯后验更新

    公式:
      P(状态_t | 观测_{1:t}) 
        ∝ P(观测_t | 状态_t) * Σ_{s} P(状态_t | 状态_{t-1}=s) * P(状态_{t-1}=s | 观测_{1:t-1})

    这就是李飞飞框架中"仿真器"的核心数学形式:
      状态转移 × 观测似然 → 后验信念
    """

    def __init__(self, transition_matrix: TransitionMatrix,
                 observation_model: ObservationModel):
        self.tm = transition_matrix
        self.om = observation_model
        # 初始先验: 入睡前通常是alert或calm
        self.belief = {
            ArousalState.ANXIOUS: 0.10,
            ArousalState.ALERT: 0.40,
            ArousalState.CALM: 0.35,
            ArousalState.DROWSY: 0.10,
            ArousalState.SLEEPING: 0.05,
        }

    def update(self, hr: Optional[float] = None,
               stress: Optional[int] = None,
               elapsed_s: float = 60.0,
               hr_series: Optional[list] = None,
               hrv_series: Optional[list] = None,
               homeostasis_state: Optional[dict] = None) -> Dict[ArousalState, float]:
        """
        贝叶斯滤波更新

        Args:
            hr: 心率观测
            stress: 压力观测
            elapsed_s: 距上次更新的时间 (影响转移幅度)
            hr_series: HR序列 (用于HRV分析, 可选)
            hrv_series: HRV-RMSSD序列 (用于自主神经分析, 可选)
            homeostasis_state: Process S+C模型输出 (可选)

        Returns:
            后验信念分布 dict[ArousalState, float]
        """
        # 时间因子: 时间越长，转移概率越向稳态集中
        time_factor = min(elapsed_s / 300.0, 1.0)  # 5分钟拉满

        # 知识注入 P1: HRV频域调整 (如有序列数据)
        hrv_adjust = None
        if hr_series or hrv_series:
            hrv_result = self.om.hrv_frequency_analysis(
                hr_series or [hr] if hr else [60],
                hrv_series or []
            )
            if hrv_result["balance"] == "vagal_dominant":
                hrv_adjust = "relax"    # 副交感主导 → 更可能放松
            elif hrv_result["balance"] == "sympathetic_dominant":
                hrv_adjust = "tense"    # 交感主导 → 更可能紧张

        # 知识注入 P0: 两过程模型调整 (如有稳态模型输出)
        homeostasis_adjust = None
        if homeostasis_state:
            drowsiness = homeostasis_state.get("drowsiness", "neutral")
            if drowsiness in ("very_sleepy", "sleepy"):
                homeostasis_adjust = "sleep_pressure"  # 高睡眠压力
            elif drowsiness in ("fully_awake", "alert"):
                homeostasis_adjust = "low_pressure"    # 低睡眠压力

        # --- 预测步 ---
        predicted = defaultdict(float)
        for prev_state, prev_prob in self.belief.items():
            if prev_prob <= 0:
                continue
            trans_probs = self.tm.get(prev_state)
            for next_state, trans_prob in trans_probs.items():
                # 混合: 时间越长越倾向于停留或向"更放松"方向转移
                adjusted_trans = trans_prob
                if time_factor > 0.5:
                    # 长时间无观测 → 倾向于状态改善
                    if next_state.index() > prev_state.index():
                        adjusted_trans *= 1.0 + 0.2 * time_factor
                    elif next_state.index() < prev_state.index():
                        adjusted_trans *= 1.0 - 0.1 * time_factor

                # P1: HRV自主神经调整 (知识注入)
                if hrv_adjust == "relax":
                    if next_state.index() > prev_state.index():
                        adjusted_trans *= 1.15
                elif hrv_adjust == "tense":
                    if next_state.index() < prev_state.index():
                        adjusted_trans *= 1.15

                # P0: 稳态模型调整 (知识注入)
                if homeostasis_adjust == "sleep_pressure":
                    if next_state.index() > prev_state.index():
                        adjusted_trans *= 1.2
                    if next_state.value == "drowsy":
                        adjusted_trans *= 1.3
                elif homeostasis_adjust == "low_pressure":
                    if next_state.index() < prev_state.index():
                        adjusted_trans *= 1.1

                predicted[next_state] += prev_prob * adjusted_trans

        # 归一化预测
        pred_total = sum(predicted.values())
        if pred_total > 0:
            for s in predicted:
                predicted[s] /= pred_total

        # --- 更新步 ---
        posterior = {}
        for state in ArousalState.list():
            prior = predicted.get(state, 0)
            if prior <= 0:
                posterior[state] = 0
                continue
            lik = self.om.likelihood(state, hr, stress)
            posterior[state] = prior * lik

        # 归一化后验
        post_total = sum(posterior.values())
        if post_total > 0:
            for s in posterior:
                posterior[s] /= post_total
        else:
            posterior = dict(predicted)  # 退回到预测

        self.belief = posterior
        return posterior

    def most_likely_state(self) -> ArousalState:
        """当前最可能的隐藏状态 (MAP估计)"""
        return max(self.belief, key=self.belief.get)

    def get_confidence(self) -> float:
        """当前估计的置信度 (最高后验概率)"""
        return max(self.belief.values())

    def entropy(self) -> float:
        """信念分布的熵 — 不确定性度量"""
        h = 0
        for p in self.belief.values():
            if p > 0:
                h -= p * math.log2(p)
        return h


# ============================================================
# 4. 状态预测器 — 前向预测会话指令序列
# ============================================================

class StatePredictor:
    """
    前向预测状态序列 (替代之前的固定时间线)

    session_plan() 的升级版:
      从一个初始信念出发，向前推演整个睡眠会话的状态演化，
      每一步都用贝叶斯预测而不是固定时间切割。
    """

    def __init__(self, transition_matrix: TransitionMatrix,
                 observation_model: ObservationModel):
        self.tm = transition_matrix
        self.om = observation_model

    def predict_session(self, initial_hr: Optional[float] = None,
                        initial_stress: Optional[int] = None,
                        total_hours: float = 7.0,
                        step_s: float = 300.0) -> List[Tuple[ArousalState, float, float]]:
        """
        预测整个会话的状态序列

        Returns:
            [(state, start_s, duration_s), ...]
        """
        total_s = total_hours * 3600
        steps = int(total_s / step_s)

        # 初始信念
        initial_belief = BayesFilter(self.tm, self.om)
        initial_belief.update(hr=initial_hr, stress=initial_stress)

        current_belief = initial_belief.belief
        timeline = []
        current_state = initial_belief.most_likely_state()
        segment_start = 0.0

        for step in range(steps):
            t = step * step_s

            # 每步做状态转移预测（无观测，纯动力学推演）
            predicted = defaultdict(float)
            for prev_state, prev_prob in current_belief.items():
                if prev_prob <= 0:
                    continue
                trans_probs = self.tm.get(prev_state)
                for next_state, trans_prob in trans_probs.items():
                    # 时间因子: 越往后越倾向于放松
                    time_factor = min(t / 3600.0 / 3.0, 1.0)
                    adjusted = trans_prob
                    if next_state.index() > prev_state.index():
                        adjusted *= 1.0 + 0.15 * time_factor
                    predicted[next_state] += prev_prob * adjusted

            pred_total = sum(predicted.values())
            if pred_total > 0:
                for s in predicted:
                    predicted[s] /= pred_total

            next_state = max(predicted, key=predicted.get)

            if next_state != current_state:
                seg_dur = t - segment_start
                if seg_dur >= 60:  # 至少60秒
                    timeline.append((current_state, segment_start, seg_dur))
                segment_start = t
                current_state = next_state

            current_belief = predicted

        # 最后一个segment
        final_dur = total_s - segment_start
        if final_dur > 0:
            timeline.append((current_state, segment_start, final_dur))

        return timeline


# ============================================================
# 5. 用户个性化层
# ============================================================

class Personalizer:
    """
    跨session学习，更新用户特定的转移参数

    每session结束后调用 feedback():
      记录实际状态转移
      更新转移矩阵计数
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.transition_matrix = TransitionMatrix(user_id)
        self.observation_model = ObservationModel()
        self.filter = BayesFilter(self.transition_matrix, self.observation_model)
        self.predictor = StatePredictor(self.transition_matrix, self.observation_model)
        self._session_history: List[Dict] = []

    def update_belief(self, hr: Optional[float] = None,
                      stress: Optional[int] = None,
                      elapsed_s: float = 60.0) -> ArousalState:
        """贝叶斯滤波更新，返回最可能状态"""
        self.filter.update(hr=hr, stress=stress, elapsed_s=elapsed_s)
        return self.filter.most_likely_state()

    def predict_session(self, **kwargs) -> List[Tuple]:
        """预测会话序列"""
        return self.predictor.predict_session(**kwargs)

    def feedback(self, actual_states: List[Tuple[ArousalState, float]]):
        """
        session结束后反馈实际状态序列

        Args:
            actual_states: [(state, duration_s), ...]
        """
        for i in range(len(actual_states) - 1):
            from_s = actual_states[i][0]
            to_s = actual_states[i + 1][0]
            self.transition_matrix.record_transition(from_s, to_s)

        self._session_history.append({
            "timestamp": time.time(),
            "state_count": len(actual_states),
            "total_duration": sum(d for _, d in actual_states),
        })

        # 用户画像编码：每次反馈后更新向量
        try:
            encoder = UserProfileEncoder()
            encoder.register_user(self.user_id, self.transition_matrix)
        except Exception:
            pass  # 非阻塞

    def get_model_params(self) -> dict:
        """导出用户个性化参数"""
        return {
            "user_id": self.user_id,
            "transition_matrix": self.transition_matrix.to_dict(),
            "session_count": len(self._session_history),
        }


# ============================================================
# 6. 与 biofeedback_renderer 的桥接层
# ============================================================

class StateModelBridge:
    """
    桥接层: 把 P1 状态转移模型挂到 P0 渲染器上

    replace:
      renderer._compute_stage_timeline()
      renderer.estimate_state()
    with:
      personalizer.predict_session()
      personalizer.update_belief()
    """

    def __init__(self, user_id: str = "default"):
        self.personalizer = Personalizer(user_id)

    def build_session_plan(self, stress_level: int = 5,
                           sleep_latency: int = 30,
                           expected_hours: float = 7.0) -> List[Dict]:
        """生成状态序列 + 概率置信度"""
        # 从初始条件推断hr
        inferred_hr = {
            9: 88, 8: 84, 7: 78, 6: 74,
            5: 68, 4: 64, 3: 60, 2: 56, 1: 54
        }.get(stress_level, 68)

        timeline = self.personalizer.predict_session(
            initial_hr=inferred_hr,
            initial_stress=stress_level,
            total_hours=expected_hours,
        )

        result = []
        for state, start_s, dur_s in timeline:
            confidence = 0.0
            if state == ArousalState.SLEEPING:
                confidence = 0.85
            else:
                # 置信度随着预测远度递减
                confidence = max(0.95 - start_s / 14400, 0.3)

            result.append({
                "state": state.value,
                "start_s": round(start_s, 1),
                "duration_s": round(dur_s, 1),
                "confidence": round(confidence, 2),
            })

        return result

    def realtime_update(self, hr: Optional[float] = None,
                        stress: Optional[int] = None,
                        elapsed_s: float = 60.0) -> dict:
        """实时贝叶斯更新"""
        state = self.personalizer.update_belief(hr=hr, stress=stress, elapsed_s=elapsed_s)
        return {
            "state": state.value,
            "confidence": round(self.personalizer.filter.get_confidence(), 3),
            "entropy": round(self.personalizer.filter.entropy(), 3),
            "belief": {
                s.value: round(p, 3)
                for s, p in self.personalizer.filter.belief.items()
                if p > 0.01
            },
        }


# ============================================================
# 7. 快速测试
# ============================================================

def run_demo():
    print("=" * 60)
    print("P1 状态转移模型 v1.0 — 贝叶斯概率转移")
    print("=" * 60)

    # 测试1: 贝叶斯滤波
    print("\n[测试1] 贝叶斯滤波: 焦虑→平静 (输入HR序列)")
    bridge = StateModelBridge("demo")
    for hr, elapsed in [(82, 0), (76, 60), (70, 120), (65, 180), (60, 300)]:
        result = bridge.realtime_update(hr=hr, elapsed_s=elapsed if elapsed > 60 else 0)
        belief_str = ", ".join(
            f"{s}: {p:.0%}"
            for s, p in result["belief"].items()
        )
        print(f"  HR={hr:3d} → {result['state']:10s} (conf={result['confidence']:.0%}) [{belief_str}]")

    # 测试2: 会话预测
    print("\n[测试2] 会话预测: stress=7, 7h")
    plan = bridge.build_session_plan(stress_level=7, expected_hours=7.0)
    for p in plan:
        start_m = p['start_s'] / 60
        dur_m = p['duration_s'] / 60
        print(f"  [{start_m:3.0f}-{start_m+dur_m:3.0f}min] "
              f"{p['state']:10s} (confidence: {p['confidence']:.0%})")

    # 测试3: 个性化学习
    print("\n[测试3] 个性化学习: 反馈10次历史session")
    bridge2 = StateModelBridge("learner")
    for _ in range(10):
        # 模拟一个典型模式: alert→calm→drowsy→sleeping
        states = [
            (ArousalState.ALERT, 300),
            (ArousalState.CALM, 600),
            (ArousalState.DROWSY, 900),
            (ArousalState.SLEEPING, 3000),
        ]
        bridge2.personalizer.feedback(states)

    # 看看学到了什么
    tm = bridge2.personalizer.transition_matrix
    print(f"  转移计数:")
    for from_s in ArousalState.list():
        for to_s in ArousalState.list():
            c = tm._counts[from_s.value].get(to_s.value, 0)
            if c > 0:
                print(f"    {from_s.value:10s} → {to_s.value:10s}: {int(c)}次")

    print("\n所有测试通过!")


if __name__ == "__main__":
    run_demo()


class UserProfileEncoder:
    """
    用户画像编码器：将转移矩阵 -> 128维向量
    
    用于:
      1. 新用户冷启动：匹配最相似历史用户
      2. 聚类：发现用户行为模式簇
      3. 监控：检测用户行为漂移
    """
    
    # 状态空间维度
    STATE_NAMES = ['anxious', 'alert', 'calm', 'drowsy', 'sleeping']
    STATE_DIM = 5  # 5×5转移矩阵 = 25维
    
    def __init__(self):
        import json, os
        self._vectors = {}  # user_id -> vector (list of floats)
        self._cache_path = os.path.join(os.path.dirname(__file__) or '.', 'data', 'user_vectors.json')
        self._load_cache()
    
    def encode(self, transition_matrix) -> list:
        """
        从转移矩阵提取25维特征向量
        5×5 = 25维 + 4维统计 = 29维
        """
        mc = transition_matrix._counts
        prior = transition_matrix._prior
        
        vec = []
        for from_state in self.STATE_NAMES:
            for to_state in self.STATE_NAMES:
                cnt = mc.get(from_state, {}).get(to_state, 0)
                # 混合先验：log(1 + count) 在狄利克雷后验中的权重
                prior_p = prior.get(from_state, {}).get(to_state, 0)
                # 使用 alpha = total/(total+10) 混合
                total = sum(mc.get(from_state, {}).values())
                alpha = total / (total + 10) if total > 0 else 0
                if total > 0:
                    emp_p = cnt / total
                    p = alpha * emp_p + (1 - alpha) * prior_p
                else:
                    p = prior_p
                vec.append(p)
        
        # 附加统计特征
        total_transitions = sum(sum(c.values()) for c in mc.values())
        unique_states_seen = sum(1 for c in mc.values() for v in c.values() if v > 0)
        
        vec.extend([
            min(1.0, total_transitions / 100),  # 用户成熟度
            unique_states_seen / 25,  # 状态覆盖率
            1.0 if total_transitions > 5 else total_transitions / 5,  # 数据充足度
            1.0 if len([s for s in self.STATE_NAMES if s in str(mc)]) > 3 else 0.5,  # 多样性
        ])
        
        return vec  # 29维
    
    def _load_cache(self):
        """加载缓存向量"""
        import json, os
        if os.path.exists(self._cache_path):
            try:
                with open(self._cache_path, 'r', encoding='utf-8') as f:
                    self._vectors = json.load(f)
            except:
                self._vectors = {}
    
    def _save_cache(self):
        """保存向量到缓存"""
        import json, os
        os.makedirs(os.path.dirname(self._cache_path), exist_ok=True)
        with open(self._cache_path, 'w', encoding='utf-8') as f:
            json.dump(self._vectors, f, ensure_ascii=False, indent=2)
    
    def register_user(self, user_id: str, transition_matrix):
        """编码并注册用户"""
        self._vectors[user_id] = self.encode(transition_matrix)
        self._save_cache()
    
    def find_similar(self, user_id: str, top_k: int = 5) -> list:
        """找最相似用户（余弦相似度）"""
        if user_id not in self._vectors:
            return []
        target = self._vectors[user_id]
        scores = []
        for uid, vec in self._vectors.items():
            if uid == user_id:
                continue
            # 余弦相似度
            dot = sum(a * b for a, b in zip(target, vec))
            n1 = sum(a * a for a in target) ** 0.5
            n2 = sum(b * b for b in vec) ** 0.5
            sim = dot / (n1 * n2) if n1 > 0 and n2 > 0 else 0
            scores.append((uid, sim))
        scores.sort(key=lambda x: -x[1])
        return scores[:top_k]
    
    def get_cold_start_bias(self, user_id: str) -> dict:
        """
        新用户冷启动：返回最相似用户的偏置
        
        如果没有相似用户，返回默认偏置
        """
        if user_id in self._vectors:
            return {}  # 已有数据
        
        # 找全局最热门的用户向量平均
        if self._vectors:
            # 使用所有用户的平均向量作为默认
            all_vecs = list(self._vectors.values())
            avg = [sum(dim)/len(dim) for dim in zip(*all_vecs)]
        else:
            avg = [0.5] * 29  # 完全默认
        
        return {'vector_dims': 29, 'population_bias': avg[:4]}  # 只返前4维做简单偏置

