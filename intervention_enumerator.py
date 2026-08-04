#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
干预策略枚举器 v1.0 — 给世界模型的"想象引擎"喂候选干预

功能:
  给定当前 WorldState，生成 3-5 种候选干预动作
  每种候选附带"历史成功率"(从 PerceptionGraph 查)
  用于 coordinator.step() 末尾的"如果A vs 如果B"推演

架构:
  PerceptionGraph ——→ 候选排序 (历史成功率影响排序)
       ↑                        |
  用户历史行为 ←——— 枚举器输出候选列表
       |                        ↓
  coordinator.step()  ———→ 推演评估器选最优
"""

import json
import os
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


# ============================================================
# 干预动作定义
# ============================================================

INTERVENTION_CATALOG = {
    "breath_4_7_8": {
        "name": "4-7-8 呼吸法",
        "category": "breathing",
        "tempo_bpm": 5.5,
        "breathing_in_s": 4.0,
        "breathing_out_s": 8.0,
        "text_speed": 0.72,
        "silence_s": 5.0,
        "volume_db": -3.0,
        "energy_cost": "low",       # 用户需要配合的程度
        "suitable_arousal": ["anxious", "alert"],
    },
    "breath_box": {
        "name": "箱式呼吸",
        "category": "breathing",
        "tempo_bpm": 6.0,
        "breathing_in_s": 4.0,
        "breathing_out_s": 4.0,
        "text_speed": 0.78,
        "silence_s": 4.0,
        "volume_db": -2.0,
        "energy_cost": "low",
        "suitable_arousal": ["alert", "calm"],
    },
    "rain_sound": {
        "name": "雨声白噪音",
        "category": "audio",
        "tempo_bpm": 6.0,
        "volume_db": -4.0,
        "silence_s": 999,           # 纯音频，无引导语
        "modulation_hz": 0.08,
        "modulation_depth": 0.2,
        "envelope": "sine",
        "energy_cost": "none",      # 被动收听
        "suitable_arousal": ["anxious", "alert", "calm", "drowsy"],
    },
    "stream_sound": {
        "name": "溪流声",
        "category": "audio",
        "tempo_bpm": 6.0,
        "volume_db": -3.0,
        "silence_s": 999,
        "modulation_hz": 0.12,
        "modulation_depth": 0.15,
        "envelope": "plateau",
        "energy_cost": "none",
        "suitable_arousal": ["calm", "drowsy"],
    },
    "progressive_relaxation": {
        "name": "渐进式肌肉放松引导",
        "category": "guided",
        "tempo_bpm": 4.0,
        "text_speed": 0.65,
        "silence_s": 6.0,
        "volume_db": -3.0,
        "energy_cost": "medium",
        "suitable_arousal": ["anxious", "alert"],
    },
    "cool_down": {
        "name": "室温降低引导",
        "category": "environment",
        "tempo_bpm": 6.0,
        "volume_db": -2.0,
        "silence_s": 3.0,
        "energy_cost": "none",
        "suitable_arousal": ["alert", "calm", "drowsy"],
        "iot_action": {"device": "ac", "target_temp_delta": -0.5},
    },
    "do_nothing": {
        "name": "继续观察（基线）",
        "category": "monitor",
        "tempo_bpm": 0,
        "volume_db": -10.0,
        "silence_s": 999,
        "energy_cost": "none",
        "suitable_arousal": ["drowsy", "sleeping", "calm"],
    },
}


@dataclass
class InterventionCandidate:
    """一个候选干预动作"""
    action_id: str                  # 对应 INTERVENTION_CATALOG 的 key
    score: float = 0.0             # 综合得分（由枚举器评分）
    history_success_rate: float = 0.0  # PerceptionGraph 查到的历史成功率
    confidence: float = 0.0         # 推荐置信度

    def to_dict(self) -> dict:
        meta = INTERVENTION_CATALOG.get(self.action_id, {})
        return {
            "id": self.action_id,
            "name": meta.get("name", self.action_id),
            "category": meta.get("category", "unknown"),
            "score": round(self.score, 3),
            "energy_cost": meta.get("energy_cost", "low"),
            "success_rate": round(self.history_success_rate, 3),
            "confidence": round(self.confidence, 3),
            "render": {
                "tempo_bpm": meta.get("tempo_bpm", 6.0),
                "volume_db": meta.get("volume_db", -2.0),
                "silence_s": meta.get("silence_s", 3.0),
                "breathing": {
                    "in_s": meta.get("breathing_in_s", 4.0),
                    "out_s": meta.get("breathing_out_s", 8.0),
                },
                "audio": meta.get("category") == "audio",
            },
        }


class InterventionEnumerator:
    """
    干预策略枚举器

    输入: 当前 WorldState (从 coordinator.step() 拿到)
    处理: 过滤不符合当前状态的干预 → 排序 → 输出 Top-3
    输出: [InterventionCandidate, ...]
    """

    def __init__(self, perception_graph=None):
        self._pg = perception_graph

    def enumerate(self, world_state_dict: Dict, top_k: int = 3) -> List[InterventionCandidate]:
        """
        枚举 Top-K 候选干预

        Args:
            world_state_dict: coordinator.step() 返回的 WorldState.to_dict()
            top_k: 返回前几个候选

        Returns:
            按 score 降序排列的候选列表
        """
        arousal = world_state_dict.get("arousal", {}).get("state", "calm")
        sleep_phase = world_state_dict.get("sleep", {}).get("phase", "wake")

        # 过滤：根据睡眠阶段限制干预类型
        # n1(浅睡): 可以用被动式干预(白噪声/降温)
        # n3/rem(深睡/快速眼动): 只留 do_nothing
        # wake: 全部候选
        deep_sleep_phases = ("n2", "n3", "rem")
        light_sleep_phases = ("n1",)

        candidates = []
        for action_id, meta in INTERVENTION_CATALOG.items():
            if arousal not in meta.get("suitable_arousal", []):
                continue
            if sleep_phase in deep_sleep_phases and action_id != "do_nothing":
                continue
            # n1阶段只保留被动式干预（audio/environment）和 do_nothing
            if sleep_phase in light_sleep_phases:
                cat = meta.get("category", "")
                if action_id != "do_nothing" and cat not in ("audio", "environment", "monitor"):
                    continue
            cand = InterventionCandidate(action_id=action_id)
            # 查历史成功率 (从PerceptionGraph)
            if self._pg and hasattr(self._pg, 'get_intervention_rate'):
                try:
                    sr = self._pg.get_intervention_rate(action_id, arousal_state=arousal)
                    cand.history_success_rate = sr
                except Exception:
                    pass
            candidates.append(cand)

        # 评分：历史成功率 + 能量成本权重 + 置信度
        energy_weights = {"none": 1.5, "low": 1.0, "medium": 0.5}
        for cand in candidates:
            meta = INTERVENTION_CATALOG.get(cand.action_id, {})
            # 有历史数据：用真实成功率；无历史数据：回退到默认 0.5
            rate_score = cand.history_success_rate if cand.history_success_rate > 0.0 else (
                0.5 if cand.history_success_rate == 0.0 else 0.0
            )
            energy_w = energy_weights.get(meta.get("energy_cost", "low"), 1.0)
            cand.score = rate_score * energy_w
            cand.confidence = min(0.3 + (cand.history_success_rate * 0.5 if cand.history_success_rate > 0 else 0.2), 0.95)

        # 排序 → 取 Top-K
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:top_k]

    def to_candidates_dict(self, world_state_dict: Dict, top_k: int = 3) -> List[Dict]:
        """直接输出 dict 列表，供 API 返回"""
        return [c.to_dict() for c in self.enumerate(world_state_dict, top_k)]


# ============================================================
# 集成点 — 嵌入 coordinator.step()
# ============================================================

def inject_into_coordinator_step(coordinator, tracer=None):
    """
    钩子函数：在 coordinator.step() 返回前插入
    
    用法:
        from intervention_enumerator import inject_into_coordinator_step
        # 在 coordinator.step() 末尾:
        candidates = inject_into_coordinator_step(self, tracer)
        result_dict["intervention_candidates"] = candidates
    """
    enumerator = getattr(coordinator, '_enumerator', None)
    if enumerator is None:
        try:
            pg = getattr(coordinator, '_perception_graph', None) or getattr(coordinator, '_memory', None)
            enumerator = InterventionEnumerator(perception_graph=pg)
            coordinator._enumerator = enumerator
        except Exception:
            enumerator = InterventionEnumerator()

    state = coordinator.state.to_dict() if hasattr(coordinator.state, 'to_dict') else {}
    candidates = enumerator.to_candidates_dict(state, top_k=3)

    if tracer and candidates:
        tracer.add_layer("intervention_enumerator", {
            "candidates": [c["id"] for c in candidates],
            "top_score": candidates[0]["score"] if candidates else 0,
        })

    return candidates


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    # 模拟一个 WorldState
    mock_state = {
        "physiology": {"hr": 72, "hrv": 45, "stress": 6, "movement": 2},
        "arousal": {"state": "alert", "confidence": 0.7},
        "sleep": {"phase": "wake", "latency_min": 20},
        "render": {"tempo_bpm": 5.0, "volume_db": -2.0},
    }

    enum = InterventionEnumerator()
    candidates = enum.enumerate(mock_state, top_k=4)
    print(f"Arousal=alert → 候选干预 ({len(candidates)}):")
    for c in candidates:
        print(f"  [{c.score:.3f}] {c.action_id} (历史成功率={c.history_success_rate})")

    # 测试已睡着状态
    mock_sleep = {
        "physiology": {"hr": 58, "hrv": 62, "stress": 2, "movement": 0},
        "arousal": {"state": "sleeping", "confidence": 0.9},
        "sleep": {"phase": "n3", "latency_min": 0},
        "render": {"tempo_bpm": 0, "volume_db": -10.0},
    }
    candidates2 = enum.enumerate(mock_sleep, top_k=3)
    print(f"\nArousal=sleeping → 候选干预 ({len(candidates2)}):")
    for c in candidates2:
        print(f"  [{c.score:.3f}] {c.action_id}")
