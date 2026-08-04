#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
counterfactual.py — AISleepGen 反事实推理框架

核心问题：用户评分变了，是干预起效了，还是自然波动？
解决：从非干预日的评分历史建"自然基线"，用干预日效果 vs 基线做判断。

三位一体：
  1. 自然基线模型 — 用户不做任何干预时的期望评分分布
  2. 干预效果评估 — 每次干预后的评分变化 vs 同期基线
  3. 决策门 — "这个值不值得干预？"

数据不足时自动跳过（min_natural_days=7）。
"""
import os, json
from datetime import datetime, timedelta
from math import sqrt

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def build_natural_baseline(profile):
    """从非干预日数据构建自然基线

    返回: dict {
        'mean': 0.0,       # 自然平均评分
        'std': 0.0,        # 自然标准差（衡量自然波动）
        'count': 0,        # 非干预日样本数
        'recent_mean': 0.0, # 近7天自然均值
        'has_baseline': False,  # 基线是否有效
    }
    """
    history = profile.get('history', [])
    pending = profile.get('_pending_interventions', [])
    rec_history = profile.get('_recommendation_history', [])

    # 记录所有被干预的日期
    intervention_dates = set()
    for p in pending:
        d = p.get('time', '')
        if d:
            intervention_dates.add(d[:10])
    for r in rec_history:
        d = r.get('date', '')
        if d:
            intervention_dates.add(d)
        eval_d = r.get('evaluated_on', '')
        if eval_d:
            intervention_dates.add(eval_d)

    # 筛选非干预日的评分
    natural_scores = []
    for h in history:
        if not isinstance(h, dict):
            continue
        date_str = h.get('date', '')
        score = h.get('wm_score', 0)
        if date_str and score > 0 and date_str not in intervention_dates:
            natural_scores.append({'date': date_str, 'score': score})

    count = len(natural_scores)
    if count < 7:  # 数据不足
        return {
            'mean': 0, 'std': 0, 'count': count,
            'recent_mean': 0, 'has_baseline': False,
        }

    scores = [s['score'] for s in natural_scores]
    mean = sum(scores) / count
    variance = sum((s - mean) ** 2 for s in scores) / count
    std = sqrt(variance) if variance > 0 else 0

    # 近7天
    cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    recent = [s for s in natural_scores if s['date'] >= cutoff]
    recent_mean = sum(s['score'] for s in recent) / len(recent) if recent else mean

    return {
        'mean': round(mean, 1),
        'std': round(std, 1),
        'count': count,
        'recent_mean': round(recent_mean, 1),
        'has_baseline': True,
    }


def evaluate_intervention_effect(profile, baseline=None):
    """评估最近一次干预的效果是否超过自然波动

    返回: dict {
        'lift': 0,           # 干预后评分提升(相比基线)
        'effect_size': 0,    # 标准化效应量 (lift / baseline.std)
        'notable': False,    # 是否值得关注(效应量>0.3)
        'detail': '',
    }
    """
    if baseline is None:
        baseline = build_natural_baseline(profile)

    if not baseline['has_baseline']:
        return {'lift': 0, 'effect_size': 0, 'notable': False,
                'detail': '基线数据不足(需≥7个非干预日)', 'baseline': baseline}

    rec_history = profile.get('_recommendation_history', [])
    evaluated = [r for r in rec_history if r.get('status') == 'evaluated'
                 and r.get('score_at_time') and r.get('score_after')]
    if not evaluated:
        return {'lift': 0, 'effect_size': 0, 'notable': False,
                'detail': '无已评估的干预记录', 'baseline': baseline}

    # 最近一次干预效果
    latest = evaluated[-1]
    lift = (latest['score_after'] - latest['score_at_time']) - baseline['recent_mean'] + baseline['mean']

    # 效应量 = lift / 自然标准差
    effect_size = lift / baseline['std'] if baseline['std'] > 0 else 0

    return {
        'lift': round(lift, 1),
        'effect_size': round(effect_size, 2),
        'notable': abs(effect_size) >= 0.3,
        'detail': (
            f'自然基线={baseline["mean"]}±{baseline["std"]}(n={baseline["count"]}) '
            f'vs 干预Lift={lift:.1f}, 效应量={effect_size:.2f}'
        ),
        'baseline': baseline,
    }


def should_intervene(profile, predicted_score, baseline=None):
    """反事实决策门：这个值不值得干预？

    核心逻辑：
    - 如果预测评分在自然基线的1个标准差内 → 自然波动，不干预
    - 如果超出1个标准差且趋势变差 → 干预
    - 数据不足时 fallback 到旧逻辑（predicted < 75）
    """
    if baseline is None:
        baseline = build_natural_baseline(profile)

    if not baseline['has_baseline']:
        # 降级到旧逻辑
        return {'intervene': False, 'reason': 'fallback_threshold',
                'detail': '数据不足，由干预调度器自主决定'}

    # 自然波动范围
    natural_high = baseline['mean'] + baseline['std']
    natural_low = baseline['mean'] - baseline['std']

    if predicted_score < natural_low:
        return {'intervene': True, 'reason': 'below_natural_range',
                'detail': f'预测{predicted_score}分低于自然下限{natural_low:.0f}分'}
    elif predicted_score > natural_high:
        return {'intervene': False, 'reason': 'above_natural_range',
                'detail': f'预测{predicted_score}分在自然范围内({natural_low:.0f}-{natural_high:.0f})'}
    else:
        # 在自然范围内 → 看趋势
        return {'intervene': False, 'reason': 'within_natural_range',
                'detail': f'在自然波动范围内，不干预'}


# ===== 快速测试 =====
if __name__ == '__main__':
    test_profile = {
        'history': [
            {'date': f'2026-0{(d%12)+1:02d}-0{(d%28)+1:02d}',
             'wm_score': 55 + d}
            for d in range(14)
        ],
        '_pending_interventions': [
            {'strategy_id': 'wind_down_routine', 'time': '2026-07-04 20:00', 'completed': True}
        ],
        '_recommendation_history': [
            {'type': 'fixed_schedule', 'date': '2026-07-03',
             'score_at_time': 57, 'score_after': 72,
             'status': 'evaluated', 'effect': 'positive',
             'evaluated_on': '2026-07-04'},
        ],
    }

    baseline = build_natural_baseline(test_profile)
    print(f'基线: mean={baseline["mean"]} std={baseline["std"]} count={baseline["count"]}')

    effect = evaluate_intervention_effect(test_profile, baseline)
    print(f'效果: {effect["detail"]}')
    print(f'  效应量={effect["effect_size"]}, notable={effect["notable"]}')

    decision = should_intervene(test_profile, 60, baseline)
    print(f'决策: {decision["reason"]} — {decision["detail"]}')
