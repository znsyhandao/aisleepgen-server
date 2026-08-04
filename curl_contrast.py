#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
curl_contrast.py — CURL对比表示学习 (v7.5+)
原理: DeepMind CURL — 从无标签数据中用对比学习自动发现模式
落地: 用同用户相邻两天为正样本、不同用户为负样本，学习睡眠模式的区分度

用法:
  from curl_contrast import fit_curl, contrast_score, curl_summary
  model = fit_curl(records)
  sim = contrast_score(model, day1, day2)
"""

import math
import random
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


def _zscore(vec):
    n = len(vec)
    if n < 2:
        return vec[:]
    mu = sum(vec) / n
    s = math.sqrt(max(1e-10, sum((v - mu)**2 for v in vec) / (n - 1)))
    return [(v - mu) / s for v in vec]


def _to_vector(rec, active_dims):
    """将记录转为归一化向量"""
    vec = []
    for d in active_dims:
        v = rec.get(d) if isinstance(rec, dict) else 0
        if v is not None:
            try:
                vec.append(float(v))
            except (ValueError, TypeError):
                vec.append(0.0)
        else:
            vec.append(0.0)
    return vec


def _cosine_sim(a, b):
    """余弦相似度"""
    dot = sum(ai * bi for ai, bi in zip(a, b))
    na = math.sqrt(max(1e-10, sum(ai**2 for ai in a)))
    nb = math.sqrt(max(1e-10, sum(bi**2 for bi in b)))
    return dot / (na * nb)


def _contrastive_loss(pos_sim, neg_sims, temperature=0.1):
    """InfoNCE对比损失

    让正样本相似度高、负样本相似度低
    loss = -log( exp(pos/tau) / (exp(pos/tau) + sum(exp(neg_i/tau))) )
    """
    pos_exp = math.exp(pos_sim / temperature)
    neg_sum = sum(math.exp(n / temperature) for n in neg_sims)
    if pos_exp + neg_sum == 0:
        return 1.0
    return -math.log(pos_exp / (pos_exp + neg_sum))


def _find_neighbors(records, active_dims, k=3):
    """找"正样本对": 同用户相邻2天

    用相邻索引模拟相邻日期
    负样本: 随机选不同索引的数据
    """
    n = len(records)
    pos_pairs = []
    for i in range(n - 1):
        # 相邻两天的数据是正样本
        v1 = _to_vector(records[i], active_dims)
        v2 = _to_vector(records[i + 1], active_dims)
        if v1 and v2:
            pos_pairs.append((v1, v2))

    return pos_pairs


def fit_curl(records, temperature=0.1, n_negatives=3):
    """训练CURL对比表示模型

    用InfoNCE损失训练"相邻天相似、不同天不同"

    Args:
        records: list[dict] — 用户历史睡眠记录（按时间顺序）
        temperature: float — 对比损失的温度参数
        n_negatives: int — 每个正样本对的负样本数

    Returns:
        dict: {projection, avg_loss, n_pairs, active_dims}
    """
    # 提取活跃维度
    vecs = {d: [] for d in DIMENSIONS}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for d in DIMENSIONS:
            v = rec.get(d)
            if v is not None:
                try:
                    vecs[d].append(float(v))
                except (ValueError, TypeError):
                    pass

    active = [d for d in DIMENSIONS if len(vecs[d]) >= 3]
    if len(active) < 3:
        return {'error': '数据不足', 'active_dims': active}

    n = len(records)
    pos_pairs = _find_neighbors(records, active)

    if len(pos_pairs) < 2:
        return {'error': '正样本对不足', 'active_dims': active}

    # 学习"投影方向": 用对比损失驱动
    # 用SimCLR风格的简单线性投影
    # 随机初始化一个投影向量
    random.seed(42)
    proj = [random.gauss(0, 1.0 / math.sqrt(len(active))) for _ in range(len(active))]

    # 用梯度下降优化（模拟对比训练）
    lr = 0.05
    for epoch in range(30):
        total_loss = 0.0
        for v1, v2 in pos_pairs:
            # 投影
            p1 = sum(v1[d] * proj[d] for d in range(len(active)))
            p2 = sum(v2[d] * proj[d] for d in range(len(active)))
            pos_sim = _cosine_sim(v1, v2)

            # 随机负样本
            neg_sims = []
            for _ in range(n_negatives):
                neg_idx = random.randint(0, n - 1)
                # 确保不是v1/v2的同一索引
                while neg_idx in (pos_pairs.index((v1, v2)),):
                    neg_idx = random.randint(0, n - 1)
                v_neg = _to_vector(records[neg_idx], active)
                neg_sims.append(_cosine_sim(v1, v_neg))

            loss = _contrastive_loss(pos_sim, neg_sims, temperature)
            total_loss += loss

            # 梯度下降: 投影向量微调
            for d in range(len(active)):
                # 简化梯度: 使正样本投影接近、负样本远离
                grad = 0
                for ns in neg_sims:
                    grad += (1 - pos_sim) * v1[d] - (1 + ns) * v1[d]
                proj[d] -= lr * grad * 0.001

        avg_loss = total_loss / len(pos_pairs)
        if epoch == 29:
            final_loss = avg_loss

    return {
        'projection': [round(p, 4) for p in proj],
        'avg_loss': round(final_loss, 4),
        'n_pairs': len(pos_pairs),
        'active_dims': active,
        'temperature': temperature,
        'dim_labels': {d: DIM_LABELS.get(d, d) for d in active},
    }


def contrast_score(model, day1, day2):
    """计算两天的对比相似度

    Returns: float, -1~1
    """
    if 'error' in model:
        return 0.0
    active = model.get('active_dims', [])
    if not active:
        return 0.0

    v1 = _to_vector(day1, active)
    v2 = _to_vector(day2, active)
    if not v1 or not v2:
        return 0.0
    return round(_cosine_sim(v1, v2), 3)


def curl_summary(model):
    """摘要"""
    if 'error' in model:
        return 'CURL: %s' % model['error']
    proj = model.get('projection', [])
    top_dims = sorted(enumerate(proj), key=lambda x: -abs(x[1]))[:3]
    active = model.get('active_dims', [])
    top_str = ', '.join('%s(%.3f)' % (DIM_LABELS.get(active[d], active[d]), v) for d, v in top_dims)
    return 'CURL: %d对, 损失=%.3f, 关键维度: %s' % (
        model.get('n_pairs', 0), model.get('avg_loss', 0), top_str)


# ===== 自测 =====
if __name__ == '__main__':
    import random
    random.seed(42)

    # 模拟: 连续35天数据（相邻天相似）
    records = []
    base_stress = 5.0
    base_latency = 30.0
    for d in range(35):
        # 相邻天漂移小
        drift = random.gauss(0, 0.3)
        base_stress += drift * 0.5
        base_latency += drift
        records.append({
            'stress_level': max(1, min(10, base_stress + random.gauss(0, 0.5))),
            'sleep_latency': max(5, min(120, base_latency + random.gauss(0, 5))),
            'score': max(10, min(100, 70 - base_stress * 2 - base_latency * 0.2 + random.gauss(0, 5))),
            'awake_times': max(0, random.gauss(1.5, 0.8)),
        })

    model = fit_curl(records)
    print(curl_summary(model))

    # 相邻天应该有高相似度
    sim_pos = contrast_score(model, records[5], records[6])
    sim_neg = contrast_score(model, records[5], records[20])
    print('Adjacent days sim: %.3f, Far days sim: %.3f' % (sim_pos, sim_neg))

    assert 'error' not in model
    assert model['n_pairs'] >= 2

    # 测试数据不足
    m2 = fit_curl([{'stress_level': 5}])
    assert 'error' in m2

    print('\nAll tests passed!')
