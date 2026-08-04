#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
noisy_student.py — Noisy Student自训练 (v7.5+)
原理: Google Noisy Student — 用伪标签+噪声进行半监督自训练
落地: 从历史数据中生成"伪标签"增强分析鲁棒性

用法:
  from noisy_student import self_train_with_noise, get_noisy_ensemble
  ensemble = self_train_with_noise(records)
  pred = get_noisy_ensemble(ensemble, new_data)
"""

import random
import math
from collections import defaultdict

DIMENSIONS = [
    'sleep_latency', 'awake_times', 'total_duration',
    'stress_level', 'bedtime_hour', 'wake_hour', 'score',
]

DIM_LABELS = {
    'sleep_latency': '入睡延迟', 'awake_times': '夜醒次数',
    'total_duration': '总睡眠时长', 'stress_level': '压力水平',
    'bedtime_hour': '就寝时间', 'wake_hour': '起床时间', 'score': '睡眠评分',
}


def _generate_pseudo_labels(records, noise_std=0.15):
    """从真实数据生成带噪声的伪标签

    找一个有'分数标签'的记录，随机扰动后作为伪标签
    """
    pseudo = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        score = rec.get('score') or rec.get('wm_score')
        if score is None:
            continue
        try:
            score = float(score)
        except (ValueError, TypeError):
            continue

        # 加噪声
        noisy = score + random.gauss(0, noise_std * 100)
        # 扰动维度
        new_rec = dict(rec)
        for dim in DIMENSIONS:
            val = new_rec.get(dim)
            if val is not None:
                try:
                    new_rec[dim] = float(val) + random.gauss(0, noise_std * 10)
                except (ValueError, TypeError):
                    pass
        new_rec['pseudo_score'] = max(0, min(100, noisy))
        new_rec['_is_pseudo'] = True
        pseudo.append(new_rec)
    return pseudo


def _weighted_average(values, weights):
    """加权平均"""
    total_w = sum(weights)
    if total_w == 0:
        return 0
    return sum(v * w for v, w in zip(values, weights)) / total_w


def self_train_with_noise(records, n_pseudo_rounds=2, noise_std=0.15):
    """Noisy Student自训练

    1. 用真实数据训练初步评估器
    2. 生成带噪声的伪标签
    3. 用伪标签扩充训练集
    4. 重复

    返回: 集成评估器（各轮结果的加权集成）
    """
    if not records or len(records) < 2:
        return {'rounds': [], 'ensemble': [], 'note': '数据不足'}

    # 第1轮：真实数据
    real_round = {
        'round': 0,
        'n_real': len(records),
        'n_pseudo': 0,
        'estimates': {},
    }

    # 计算维度均值（作为基线评估器）
    for dim in DIMENSIONS:
        vals = []
        for rec in records:
            v = rec.get(dim)
            if v is not None:
                try:
                    vals.append(float(v))
                except (ValueError, TypeError):
                    pass
        if vals:
            real_round['estimates'][dim] = {
                'mean': sum(vals) / len(vals),
                'std': math.sqrt(sum((v - sum(vals)/len(vals))**2 for v in vals) / len(vals)),
                'n': len(vals),
            }

    rounds = [real_round]

    # 后续轮次：加噪声自训练
    all_records = list(records)
    for r in range(1, n_pseudo_rounds + 1):
        pseudo = _generate_pseudo_labels(records, noise_std=noise_std / r)
        all_records.extend(pseudo)

        pseudo_round = {
            'round': r,
            'n_real': len(records),
            'n_pseudo': len(pseudo),
            'estimates': {},
        }

        for dim in DIMENSIONS:
            vals = []
            for rec in all_records:
                v = rec.get(dim) or rec.get('pseudo_score')
                if v is not None:
                    try:
                        vals.append(float(v))
                    except (ValueError, TypeError):
                        pass
            if vals:
                pseudo_round['estimates'][dim] = {
                    'mean': sum(vals) / len(vals),
                    'std': math.sqrt(sum((v - sum(vals)/len(vals))**2 for v in vals) / len(vals)),
                    'n': len(vals),
                }

        rounds.append(pseudo_round)

    # 集成：各轮加权（越晚的轮次权重越高）
    ensemble = {}
    for dim in DIMENSIONS:
        for rnd in rounds:
            if dim in rnd.get('estimates', {}):
                weight = rnd['round'] + 1  # 后轮权重高
                if dim not in ensemble:
                    ensemble[dim] = {'means': [], 'weights': []}
                ensemble[dim]['means'].append(rnd['estimates'][dim]['mean'])
                ensemble[dim]['weights'].append(weight)

    return {
        'rounds': rounds,
        'ensemble': ensemble,
        'n_total': len(all_records),
    }


def get_noisy_ensemble(model, new_data):
    """用集成评估器对新数据做预测"""
    if 'error' in model or not model.get('ensemble'):
        return {'prediction': None, 'note': '模型未就绪'}

    ensemble = model['ensemble']
    predictions = {}
    for dim in DIMENSIONS:
        if dim in ensemble:
            info = ensemble[dim]
            pred = _weighted_average(info['means'], info['weights'])
            predictions[dim] = round(pred, 2)

    return {
        'prediction': predictions,
        'n_rounds': len(model.get('rounds', [])),
        'n_total': model.get('n_total', 0),
    }


def noisy_summary(model):
    """摘要"""
    if 'note' in model:
        return 'NoisyStudent: %s' % model['note']
    rounds = model.get('rounds', [])
    n_pseudo = sum(r['n_pseudo'] for r in rounds)
    return 'NoisyStudent: %d轮(%d真实+%d伪标签), %d维度' % (
        len(rounds), rounds[0]['n_real'] if rounds else 0,
        n_pseudo, len(model.get('ensemble', {})))


# ===== 自测 =====
if __name__ == '__main__':
    import random
    random.seed(42)

    records = []
    for i in range(15):
        stress = random.gauss(5, 2)
        latency = 30 + stress * 3 + random.gauss(0, 8)
        score = 75 - stress * 3 - latency * 0.1 + random.gauss(0, 6)
        records.append({'stress_level': stress, 'sleep_latency': latency, 'score': max(10, min(100, score))})

    model = self_train_with_noise(records)
    print(noisy_summary(model))
    print('Rounds:', len(model['rounds']))
    assert len(model['rounds']) == 3
    assert model['rounds'][0]['n_pseudo'] == 0
    assert model['rounds'][1]['n_pseudo'] == 15

    pred = get_noisy_ensemble(model, {})
    print('Prediction:', pred.get('prediction', {}))
    assert 'score' in pred.get('prediction', {})

    print('\nAll tests passed!')
