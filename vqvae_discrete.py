#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vqvae_discrete.py — VQ-VAE离散编码 (v7.5+)
原理: DeepMind VQ-VAE — 用Vector Quantization将连续睡眠数据离散化为"码本模式"
落地: 从历史数据中学习"N种典型睡眠模式"（如: 高压力-短睡眠-低评分）

用法:
  from vqvae_discrete import fit_vqvae, encode_pattern, get_pattern_summary
  model = fit_vqvae(records, k=6)
  pattern = encode_pattern(model, new_data)
  summary = get_pattern_summary(model)
"""

import math
import random
from collections import Counter

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


def _extract_matrix(records):
    """提取矩阵 [样本数 x 维度数]"""
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
        return None, active

    n = min(len(vecs[d]) for d in active)
    matrix = []
    for i in range(n):
        row = [vecs[d][i] for d in active]
        matrix.append(row)

    # Z-score归一化
    for j in range(len(active)):
        col = [matrix[i][j] for i in range(n)]
        zcol = _zscore(col)
        for i in range(n):
            matrix[i][j] = zcol[i]

    return matrix, active


def _euclidean(a, b):
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))


def _kmeans_init(data, k):
    """k-means++初始化"""
    n = len(data)
    centroids = [random.choice(data)]
    for _ in range(1, k):
        dists = [min(_euclidean(p, c) for c in centroids) ** 2 for p in data]
        total = sum(dists)
        if total == 0:
            centroids.append(random.choice(data))
        else:
            probs = [d / total for d in dists]
            idx = random.choices(range(n), weights=probs, k=1)[0]
            centroids.append(data[idx])
    return centroids


def _kmeans(data, k, max_iter=30):
    """k-means聚类"""
    centroids = _kmeans_init(data, k)
    for _ in range(max_iter):
        # 分配
        labels = [min(range(k), key=lambda j: _euclidean(p, centroids[j])) for p in data]
        # 更新
        new_centroids = []
        for j in range(k):
            members = [data[i] for i in range(len(data)) if labels[i] == j]
            if members:
                new_centroids.append([sum(m[d] for m in members) / len(members) for d in range(len(members[0]))])
            else:
                new_centroids.append(centroids[j])  # 保留旧中心
        centroids = new_centroids
    return centroids


def fit_vqvae(records, k=6):
    """训练VQ-VAE码本

    VQ-VAE = k-means + 码本查找

    Args:
        records: list[dict] — 用户历史睡眠记录
        k: int — 码本大小（典型睡眠模式数量）

    Returns:
        dict: {codebook, counts, reconst_error, center_dims, active_dims}
    """
    matrix, active = _extract_matrix(records)
    if matrix is None:
        return {'error': '数据不足', 'active_dims': active or []}

    # k-means训练码本
    codebook = _kmeans(matrix, k)

    # 编码: 每个样本→最近码本索引
    codes = [min(range(k), key=lambda j: _euclidean(p, codebook[j])) for p in matrix]

    # 重建误差
    errors = [_euclidean(matrix[i], codebook[codes[i]]) for i in range(len(matrix))]
    avg_error = sum(errors) / len(errors)

    # 每个码本被分配了多少样本
    counts = Counter(codes)

    # 每个码本的中心维度值（可读化）
    center_dims = {}
    for j in range(k):
        dim_vals = {}
        for di, dim in enumerate(active):
            dim_vals[dim] = round(codebook[j][di], 3)
        center_dims[j] = dim_vals

    return {
        'codebook': [[round(v, 3) for v in c] for c in codebook],
        'counts': dict(counts),
        'reconst_error': round(avg_error, 3),
        'center_dims': center_dims,
        'active_dims': active,
        'k': k,
        'n_samples': len(matrix),
    }


def encode_pattern(model, new_data):
    """将新数据编码为最近的码本索引

    Returns: (code_idx, distance)
    """
    if 'error' in model:
        return -1, 0

    # 将新数据转成向量
    active = model.get('active_dims', [])
    if not active:
        return -1, 0

    codebook = model.get('codebook', [])
    if not codebook:
        return -1, 0

    vec = []
    for d in active:
        v = new_data.get(d) if isinstance(new_data, dict) else 0
        if v is not None:
            try:
                vec.append(float(v))
            except (ValueError, TypeError):
                vec.append(0.0)
        else:
            vec.append(0.0)

    k = len(codebook)
    distances = [_euclidean(vec[:len(codebook[0])], cb) for cb in codebook]
    best = min(range(k), key=lambda j: distances[j])
    return best, round(distances[best], 3)


def get_pattern_summary(model):
    """可读的模式摘要"""
    if 'error' in model:
        return 'VQ-VAE: %s' % model['error']

    k = model.get('k', 0)
    counts = model.get('counts', {})
    center_dims = model.get('center_dims', {})
    err = model.get('reconst_error', 0)

    lines = ['VQ-VAE (%d种睡眠模式, 重建误差=%.3f):' % (k, err)]
    for j in range(k):
        count = counts.get(j, 0)
        dims = center_dims.get(j, {})
        # 找最有特征（最偏离0的维度）
        top = [(d, abs(v)) for d, v in dims.items()]
        top.sort(key=lambda x: -x[1])
        top3 = [(d, v) for d, v in dims.items() if abs(v) > 0.3]
        if not top3:
            top3 = [(d, dims[d]) for d, v in top[:2]]
        desc = ', '.join('(%s %.1f)' % (DIM_LABELS.get(d, d), v) for d, v in top3)
        lines.append('  模式%d [%d条]: %s' % (j, count, desc))

    return '\n'.join(lines)


# ===== 自测 =====
if __name__ == '__main__':
    import random
    random.seed(42)

    # 模拟数据: 3种隐含模式
    records = []
    for _ in range(40):
        mode = random.randint(0, 2)
        if mode == 0:  # 高压力-入睡慢-低分
            records.append({
                'stress_level': random.gauss(8, 1),
                'sleep_latency': random.gauss(60, 10),
                'score': random.gauss(35, 5),
                'awake_times': random.gauss(3, 1),
                'total_duration': random.gauss(300, 30),
                'bedtime_hour': 23 + random.gauss(0, 0.5),
                'wake_hour': 6 + random.gauss(0, 0.3),
            })
        elif mode == 1:  # 低压力-正常入睡-高分
            records.append({
                'stress_level': random.gauss(2, 1),
                'sleep_latency': random.gauss(15, 5),
                'score': random.gauss(85, 5),
                'awake_times': random.gauss(0.5, 0.5),
                'total_duration': random.gauss(480, 30),
                'bedtime_hour': 22.5 + random.gauss(0, 0.3),
                'wake_hour': 7 + random.gauss(0, 0.3),
            })
        else:  # 中压力-中等入睡-中分
            records.append({
                'stress_level': random.gauss(5, 1),
                'sleep_latency': random.gauss(30, 8),
                'score': random.gauss(60, 5),
                'awake_times': random.gauss(1.5, 0.8),
                'total_duration': random.gauss(400, 30),
                'bedtime_hour': 23 + random.gauss(0, 0.5),
                'wake_hour': 6.5 + random.gauss(0, 0.3),
            })

    model = fit_vqvae(records, k=4)
    print(get_pattern_summary(model))

    # 编码新数据
    code, dist = encode_pattern(model, {'stress_level': 9, 'sleep_latency': 70, 'score': 30})
    print('\nHigh-stress encoded as pattern %d (dist=%.2f)' % (code, dist))

    assert 'error' not in model
    assert model['k'] == 4
    assert code >= 0
    print('\nAll tests passed!')
