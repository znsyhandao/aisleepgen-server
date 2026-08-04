#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dpo_preference.py — DPO偏好对齐 (v7.5+)
原理: Anthropic DPO (Direct Preference Optimization) — 直接从偏好对比中学习
落地: 从用户反馈中学习"什么类型的回复该提升，什么该降低"

区别于RLAIF: RLAIF从rating自动调整专家权重
DPO从对比对(正/负样本)中学习偏好方向

用法:
  from dpo_preference import record_preference, get_dpo_bias, dpo_summary
  record_preference(openid, preferred_expert, rejected_expert)
  bias = get_dpo_bias(openid, 'CBT')
"""

import json, os, math, time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DPO_DIR = os.path.join(PROJECT_ROOT, 'data', 'dpo')
os.makedirs(DPO_DIR, exist_ok=True)

_DPO_LR = 0.1  # 学习率


def _user_path(openid):
    safe = openid.replace('/', '_').replace('\\', '_')
    return os.path.join(DPO_DIR, '%s.json' % safe)


def _load_user(openid):
    path = _user_path(openid)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'probs': {}, 'pairs': 0}


def _save_user(openid, data):
    with open(_user_path(openid), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def record_preference(openid, preferred_expert, rejected_expert=None, preferred_type=None, rejected_type=None):
    """记录用户偏好对比

    DPO核心: 在对比对中提升正样本概率，降低负样本概率

    Args:
        openid: str — 用户ID
        preferred_expert: str — 用户更喜欢的专家（得分更高的）
        rejected_expert: str — 用户不喜欢的专家（可选）
        preferred_type: str — 偏好类型（直接指定，如'score_high'）
        rejected_type: str — 拒绝类型
    """
    if not openid:
        return

    data = _load_user(openid)
    probs = data['probs']

    # 如果没有对比对象，用默认基线
    experts_involved = set()
    if preferred_expert:
        experts_involved.add(preferred_expert)
    if rejected_expert:
        experts_involved.add(rejected_expert)

    # 初始化
    for e in experts_involved:
        if e not in probs:
            probs[e] = 0.5  # 初始中性

    # DPO更新: 偏好专家概率+，拒绝专家概率-
    if preferred_expert:
        probs[preferred_expert] = min(0.99, probs[preferred_expert] + _DPO_LR)
    if rejected_expert:
        probs[rejected_expert] = max(0.01, probs[rejected_expert] - _DPO_LR)

    data['pairs'] += 1
    _save_user(openid, data)


def get_dpo_bias(openid, expert_name):
    """获取DPO偏好偏差

    Returns: float, -0.5 ~ +0.5（映射自0-1偏好概率）
    """
    if not openid or not expert_name:
        return 0.0
    data = _load_user(openid)
    prob = data['probs'].get(expert_name, 0.5)
    return round(prob - 0.5, 3)  # 0.5中性，>0偏好，<0排斥


def dpo_summary(openid):
    """偏好摘要"""
    data = _load_user(openid)
    return {
        'pairs': data['pairs'],
        'biases': {k: round(v - 0.5, 3) for k, v in data['probs'].items()},
    }


# ===== 自测 =====
if __name__ == '__main__':
    print('=== DPO Preference Test ===\n')

    # 用户喜欢CBT不喜欢RiskManager
    record_preference('test_dpo', 'CBT', 'RiskManager')
    print('Test 1: CBT=%.3f, RM=%.3f' % (
        get_dpo_bias('test_dpo', 'CBT'),
        get_dpo_bias('test_dpo', 'RiskManager')))
    assert get_dpo_bias('test_dpo', 'CBT') > 0
    assert get_dpo_bias('test_dpo', 'RiskManager') < 0

    # 多次CP作为偏好
    for _ in range(5):
        record_preference('test_dpo', 'ClinicalPsychologist', 'RiskManager')
    cp_bias = get_dpo_bias('test_dpo', 'ClinicalPsychologist')
    rm_bias = get_dpo_bias('test_dpo', 'RiskManager')
    print('Test 2 (5x CP>RM): CP=%.3f, RM=%.3f' % (cp_bias, rm_bias))
    assert cp_bias > 0.3  # 累积到明显偏好
    assert rm_bias < -0.3

    sm = dpo_summary('test_dpo')
    print('Test 3 (summary): pairs=%d, biases=%s' % (sm['pairs'], sm['biases']))
    assert sm['pairs'] >= 6

    # 清理
    import os as _os
    _p = _os.path.join(DPO_DIR, 'test_dpo.json')
    if _os.path.exists(_p):
        _os.remove(_p)

    print('\nAll tests passed!')
