#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
routing_transformer.py — Routing Transformer聚类路由 (v7.5+)
原理: Google Routing Transformer — k-means聚类路由，分组处理专家输出
落地: 将10位专家按评分模式聚类，同一簇取聚合值减少冗余

用法:
  from routing_transformer import route_experts, routing_summary
  routed = route_experts(round2)
"""

import math


def _zscore_weights(score_map):
    """评分归一化"""
    vals = sorted(score_map.values())
    if len(vals) < 2:
        return score_map
    mu = sum(vals) / len(vals)
    s = math.sqrt(max(1e-10, sum((v - mu)**2 for v in vals) / (len(vals) - 1)))
    return {k: round((v - mu) / s, 3) for k, v in score_map.items()}


def route_experts(round2, k=None):
    """将专家按评分模式聚类路由

    Args:
        round2: dict — {expert_name: {score, confidence, ...}}
        k: int — 聚类数，默认自动

    Returns:
        dict: {routes, centroids, aggregated, routing_efficiency}
    """
    if not round2:
        return {'note': '无专家数据', 'routes': {}}

    # 提取专家评分
    experts = {}
    for name, detail in round2.items():
        if isinstance(detail, dict) and 'score' in detail:
            score = detail.get('score', 0.5)
            conf = detail.get('confidence', 0.5)
            risk = 1.0 if detail.get('risk_level', '') in ('high', 'medium') else 0.0
            experts[name] = {'score': score, 'confidence': conf, 'risk': risk}

    if len(experts) < 3:
        # 专家太少，不聚类
        return {
            'routes': {n: {'cluster': 0, 'score': v['score'],
                           'confidence': v['confidence']} for n, v in experts.items()},
            'n_clusters': 1,
            'centroids': {0: {'score': 0.5, 'count': len(experts)}},
            'aggregated': {n: v['score'] for n, v in experts.items()},
            'routing_efficiency': 1.0,
        }

    names = list(experts.keys())
    scores = [experts[n]['score'] for n in names]
    confs = [experts[n]['confidence'] for n in names]

    # k-means聚类（纯Python）
    k = k or max(2, min(4, len(experts) // 3 + 1))

    # 初始化质心：按评分排序均匀取
    sorted_idx = sorted(range(len(names)), key=lambda i: scores[i])
    step = max(1, len(names) // k)
    centroids = []
    for i in range(k):
        idx = sorted_idx[min(i * step, len(names) - 1)]
        centroids.append([scores[idx], confs[idx]])

    # 迭代k-means
    labels = [0] * len(names)
    for _ in range(20):
        new_labels = []
        for i in range(len(names)):
            best_c = 0
            best_d = float('inf')
            for c in range(k):
                d = (scores[i] - centroids[c][0])**2 + (confs[i] - centroids[c][1])**2
                if d < best_d:
                    best_d = d
                    best_c = c
            new_labels.append(best_c)
        if new_labels == labels:
            break
        labels = new_labels
        # 更新质心
        for c in range(k):
            members = [i for i in range(len(names)) if labels[i] == c]
            if members:
                centroids[c] = [
                    sum(scores[i] for i in members) / len(members),
                    sum(confs[i] for i in members) / len(members)
                ]

    # 构建路由结果
    routes = {}
    cluster_members = {c: [] for c in range(k)}
    for i, name in enumerate(names):
        c = labels[i]
        routes[name] = {
            'cluster': c,
            'score': scores[i],
            'confidence': confs[i],
            'centroid_dist': round(math.sqrt(
                (scores[i] - centroids[c][0])**2 + (confs[i] - centroids[c][1])**2), 3)
        }
        cluster_members[c].append(name)

    # 聚合：同一簇的取归一化投票
    aggregated = {}
    for c, members in cluster_members.items():
        if len(members) == 1:
            aggregated[members[0]] = experts[members[0]]['score']
        else:
            # 同簇取加权平均
            total_w = sum(experts[m]['confidence'] for m in members)
            weighted = sum(experts[m]['score'] * experts[m]['confidence'] for m in members)
            agg_score = weighted / max(0.01, total_w)
            for m in members:
                aggregated[m] = round(agg_score, 3)

    # 路由效率: 1 - (同簇数/总对数)
    total_pairs = len(experts) * (len(experts) - 1) / 2
    same_cluster_pairs = sum(len(v) * (len(v) - 1) / 2 for v in cluster_members.values())
    efficiency = 1.0 - (same_cluster_pairs / max(1, total_pairs))

    return {
        'routes': routes,
        'n_clusters': k,
        'centroids': {c: {'score': round(v[0], 3), 'confidence': round(v[1], 3),
                           'count': len(cluster_members[c])}
                      for c, v in enumerate(centroids)},
        'aggregated': aggregated,
        'routing_efficiency': round(efficiency, 3),
        'cluster_members': {str(c): ms for c, ms in cluster_members.items()},
    }


def routing_summary(result):
    """摘要"""
    if 'note' in result:
        return 'Routing: %s' % result['note']
    return 'Routing: %d簇, 效率=%.2f, 聚合%d专家' % (
        result['n_clusters'],
        result['routing_efficiency'],
        len(result['aggregated']),
    )


# ===== 自测 =====
if __name__ == '__main__':
    print('=== Routing Transformer Test ===\n')

    round2 = {}
    import random
    random.seed(42)

    experts = ['ClinicalPsychologist', 'CBT', 'SleepPhysician', 'Chronobiologist',
               'LifeScientist', 'RiskManager', 'StressRelaxation',
               'ExerciseRehab', 'CardiacMonitor', 'NutriMetabolism']

    # 模拟: 心理类评分接近, 生理类接近, 风险类单独
    for i, name in enumerate(experts):
        if name in ('ClinicalPsychologist', 'CBT', 'StressRelaxation'):
            score = 0.6 + random.random() * 0.15
        elif name in ('SleepPhysician', 'Chronobiologist', 'LifeScientist'):
            score = 0.5 + random.random() * 0.15
        elif name == 'RiskManager':
            score = 0.8 + random.random() * 0.1
        else:
            score = 0.4 + random.random() * 0.2
        round2[name] = {'score': score, 'confidence': 0.6 + random.random() * 0.3,
                        'risk_level': 'high' if name == 'RiskManager' else 'low'}

    result = route_experts(round2)
    print(routing_summary(result))
    for c, info in result['centroids'].items():
        print('  Cluster %d: score=%.3f, conf=%.3f, count=%d' % (
            c, info['score'], info['confidence'], info['count']))

    assert result['n_clusters'] >= 2
    assert len(result['aggregated']) == 10

    # 太少专家
    r2 = route_experts({'CBT': {'score': 0.5}})
    assert r2['n_clusters'] == 1

    print('\nAll tests passed!')
