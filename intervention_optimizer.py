#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
intervention_optimizer.py — 干预方案参数自适应优化

Bayesian Optimization 启发：不是固定参数，而是根据用户反馈自动调参。
当前应用：腹式呼吸节奏（吸-停-呼秒数）+ 白噪音音量

原理简化版：
1. 每个参数有一个默认值 + 可调范围
2. 每次推荐时，从高斯过程后验采样最优参数
3. 用户反馈（有效/无效）→ 更新后验
4. 探索-利用：ε=20% 概率尝试新参数

数据不足时(<3次反馈)返回默认值。
"""

import math
import random
import time

# 参数空间定义（边界 + 默认值）
PARAM_SPACE = {
    'breath_mantra': {
        'inhale_sec': {'default': 4, 'min': 3, 'max': 6, 'step': 1},
        'hold_sec': {'default': 4, 'min': 2, 'max': 7, 'step': 1},
        'exhale_sec': {'default': 4, 'min': 3, 'max': 8, 'step': 1},
    },
    'wind_down_routine': {
        'duration_min': {'default': 30, 'min': 15, 'max': 45, 'step': 5},
    },
}

# 简化的高斯过程核：距离越近的反馈权重越高
_GP_MEMORY = {}  # {strategy_id: [(params_tuple, score), ...]}


def _gaussian_kernel(d, length_scale=2.0):
    """RBF 核：距离 d 下的相关性"""
    return math.exp(-0.5 * (d / length_scale) ** 2)


def _params_distance(a, b):
    """两个参数向量的欧氏距离（归一化后）"""
    if len(a) != len(b):
        return 1.0
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b))) / max(len(a), 1)


def record_feedback(strategy_id, params, effective):
    """记录一次参数反馈
    
    Args:
        strategy_id: 策略ID
        params: dict — 参数名→值
        effective: bool — 是否有效
    """
    if strategy_id not in PARAM_SPACE:
        return False
    
    param_defs = PARAM_SPACE[strategy_id]
    # 归一化为元组
    normalized = tuple(
        (params.get(k, v['default']) - v['min']) / max(v['max'] - v['min'], 1)
        for k, v in sorted(param_defs.items())
    )
    
    if strategy_id not in _GP_MEMORY:
        _GP_MEMORY[strategy_id] = []
    _GP_MEMORY[strategy_id].append((normalized, 1.0 if effective else 0.0, time.time()))
    
    # 保留最多 50 条历史
    if len(_GP_MEMORY[strategy_id]) > 50:
        _GP_MEMORY[strategy_id] = _GP_MEMORY[strategy_id][-50:]
    
    return True


def _gp_predict(strategy_id, candidate_norm):
    """高斯过程预测：候选参数的效果期望
    
    用已有反馈的加权平均（权重=RBF核距离）
    """
    records = _GP_MEMORY.get(strategy_id, [])
    if not records:
        return 0.5, 0.3  # 无数据→默认50%+高不确定性
    
    total_weight = 0.0
    weighted_sum = 0.0
    for norm_tuple, eff, _ts in records:
        dist = _params_distance(candidate_norm, norm_tuple)
        w = _gaussian_kernel(dist)
        total_weight += w
        weighted_sum += w * eff
    
    if total_weight < 1e-6:
        return 0.5, 0.3
    
    mean = weighted_sum / total_weight
    # 不确定性 = 1 - 最大权重（越近的反馈越确定）
    max_w = max((_gaussian_kernel(_params_distance(candidate_norm, r[0])) for r in records), default=0)
    uncertainty = max(0.05, 1.0 - max_w * 0.8)
    
    return mean, uncertainty


def suggest_params(strategy_id, explore_prob=0.2):
    """推荐最优参数
    
    使用上置信界(UCB)采集函数：
    score = mean + 1.96 * sqrt(uncertainty)
    
    Args:
        strategy_id: 策略ID
        explore_prob: 探索概率（默认20%随机探索）
    
    Returns:
        dict — 参数名→值
    """
    if strategy_id not in PARAM_SPACE:
        return {}
    
    param_defs = PARAM_SPACE[strategy_id]
    records = _GP_MEMORY.get(strategy_id, [])
    
    # 数据不足 → 返回默认值
    if len(records) < 3:
        return {k: v['default'] for k, v in param_defs.items()}
    
    # 探索：随机参数
    if random.random() < explore_prob:
        return {
            k: random.randrange(v['min'], v['max'] + 1, v['step'])
            for k, v in param_defs.items()
        }
    
    # 利用：在参数空间中搜索 UCB 最高的点
    param_names = sorted(param_defs.keys())
    best_score = -float('inf')
    best_params = None
    
    # 简单网格搜索
    def _grid(params_dict, depth=0):
        nonlocal best_score, best_params
        if depth == len(param_names):
            norm = tuple(
                (params_dict[k] - param_defs[k]['min']) / max(param_defs[k]['max'] - param_defs[k]['min'], 1)
                for k in param_names
            )
            mean, uncert = _gp_predict(strategy_id, norm)
            ucb = mean + 1.96 * math.sqrt(uncert)  # 95%置信上界
            if ucb > best_score:
                best_score = ucb
                best_params = dict(params_dict)
            return
        
        k = param_names[depth]
        v = param_defs[k]
        for val in range(v['min'], v['max'] + 1, v['step']):
            params_dict[k] = val
            _grid(params_dict, depth + 1)
    
    _grid({})
    return best_params or {k: v['default'] for k, v in param_defs.items()}


def get_optimizer_summary():
    """诊断：返回活跃策略的参数空间和反馈数量"""
    result = {}
    for strategy_id, records in _GP_MEMORY.items():
        result[strategy_id] = {
            'feedback_count': len(records),
            'param_space': {k: v['default'] for k, v in PARAM_SPACE.get(strategy_id, {}).items()},
        }
    return result


if __name__ == '__main__':
    print('=== Intervention Optimizer ===')
    # 测试
    params = suggest_params('breath_mantra')
    print(f'Default (no data): {params}')
    
    # 加反馈
    record_feedback('breath_mantra', {'inhale_sec': 4, 'hold_sec': 4, 'exhale_sec': 4}, True)
    record_feedback('breath_mantra', {'inhale_sec': 5, 'hold_sec': 5, 'exhale_sec': 5}, True)
    record_feedback('breath_mantra', {'inhale_sec': 3, 'hold_sec': 2, 'exhale_sec': 3}, False)
    
    params = suggest_params('breath_mantra', explore_prob=0)
    print(f'Optimized (3 feedbacks): {params}')
    
    print(f'Summary: {get_optimizer_summary()}')
