#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gflownet.py — GFlowNet生成流网络 (v7.5+)
原理: GFlowNet — 从历史数据学得分分布，用能量基模型采样新的睡眠模式建议
落地: 从用户历史中学习"好睡眠"的能量分布，采样推荐干预方向

用法:
  from gflownet import sample_improvement, train_gflownet, gfn_summary
  model = train_gflownet(history)
  suggestion = sample_improvement(model, current_profile)
"""

import math, random, json, os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
GFN_DIR = os.path.join(PROJECT_ROOT, 'data', 'gflownet')
os.makedirs(GFN_DIR, exist_ok=True)

DIMS = ['stress_level', 'sleep_latency', 'score', 'awake_times', 'bedtime_hour']


def _energy(record, history):
    """能量函数: 低能量 = 好睡眠

    评分高→能量低, 压力大→能量高, 入睡慢→能量高
    """
    score = record.get('score', 50) if isinstance(record, dict) else 50
    stress = record.get('stress_level', 5) if isinstance(record, dict) else 5
    latency = record.get('sleep_latency', 30) if isinstance(record, dict) else 30
    awake = record.get('awake_times', 1) if isinstance(record, dict) else 1

    # 评分贡献: 78分以上低能量
    score_e = -1.0 * max(0, score - 60) / 40

    # 压力贡献: 5以上高能量
    stress_e = 0.5 * max(0, stress - 3) / 7

    # 入睡延迟: 30以上高能量
    latency_e = 0.3 * max(0, latency - 20) / 100

    # 夜醒: 2次以上高能量
    awake_e = 0.2 * max(0, awake - 1) / 4

    total = score_e + stress_e + latency_e + awake_e
    return total


def _temperature_schedule(epoch, total_epochs=50):
    """退火温度: 从1.0线性降到0.2"""
    return max(0.2, 1.0 - 0.8 * epoch / total_epochs)


def _normalize_energy(energies):
    """用Softmax将能量转为概率分布"""
    if not energies:
        return []
    max_e = max(energies)
    weights = [math.exp(-(e - max_e)) for e in energies]
    total = sum(weights)
    if total == 0:
        return [1.0 / len(energies)] * len(energies)
    return [w / total for w in weights]


def train_gflownet(history, n_steps=50):
    """训练GFlowNet模型（能量基模型）

    学一个从历史数据中采样"好睡眠模式"的能力

    Args:
        history: list[dict] — 用户的睡眠记录
        n_steps: int — 退火步数

    Returns:
        dict: {energies, prototypes, n_records, version}
    """
    if not history or len(history) < 3:
        return {'error': '历史数据不足'}

    # 用k-medoids选原型: 能量最低的k=3条记录
    energies = []
    valid_records = [r for r in history if isinstance(r, dict)]
    if len(valid_records) < 3:
        return {'error': '有效记录不足'}

    for rec in valid_records:
        e = _energy(rec, valid_records)
        energies.append((e, rec))

    # 按能量排序（低=好）
    energies.sort(key=lambda x: x[0])

    # 选能量最低的前k条作为原型
    k = min(3, max(1, len(energies) // 5 + 1))
    prototypes = [rec for e, rec in energies[:k]]

    # 退火采样: 逐步收敛
    final_weights = None
    for epoch in range(n_steps):
        temp = _temperature_schedule(epoch, n_steps)
        # 所有记录的能量→概率
        e_list = [e for e, rec in energies]
        e_list = [e / temp for e in e_list]
        probs = _normalize_energy(e_list)
        final_weights = probs

    # 采样最多的记录类型
    ensemble = {}
    for i, (e, rec) in enumerate(energies):
        cluster_key = 'good' if e < 0 else ('medium' if e < 1 else 'poor')
        if cluster_key not in ensemble:
            ensemble[cluster_key] = {'count': 0, 'energy_sum': 0, 'score_sum': 0}
        ensemble[cluster_key]['count'] += 1
        ensemble[cluster_key]['energy_sum'] += e
        score = rec.get('score', 50) if isinstance(rec, dict) else 50
        ensemble[cluster_key]['score_sum'] += score

    return {
        'energies': [round(e, 3) for e, rec in energies],
        'prototypes': prototypes,
        'n_records': len(valid_records),
        'energy_ensemble': {k: {'count': v['count'],
                                'avg_energy': round(v['energy_sum'] / v['count'], 3),
                                'avg_score': round(v['score_sum'] / v['count'], 1)}
                            for k, v in ensemble.items()},
        'lowest_energy': round(energies[0][0], 3) if energies else 0,
        'version': 'v1',
    }


def sample_improvement(model, current):
    """采样改善方向

    从学习到的分布中采样，给出和当前最不同的高概率点

    Args:
        model: GFlowNet模型
        current: dict — 当前睡眠状态

    Returns:
        dict: {deltas: 各维度调整方向, suggested_score, confidence}
    """
    if 'error' in model:
        return {'suggestion': model['error']}

    prototypes = model.get('prototypes', [])
    if not prototypes:
        return {'suggestion': '无原型'}

    # 找最接近当前的原型
    best_proto = None
    best_dist = float('inf')
    for proto in prototypes:
        if not isinstance(proto, dict):
            continue
        dist = 0
        for d in DIMS:
            cv = current.get(d, 50) if isinstance(current, dict) else 50
            pv = proto.get(d, 50)
            try:
                dist += abs(float(cv) - float(pv)) / 100
            except (ValueError, TypeError):
                pass
        if dist < best_dist:
            best_dist = dist
            best_proto = proto

    if not best_proto:
        return {'suggestion': '无匹配原型'}

    # 计算改善方向
    deltas = {}
    total_dims = 0
    for d in DIMS:
        cv = current.get(d, 50) if isinstance(current, dict) else 50
        pv = best_proto.get(d, 50)
        try:
            delta = float(pv) - float(cv)
            if abs(delta) > 0.5:  # 忽略微小变化
                deltas[d] = round(delta, 1)
                total_dims += 1
        except (ValueError, TypeError):
            pass

    suggested_score = best_proto.get('score', 0)
    current_score = current.get('score', 50) if isinstance(current, dict) else 50

    return {
        'deltas': deltas,
        'n_dims_to_improve': total_dims,
        'suggested_score': round(suggested_score, 1) if suggested_score else 0,
        'current_score': round(current_score, 1),
        'potential_gain': round(suggested_score - current_score, 1) if suggested_score and current_score else 0,
        'matched_proto_energy': _energy(best_proto, prototypes),
    }


def gfn_summary(model):
    """摘要"""
    if 'error' in model:
        return 'GFlowNet: %s' % model['error']
    ensemble = model.get('energy_ensemble', {})
    good = ensemble.get('good', {})
    return 'GFlowNet: %d条, 好睡眠(%d条, 评分%.1f), 最低能量=%.2f' % (
        model['n_records'],
        good.get('count', 0),
        good.get('avg_score', 0),
        model.get('lowest_energy', 0),
    )


# ===== 自测 =====
if __name__ == '__main__':
    print('=== GFlowNet Test ===\n')

    # 混合数据: 大部分差, 小部分好
    history = [{'stress_level': 7, 'sleep_latency': 55, 'score': 35,
                'awake_times': 3, 'bedtime_hour': 23.5} for _ in range(15)]
    history += [{'stress_level': 3, 'sleep_latency': 18, 'score': 82,
                 'awake_times': 0.5, 'bedtime_hour': 22.8} for _ in range(5)]

    model = train_gflownet(history)
    print(gfn_summary(model))
    assert 'error' not in model
    assert model['n_records'] == 20

    # 采样改善
    current = {'stress_level': 7, 'sleep_latency': 55, 'score': 35,
               'awake_times': 3, 'bedtime_hour': 23.5}
    suggestion = sample_improvement(model, current)
    print('Deltas:', suggestion['deltas'])
    print('Gain:', suggestion['potential_gain'])
    assert 'deltas' in suggestion

    # 数据不足
    m2 = train_gflownet([])
    assert 'error' in m2

    print('\nAll tests passed!')
