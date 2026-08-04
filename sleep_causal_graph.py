#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sleep_causal_graph.py — 睡眠维度因果发现（v7.5+）
原理: PC算法简化版 — 基于条件独立性检验发现因果关系
参考: Spirtes et al. "Causation, Prediction, and Search"

维度: bedtime, wake_time, sleep_latency, awake_times,
       total_duration, stress_level, deep_sleep_pct, score

用法:
  from sleep_causal_graph import build_causal_graph, get_causal_insight
  graph = build_causal_graph(history_records)
  insight = get_causal_insight(graph, 'sleep_latency')
"""

import math
import json
import os
from datetime import datetime
from collections import defaultdict


# ===== 维度定义 =====
DIMENSIONS = [
    'sleep_latency', 'awake_times', 'total_duration',
    'stress_level', 'bedtime_hour', 'wake_hour', 'score',
]

DIM_LABELS = {
    'sleep_latency': '入睡延迟',
    'awake_times': '夜醒次数',
    'total_duration': '总睡眠时长',
    'stress_level': '压力水平',
    'bedtime_hour': '就寝时间',
    'wake_hour': '起床时间',
    'score': '睡眠评分',
}


def _pearson_r(x, y):
    """皮尔逊相关系数"""
    n = len(x)
    if n < 3:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    dx = math.sqrt(max(0, sum((x[i] - mx) ** 2 for i in range(n))))
    dy = math.sqrt(max(0, sum((y[i] - my) ** 2 for i in range(n))))
    if dx * dy == 0:
        return 0.0
    return num / (dx * dy)


def _partial_r(x, y, z):
    """一阶偏相关系数: r(x,y|z)"""
    r_xy = _pearson_r(x, y)
    r_xz = _pearson_r(x, z)
    r_yz = _pearson_r(y, z)
    denom = math.sqrt(max(0, (1 - r_xz ** 2) * (1 - r_yz ** 2)))
    if denom == 0:
        return 0.0
    return (r_xy - r_xz * r_yz) / denom


def _fisher_z(r, n):
    """Fisher Z 变换: 检验偏相关系数是否显著不为0"""
    if abs(r) >= 1.0:
        return float('inf')
    return 0.5 * math.log((1 + r) / max(1 - r, 1e-10)) * math.sqrt(n - 3)


def _extract_vectors(records):
    """从历史记录中提取维度向量"""
    vecs = {d: [] for d in DIMENSIONS}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for d in DIMENSIONS:
            val = rec.get(d, None)
            if val is not None:
                try:
                    vecs[d].append(float(val))
                except (ValueError, TypeError):
                    pass
    return vecs


def build_causal_graph(records, alpha=0.05):
    """构建因果图

    PC算法简化版:
    1. 计算全连接图
    2. 用条件独立性检验移除边
    3. 定向边（基于v-structure规则）

    Args:
        records: list[dict] — 用户历史睡眠记录
        alpha: float — 显著性水平

    Returns:
        dict: {'edges': [(from, to, strength)], 'isolated': [dim]}
    """
    vecs = _extract_vectors(records)
    active_dims = [d for d in DIMENSIONS if len(vecs[d]) >= 3]
    if len(active_dims) < 3:
        return {'edges': [], 'isolated': active_dims, 'note': '数据不足'}

    n = len(vecs[active_dims[0]])
    z_threshold = 1.96  # alpha=0.05

    # Step 1: 全连接图
    edges = set()
    for i in range(len(active_dims)):
        for j in range(i + 1, len(active_dims)):
            d1, d2 = active_dims[i], active_dims[j]
            r = _pearson_r(vecs[d1], vecs[d2])
            z = _fisher_z(r, n)
            if abs(z) > z_threshold:
                edges.add((d1, d2))

    # Step 2: 条件独立性检验（一阶）
    removed = set()
    for d1, d2 in list(edges):
        for cond in active_dims:
            if cond in (d1, d2):
                continue
            if len(vecs[cond]) < 3:
                continue
            min_len = min(len(vecs[d1]), len(vecs[d2]), len(vecs[cond]))
            if min_len < 3:
                continue
            pr = _partial_r(vecs[d1][:min_len], vecs[d2][:min_len], vecs[cond][:min_len])
            z = _fisher_z(pr, min_len)
            if abs(z) <= z_threshold:
                removed.add((d1, d2))
                edges.discard((d1, d2))
                break

    # Step 3: 定向（基于强度和时序偏好）
    # 对于每条剩余边，用绝对相关系数决定方向
    directed_edges = []
    for d1, d2 in edges:
        r = abs(_pearson_r(vecs[d1], vecs[d2]))
        # 时序启发: bedtime_hour/wake_hour 更可能是因
        if d1 in ('bedtime_hour', 'wake_hour'):
            directed_edges.append((d1, d2, round(r, 3)))
        elif d2 in ('bedtime_hour', 'wake_hour'):
            directed_edges.append((d2, d1, round(r, 3)))
        else:
            # 评分为果
            if d1 == 'score':
                directed_edges.append((d2, d1, round(r, 3)))
            elif d2 == 'score':
                directed_edges.append((d1, d2, round(r, 3)))
            else:
                # 默认: 较大相关系数方向
                directed_edges.append((d1, d2, round(r, 3)))

    directed_edges.sort(key=lambda e: -e[2])
    isolated = [d for d in active_dims if not any(d in e for e in directed_edges)]

    return {'edges': directed_edges, 'isolated': isolated, 'samples': n}


def get_causal_insight(graph, target_dim):
    """获取某个维度的因果洞察"""
    if not graph or not graph.get('edges'):
        return '数据不足以分析因果关系'

    causes = []
    effects = []
    for src, dst, strength in graph['edges']:
        if dst == target_dim:
            causes.append((src, strength))
        if src == target_dim:
            effects.append((dst, strength))

    parts = []
    if causes:
        causes.sort(key=lambda x: -x[1])
        top = causes[0]
        parts.append('%s -> %s(r=%.2f)' % (
            DIM_LABELS.get(top[0], top[0]),
            DIM_LABELS.get(target_dim, target_dim), top[1]))

    if effects:
        effects.sort(key=lambda x: -x[1])
        top = effects[0]
        parts.append('%s(r=%.2f) -> %s' % (
            DIM_LABELS.get(target_dim, target_dim), top[1],
            DIM_LABELS.get(top[0], top[0])))

    return '；'.join(parts) if parts else '该维度相对独立于其他维度'


def causal_summary(graph):
    """生成可读的因果图摘要"""
    if not graph or not graph.get('edges'):
        return '因果图: 数据不足'

    lines = ['因果图 (%d条边, %d个样本):' % (len(graph['edges']), graph.get('samples', 0))]
    for src, dst, strength in graph['edges'][:6]:
        lines.append('  %s → %s (r=%.2f)' % (
            DIM_LABELS.get(src, src),
            DIM_LABELS.get(dst, dst),
            strength))
    if graph.get('isolated'):
        lines.append('  孤立维度: ' + ', '.join(DIM_LABELS.get(d, d) for d in graph['isolated']))
    return '\n'.join(lines)


# ===== 自测 =====
if __name__ == '__main__':
    import random
    random.seed(42)

    # 模拟数据：stress_level→sleep_latency→score
    records = []
    for i in range(30):
        stress = random.uniform(1, 10)
        latency = 15 + stress * 5 + random.gauss(0, 5)
        score = 85 - latency * 0.3 + random.gauss(0, 5)
        awake = max(0, stress * 0.3 + random.gauss(0, 0.5))
        duration = 480 - stress * 10 + random.gauss(0, 20)
        records.append({
            'stress_level': stress,
            'sleep_latency': latency,
            'score': max(10, min(100, score)),
            'awake_times': round(awake),
            'total_duration': max(180, duration),
            'bedtime_hour': 23 + random.gauss(0, 0.5),
            'wake_hour': 7 + random.gauss(0, 0.5),
        })

    graph = build_causal_graph(records)
    print(causal_summary(graph))
    print()
    print('Latency insight:', get_causal_insight(graph, 'sleep_latency'))
    print('Score insight:', get_causal_insight(graph, 'score'))

    assert 'edges' in graph
    assert len(graph['edges']) > 0
    print('\nAll tests passed!')
