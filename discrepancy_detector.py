#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
discrepancy_detector.py — 评分异常检测器 v1.0

轻量级 z-score 检测器，检测用户评分与自身基线的偏差。
检测到异常后，在 POMDP 观测中注入一个"异常标记"，让信念更新走不同路径。

设计原则：
  - 纯规则引擎，<1ms
  - 无状态：每次调用只读 profile['history']
  - 无侵入：输出 dict，由 caller 决定怎么消费

输出:
  - has_discrepancy: bool
  - direction: 'spike_up' | 'spike_down' | 'volatile' | 'stable'
  - z_score: float
  - baseline: float
  - recent_avg: float
  - severity: 'normal' | 'notice' | 'warning' | 'critical'
"""

import math, logging
from datetime import datetime, timedelta

_ld_log = logging.getLogger('aisleepgen.discrepancy')

RECENT_WINDOW = 5   # 最近N次作为"近期窗口"
BASELINE_WINDOW = 14  # 过去N天作为基线


def detect(openid, current_score, profile):
    """检测评分异常

    Args:
        openid: 用户标识
        current_score: 当前评分 (0-100)
        profile: 用户画像

    Returns:
        dict:
            has_discrepancy: bool
            direction: str
            z_score: float  (标准分，|z|>2 显著异常)
            recent_avg: float
            baseline: float
            severity: str
            history_len: int
    """
    # 安全钳制：容错None/错误的profile格式
    if profile is None or not isinstance(profile, dict):
        _ld_log.warning('[Disc] %s: invalid profile, returning safe default', openid[:8])
        return {'has_discrepancy': False, 'direction': 'stable', 'z_score': 0.0,
                'recent_avg': current_score or 50, 'baseline': current_score or 50,
                'severity': 'normal', 'history_len': 0}
    history = profile.get('history', [])
    if not isinstance(history, list):
        history = []

    # 提取近期的评分序列
    scores = _extract_score_sequence(history)

    if len(scores) < 3:
        # 数据太少，无法判断异常
        return {
            'has_discrepancy': False,
            'direction': 'stable',
            'z_score': 0.0,
            'recent_avg': current_score,
            'baseline': current_score,
            'severity': 'normal',
            'history_len': len(scores),
        }

    # 计算基线（历史均值）
    baseline_scores = scores[-BASELINE_WINDOW:] if len(scores) > BASELINE_WINDOW else scores
    baseline = sum(baseline_scores) / len(baseline_scores)

    # 计算标准差
    if len(baseline_scores) > 1:
        variance = sum((s - baseline) ** 2 for s in baseline_scores) / (len(baseline_scores) - 1)
        std = math.sqrt(variance) if variance > 0 else 5.0  # 最小标准差5分
    else:
        std = 10.0  # 默认

    # z-score
    z_score = (current_score - baseline) / std if std > 0 else 0.0

    # 近期平均值（滑动窗口）
    recent = scores[-RECENT_WINDOW:] if len(scores) > RECENT_WINDOW else scores
    recent_avg = sum(recent) / len(recent)

    # 方向
    if z_score > 2.0:
        direction = 'spike_up'
    elif z_score < -2.0:
        direction = 'spike_down'
    elif z_score > 1.0 or z_score < -1.0:
        direction = 'volatile' if len(scores) > 5 and _is_volatile(scores[-5:], std) else 'stable'
    else:
        direction = 'stable'

    # 严重程度
    abs_z = abs(z_score)
    if abs_z >= 3.0:
        severity = 'critical'
    elif abs_z >= 2.0:
        severity = 'warning'
    elif abs_z >= 1.0:
        severity = 'notice'
    else:
        severity = 'normal'

    return {
        'has_discrepancy': abs_z >= 2.0,
        'direction': direction,
        'z_score': round(z_score, 2),
        'recent_avg': round(recent_avg, 1),
        'baseline': round(baseline, 1),
        'severity': severity,
        'history_len': len(scores),
    }


def _extract_score_sequence(history):
    """从history中提取有序评分列表"""
    scores = []
    for h in history:
        if isinstance(h, dict):
            s = h.get('total_score') or h.get('wm_score') or 0
        elif isinstance(h, (int, float)):
            s = h
        else:
            continue
        if isinstance(s, (int, float)) and 0 < s <= 100:
            scores.append(s)
    return scores


def _is_volatile(recent_scores, std):
    """检测近期评分是否异常波动（相邻评分变化过大）"""
    if len(recent_scores) < 3:
        return False
    jumps = [abs(recent_scores[i] - recent_scores[i-1]) for i in range(1, len(recent_scores))]
    avg_jump = sum(jumps) / len(jumps)
    return avg_jump > 2.0 * std


# ==================== 自测 ====================

def _test():
    print('=== Discrepancy Detector Self-Test ===\n')

    # 1. 稳定用户
    p1 = {'history': [{'total_score': 78}, {'total_score': 82}, {'total_score': 80},
                      {'total_score': 79}, {'total_score': 81}]}
    r1 = detect('_t1', 79, p1)
    print('1. Stable user (79 vs baseline ~80):')
    print('   has_discrepancy=%s, direction=%s, z=%.2f, sev=%s' %
          (r1['has_discrepancy'], r1['direction'], r1['z_score'], r1['severity']))
    assert not r1['has_discrepancy']

    # 2. 回弹下降
    p2 = {'history': [{'total_score': 80}, {'total_score': 82}, {'total_score': 79},
                      {'total_score': 78}, {'total_score': 81}]}
    r2 = detect('_t2', 35, p2)
    print('2. Spike down (80->35):')
    print('   has_discrepancy=%s, direction=%s, z=%.2f, sev=%s' %
          (r2['has_discrepancy'], r2['direction'], r2['z_score'], r2['severity']))
    assert r2['has_discrepancy']
    assert r2['direction'] == 'spike_down'

    # 3. 逐步下降（非突变）
    p3 = {'history': [{'total_score': 78}, {'total_score': 75}, {'total_score': 70},
                      {'total_score': 68}, {'total_score': 65}]}
    r3 = detect('_t3', 62, p3)
    print('3. Gradual decline (78->62, no spike):')
    print('   has_discrepancy=%s, direction=%s, z=%.2f, sev=%s' %
          (r3['has_discrepancy'], r3['direction'], r3['z_score'], r3['severity']))
    # gradual decline shouldn't trigger |z|>2 unless delta is huge
    # 62 vs baseline ~71: z = (62-71)/5.3 ≈ -1.7 → 'notice'

    # 4. 新用户，数据太少
    p4 = {'history': [{'total_score': 75}]}
    r4 = detect('_t4', 80, p4)
    print('4. New user (only 1 history entry):')
    print('   has_discrepancy=%s, severity=%s' % (r4['has_discrepancy'], r4['severity']))
    assert not r4['has_discrepancy']

    # 5. 回弹上升
    p5 = {'history': [{'total_score': 35}, {'total_score': 38}, {'total_score': 40},
                      {'total_score': 36}, {'total_score': 37}]}
    r5 = detect('_t5', 85, p5)
    print('5. Spike up (35->85):')
    print('   has_discrepancy=%s, direction=%s, z=%.2f, sev=%s' %
          (r5['has_discrepancy'], r5['direction'], r5['z_score'], r5['severity']))
    assert r5['has_discrepancy']
    assert r5['direction'] == 'spike_up'

    print('\nAll %s tests PASS' % 5)


if __name__ == '__main__':
    _test()

# ============================================================
# 世界模型一致性检查 (由 world_model_coordinator 调用)
# ============================================================

class WorldStateValidator:
    """
    WorldState 逻辑一致性验证器

    检查规则:
      1. 觉醒状态和睡眠阶段不能矛盾 (anxious + N3 = 不可能)
      2. 心率在合理范围内
      3. 渲染参数与状态一致
      4. 置信度与熵的数学关系
    """

    # 觉醒状态 ↔ 睡眠阶段 相容性矩阵
    COMPATIBLE = {
        "anxious":  ["wake"],
        "alert":    ["wake", "n1"],
        "calm":     ["wake", "n1", "n2"],
        "drowsy":   ["n1", "n2", "rem"],
        "sleeping": ["n2", "n3", "rem"],
    }

    @classmethod
    def validate_input(cls, hr=None, stress=None) -> dict:
        """验证输入数据一致性"""
        errors = []
        warnings = []

        if hr is not None:
            if hr < 30 or hr > 220:
                errors.append(f"心率异常: {hr}")
            elif hr < 40 or hr > 180:
                warnings.append(f"心率可疑: {hr}")

        if stress is not None:
            if stress < 1 or stress > 10:
                errors.append(f"压力值越界: {stress}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    @classmethod
    def check_world_state(cls, state: dict) -> dict:
        """验证 WorldState 的内部逻辑一致性"""
        errors = []
        warnings = []

        arousal = state.get("arousal", {}).get("state", "")
        sleep = state.get("sleep", {})
        phase = sleep.get("phase", "wake")
        hr = state.get("physiology", {}).get("hr")

        # 规则1: 觉醒状态和睡眠阶段必须相容
        compatible_phases = cls.COMPATIBLE.get(arousal, [])
        if phase and phase not in compatible_phases:
            errors.append(
                f"逻辑矛盾: 觉醒={arousal} 但睡眠阶段={phase}"
            )

        # 规则2: 置信度和熵的关系
        confidence = state.get("arousal", {}).get("confidence", 0)
        entropy = state.get("arousal", {}).get("entropy", 0)
        if confidence > 0.9 and entropy > 1.0:
            warnings.append(
                f"置信度({confidence:.2f})与熵({entropy:.2f})不匹配"
            )

        # 规则3: 渲染参数合理性
        tempo = state.get("render", {}).get("tempo_bpm", 6)
        if tempo < 2 or tempo > 12:
            warnings.append(f"呼吸节奏越界: {tempo}bpm")

        return {
            "consistent": len(errors) == 0,
            "checks": 3,
            "errors": errors,
            "warnings": warnings,
        }


def check_world_state(state: dict) -> dict:
    """快捷入口"""
    return WorldStateValidator.check_world_state(state)


def validate_input(hr=None, stress=None) -> dict:
    """快捷入口"""
    return WorldStateValidator.validate_input(hr, stress)
