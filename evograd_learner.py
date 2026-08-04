#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evograd_learner.py — EvoGrad元梯度学习 (v7.5+)
原理: DeepMind EvoGrad — 基于预测误差的元梯度学习，自动调整专家权重
落地: 从用户反馈中学习每位专家的"进化方向"——该加权重还是减权重

用法:
  from evograd_learner import update_metagrad, get_metagrad_adjustment, metagrad_summary
  update_metagrad(openid, expert_name, prediction_error)
  adj = get_metagrad_adjustment(openid, expert_name)
"""

import json, os, math, time
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
EVO_DIR = os.path.join(PROJECT_ROOT, 'data', 'evograd')
os.makedirs(EVO_DIR, exist_ok=True)

# 默认元参数
_BASE_LR = 0.02        # 基础学习率
_META_LR = 0.005       # 元学习率（meta-learning rate）
_MOMENTUM = 0.7        # 动量

# 专家分类（不同专家对误差的敏感度不同）
_EXPERT_SENSITIVITY = {
    'ClinicalPsychologist': 1.2,   # 心理评估误差更敏感
    'CBT': 1.0,
    'SleepPhysician': 1.5,         # 医学筛查误差最敏感
    'Chronobiologist': 0.8,
    'LifeScientist': 1.0,
    'RiskManager': 1.3,            # 风险评估高度敏感
    'StressRelaxation': 0.7,       # 减压评估相对宽松
    'ExerciseRehab': 0.7,
    'CardiacMonitor': 1.2,
    'NutriMetabolism': 0.7,
}


def _user_path(openid):
    safe_id = openid.replace('/', '_').replace('\\', '_')
    return os.path.join(EVO_DIR, '%s.json' % safe_id)


def _load_user(openid):
    path = _user_path(openid)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        'metagrads': {},
        'errors': [],
        'n_updates': 0,
    }


def _save_user(openid, data):
    with open(_user_path(openid), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _sigmoid_scale(x):
    """把调整量映射到 -0.3~+0.3"""
    return 0.3 * math.tanh(x)  # tanh 直接映射到 0.3*[-1,+1]


def update_metagrad(openid, expert_name, prediction_error):
    """用预测误差更新专家的元梯度

    prediction_error 范围: 0(完美预测) ~ 1(完全错误)
    负误差 = 预测过高需要降低权重
    正误差 = 预测过低需要增加权重

    Args:
        openid: str — 用户ID
        expert_name: str — 专家名
        prediction_error: float — 归一化的预测误差 (-1 ~ +1)
    """
    if not openid or not expert_name:
        return

    data = _load_user(openid)
    mg = data['metagrads']

    if expert_name not in mg:
        mg[expert_name] = {'velocity': 0.0, 'meta_lr': _META_LR, 'base_lr': _BASE_LR}

    entry = mg[expert_name]
    sensitivity = _EXPERT_SENSITIVITY.get(expert_name, 1.0)

    # 元梯度 = 误差 × 敏感度 × 元学习率 × 10（放大信号）
    meta_gradient = prediction_error * sensitivity * entry['meta_lr'] * 10

    # 动量更新
    entry['velocity'] = _MOMENTUM * entry['velocity'] + (1 - _MOMENTUM) * meta_gradient
    # 元梯度调整量映射到 -0.3 ~ +0.3
    entry['adjustment'] = round(_sigmoid_scale(entry['velocity']), 4)

    data['errors'].append({
        'expert': expert_name,
        'error': round(prediction_error, 4),
        'ts': time.time(),
    })
    # 保留最近200条
    if len(data['errors']) > 200:
        data['errors'] = data['errors'][-200:]

    data['n_updates'] += 1
    _save_user(openid, data)


def get_metagrad_adjustment(openid, expert_name):
    """获取某个专家的元梯度调整量

    Returns: float, -0.3 ~ +0.3（调整到专家score上）
    """
    if not openid or not expert_name:
        return 0.0
    data = _load_user(openid)
    entry = data['metagrads'].get(expert_name, {})
    return entry.get('adjustment', 0.0)


def metagrad_summary(openid):
    """获取元梯度摘要"""
    data = _load_user(openid)
    mg = data['metagrads']
    by_adj = sorted(mg.items(), key=lambda x: abs(x[1].get('adjustment', 0)), reverse=True)
    return {
        'n_updates': data['n_updates'],
        'top_adjusted': [(n, v.get('adjustment', 0)) for n, v in by_adj[:3]],
        'experts_tracked': len(mg),
    }


# ===== 自测 =====
if __name__ == '__main__':
    print('=== EvoGrad Test ===\n')

    # 测试1: 正误差 → 正调整
    update_metagrad('test_evo', 'ClinicalPsychologist', 0.5)
    adj = get_metagrad_adjustment('test_evo', 'ClinicalPsychologist')
    print('Test 1 (pos error): adj=%.4f (expect >0)' % adj)
    assert adj > 0

    # 测试2: 负误差 → 负调整
    update_metagrad('test_evo', 'CBT', -0.5)
    adj2 = get_metagrad_adjustment('test_evo', 'CBT')
    print('Test 2 (neg error): adj=%.4f (expect <0)' % adj2)
    assert adj2 < 0

    # 测试3: 多次更新累积
    for e in [0.3, 0.4, 0.2, 0.5]:
        update_metagrad('test_evo', 'SleepPhysician', e)
    adj3 = get_metagrad_adjustment('test_evo', 'SleepPhysician')
    print('Test 3 (multi): adj=%.4f (expect >0)' % adj3)
    assert adj3 > 0

    # 测试4: 摘要
    sm = metagrad_summary('test_evo')
    print('Test 4 (summary): updates=%d, tracked=%d' % (sm['n_updates'], sm['experts_tracked']))
    assert sm['n_updates'] >= 7

    # 清理
    import os as _os
    _p = os.path.join(EVO_DIR, 'test_evo.json')
    if _os.path.exists(_p):
        _os.remove(_p)

    print('\nAll tests passed!')
