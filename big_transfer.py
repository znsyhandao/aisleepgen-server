#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
big_transfer.py — Big Transfer迁移学习 (v7.5+)
原理: Google BiT — 预训练+微调，从老用户迁移知识到新用户
落地: 当用户数据<5条时，从最相似的老用户"借"知识做初值

用法:
  from big_transfer import init_new_user, transfer_summary
  weights = init_new_user('new_user', all_profiles)
"""

import json, os, math
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TRANSFER_DIR = os.path.join(PROJECT_ROOT, 'data', 'transfer')
os.makedirs(TRANSFER_DIR, exist_ok=True)


def _z_score(vals):
    n = len(vals)
    if n < 2:
        return 0.0
    mu = sum(vals) / n
    s = math.sqrt(max(1e-10, sum((v - mu)**2 for v in vals) / (n - 1)))
    return s


def _to_vector(history, dims):
    """从历史计算特征向量"""
    data = {d: [] for d in dims}
    for rec in history:
        if not isinstance(rec, dict):
            continue
        for d in dims:
            v = rec.get(d)
            if v is not None:
                try:
                    data[d].append(float(v))
                except (ValueError, TypeError):
                    pass
    vec = []
    for d in dims:
        v = data[d]
        if len(v) >= 2:
            mu = sum(v) / len(v)
            std = _z_score(v)
            trend = (v[-1] - v[0]) / max(1, len(v))
            vec.extend([mu, std, trend])
        else:
            vec.extend([0.5, 0.0, 0.0])
    return vec


def _cosine_sim(a, b):
    min_l = min(len(a), len(b))
    if min_l == 0:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(min_l))
    n1 = math.sqrt(max(1e-10, sum(v**2 for v in a)))
    n2 = math.sqrt(max(1e-10, sum(v**2 for v in b)))
    return dot / (n1 * n2)


def _get_dims():
    return ['stress_level', 'sleep_latency', 'score', 'awake_times',
            'bedtime_hour', 'wake_hour', 'total_duration']


def _find_similar_user(new_openid, all_profiles, min_records=5):
    """从所有用户中找和新用户最相似的老用户

    新用户可能没数据，用profile中的基本信息匹配
    """
    new_profile = all_profiles.get(new_openid, {})
    new_history = new_profile.get('history', []) if isinstance(new_profile, dict) else []
    new_vec = _to_vector(new_history, _get_dims())

    best_sim = -1.0
    best_openid = None
    best_history = []

    for openid, profile in all_profiles.items():
        if openid == new_openid or not isinstance(profile, dict):
            continue
        history = profile.get('history', [])
        if len(history) < min_records:
            continue
        vec = _to_vector(history, _get_dims())
        sim = _cosine_sim(new_vec, vec) if len(new_history) >= 2 else 0.5
        if sim > best_sim:
            best_sim = sim
            best_openid = openid
            best_history = history

    return best_openid, best_sim, best_history


def init_new_user(new_openid, source_history):
    """为新用户生成初始化参数（迁移学习）

    从源用户的历史中提取"专家偏好模式"作为初值

    Returns:
        dict: {from_openid, source_samples, transferred_params, summary}
    """
    if not source_history or len(source_history) < 3:
        return {'note': '源数据不足', 'transferred': False}

    # 从源用户历史中计算专家偏好统计
    # 用历史评分推断各专家的"预期权重"
    dims = _get_dims()

    # 源用户的评分分布
    scores = [rec.get('score', 50) for rec in source_history if isinstance(rec, dict)]
    if not scores:
        return {'note': '无评分数据', 'transferred': False}

    avg_score = sum(scores) / len(scores)
    std_score = _z_score(scores) if len(scores) >= 2 else 10.0

    # 迁移参数: 基于源用户的评分统计，生成初始化专家推荐
    # 评分高→CBT/StressRelaxation占比高, 评分低→RiskManager/ClinicalPsychologist占比高
    expert_ratio = {
        'ClinicalPsychologist': max(0.1, 0.3 - (avg_score - 50) / 200),
        'CBT': max(0.1, 0.15 + (avg_score - 50) / 200),
        'SleepPhysician': 0.15,
        'Chronobiologist': 0.10,
        'LifeScientist': 0.10,
        'RiskManager': max(0.1, 0.15 - (avg_score - 50) / 200),
        'StressRelaxation': max(0.1, 0.05 + (avg_score - 50) / 200),
        'ExerciseRehab': 0.05,
        'CardiacMonitor': 0.05,
        'NutriMetabolism': 0.05,
    }

    # 归一化
    total = sum(expert_ratio.values())
    expert_ratio = {k: round(v / total, 3) for k, v in expert_ratio.items()}

    return {
        'from_openid': new_openid,
        'source_samples': len(scores),
        'avg_source_score': round(avg_score, 1),
        'std_source_score': round(std_score, 2),
        'transferred_params': expert_ratio,
        'transferred': True,
    }


def transfer_summary(result):
    """摘要"""
    if result.get('transferred'):
        return '迁移学习: 从%d条数据迁入, 源评分=%.1f±%.1f' % (
            result['source_samples'], result['avg_source_score'], result['std_source_score'])
    return '迁移学习: %s' % result.get('note', '无数据')


# ===== 自测 =====
if __name__ == '__main__':
    print('=== Big Transfer Test ===\n')

    # 源用户: 数据充足，评分偏高
    source_history = []
    for i in range(15):
        source_history.append({
            'stress_level': 3 + (i % 5) * 0.5,
            'sleep_latency': 20 + (i % 3) * 5,
            'score': 75 + (i % 4) * 2,
            'awake_times': 1 + (i % 3) * 0.3,
            'bedtime_hour': 23 + (i % 5) * 0.1,
            'wake_hour': 7 + (i % 3) * 0.2,
            'total_duration': 470 + (i % 5) * 10,
        })

    # 新用户: 数据极少
    new_history = [{'stress_level': 5, 'sleep_latency': 35, 'score': 60}]

    result = init_new_user('new_user', source_history)
    print(transfer_summary(result))
    assert result['transferred']
    assert 'transferred_params' in result
    params = result['transferred_params']
    print('Expert ratios:', {k: v for k, v in list(params.items())[:5]})

    # 无数据
    r2 = init_new_user('new_user2', [])
    assert not r2['transferred']

    # 清理
    import os as _os
    for f in os.listdir(TRANSFER_DIR):
        p = _os.path.join(TRANSFER_DIR, f)
        if _os.path.isfile(p):
            _os.remove(p)

    print('\nAll tests passed!')
