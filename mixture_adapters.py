#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mixture_adapters.py — Mixture of Adapters 混合适配器 (v7.5+)
原理: Google MoA — 每用户/每场景一个轻量化适配器，控制专家混合权重
落地: 为每位用户学习"专家混合比例"的适配器向量

用法:
  from mixture_adapters import get_adapter, update_adapter, adapter_summary
  weights = get_adapter('user123')  # 返回 {expert: weight}
  update_adapter('user123', 'CBT', +0.1)
"""

import json, os, math
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ADAPTER_DIR = os.path.join(PROJECT_ROOT, 'data', 'adapters')
os.makedirs(ADAPTER_DIR, exist_ok=True)

# 10位专家的默认适配器向量
DEFAULT_ADAPTER = {
    'ClinicalPsychologist': 1.0,
    'CBT': 1.0,
    'SleepPhysician': 1.0,
    'Chronobiologist': 1.0,
    'LifeScientist': 1.0,
    'RiskManager': 1.0,
    'StressRelaxation': 1.0,
    'ExerciseRehab': 1.0,
    'CardiacMonitor': 1.0,
    'NutriMetabolism': 1.0,
}

EXPERT_SPECIALTIES = {
    'ClinicalPsychologist': '心理评估',
    'CBT': '失眠干预',
    'SleepPhysician': '睡眠筛查',
    'Chronobiologist': '节律分析',
    'LifeScientist': '综合分析',
    'RiskManager': '风险管控',
    'StressRelaxation': '减压评估',
    'ExerciseRehab': '运动分析',
    'CardiacMonitor': '心血管',
    'NutriMetabolism': '营养分析',
}


def _user_path(openid):
    safe = openid.replace('/', '_').replace('\\', '_')
    return os.path.join(ADAPTER_DIR, '%s.json' % safe)


def _load(openid):
    path = _user_path(openid)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'adapter': dict(DEFAULT_ADAPTER), 'updates': 0}


def _save(openid, data):
    with open(_user_path(openid), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_adapter(openid):
    """获取用户的适配器向量

    Returns: dict {expert_name: float_weight}
    """
    if not openid:
        return dict(DEFAULT_ADAPTER)
    data = _load(openid)
    return data.get('adapter', dict(DEFAULT_ADAPTER))


def update_adapter(openid, expert_name, delta):
    """更新某个专家的适配器权重

    Args:
        openid: str
        expert_name: str
        delta: float — 调整量
    """
    if not openid or not expert_name:
        return

    data = _load(openid)
    adapter = data.get('adapter', dict(DEFAULT_ADAPTER))

    old = adapter.get(expert_name, 1.0)
    new = max(0.1, min(2.0, old + delta))
    adapter[expert_name] = round(new, 3)

    data['adapter'] = adapter
    data['updates'] += 1
    _save(openid, data)


def update_adapter_multi(openid, deltas):
    """批量更新多个专家的适配器

    Args:
        openid: str
        deltas: dict {expert_name: delta}
    """
    if not openid:
        return
    data = _load(openid)
    adapter = data.get('adapter', dict(DEFAULT_ADAPTER))

    for name, delta in deltas.items():
        old = adapter.get(name, 1.0)
        new = max(0.1, min(2.0, old + delta))
        adapter[name] = round(new, 3)

    data['adapter'] = adapter
    data['updates'] += len(deltas)
    _save(openid, data)


def apply_adapter(openid, expert_scores):
    """用适配器向量调整专家评分

    Args:
        openid: str
        expert_scores: dict {expert_name: score}

    Returns:
        dict {expert_name: adjusted_score}
    """
    adapter = get_adapter(openid)
    adjusted = {}
    for name, score in expert_scores.items():
        w = adapter.get(name, 1.0)
        # 适配器权重影响: 1.0不变, >1.0推高, <1.0压低
        adjusted_score = 0.5 + (score - 0.5) * w
        adjusted[name] = max(0.05, min(0.95, round(adjusted_score, 3)))
    return adjusted


def adapter_summary(openid):
    """适配器摘要"""
    adapter = get_adapter(openid)
    data = _load(openid)
    # 找出偏离最大的专家
    deviations = [(n, round(v - 1.0, 2)) for n, v in adapter.items() if abs(v - 1.0) > 0.05]
    deviations.sort(key=lambda x: -abs(x[1]))
    return {
        'updates': data.get('updates', 0),
        'deviations': deviations[:5],
        'top_boosted': deviations[0][0] if deviations and deviations[0][1] > 0 else None,
        'top_reduced': deviations[-1][0] if deviations and deviations[-1][1] < 0 else None,
    }


# ===== 自测 =====
if __name__ == '__main__':
    print('=== Mixture of Adapters Test ===\n')

    # 默认适配器
    adapter = get_adapter('test_moa')
    print('Test 1 (default): %d experts, CBT=%.1f' % (len(adapter), adapter.get('CBT', 0)))
    assert len(adapter) == 10
    assert adapter['CBT'] == 1.0

    # 更新
    update_adapter('test_moa', 'CBT', 0.3)
    adapter = get_adapter('test_moa')
    print('Test 2 (update): CBT=%.2f' % adapter['CBT'])
    assert adapter['CBT'] == 1.3

    # 批量更新
    update_adapter_multi('test_moa', {'CBT': -0.2, 'RiskManager': 0.5, 'StressRelaxation': -0.3})
    adapter = get_adapter('test_moa')
    print('Test 3 (multi): CBT=%.2f, RM=%.2f, SR=%.2f' % (
        adapter['CBT'], adapter['RiskManager'], adapter['StressRelaxation']))
    assert adapter['CBT'] == 1.1
    assert adapter['RiskManager'] == 1.5

    # 应用适配器
    scores = {'CBT': 0.5, 'RiskManager': 0.5, 'ClinicalPsychologist': 0.7}
    adjusted = apply_adapter('test_moa', scores)
    print('Test 4 (apply): CBT=%.2f, RM=%.2f, CP=%.2f' % (
        adjusted['CBT'], adjusted['RiskManager'], adjusted['ClinicalPsychologist']))
    assert 0.05 <= adjusted['CBT'] <= 0.95

    # 摘要
    sm = adapter_summary('test_moa')
    print('Test 5 (summary): updates=%d, top=%s' % (sm['updates'], sm['top_boosted']))
    assert sm['updates'] >= 4

    # 清理
    import os as _os
    _p = os.path.join(ADAPTER_DIR, 'test_moa.json')
    if _os.path.exists(_p):
        _os.remove(_p)

    print('\nAll tests passed!')
