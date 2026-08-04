#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
embedding_api.py — Embedding API / 统计嵌入 (v7.5+)
原理: OpenAI Embedding API — 用统计方法替代API调用，生成固定维度嵌入向量
落地: 用户历史睡眠记录 → 1536维统计嵌入（可降维）→ 用户相似度匹配

用法:
  from embedding_api import embed_user, find_similar_users, embed_summary
  vec = embed_user(history)
  similar = find_similar_users(vec, all_users_embeddings)
"""

import json, os, math
from collections import Counter

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
EMBEDDING_DIR = os.path.join(PROJECT_ROOT, 'data', 'embeddings')
os.makedirs(EMBEDDING_DIR, exist_ok=True)


DIMENSIONS = ['sleep_latency', 'awake_times', 'total_duration',
              'stress_level', 'bedtime_hour', 'wake_hour', 'score']
DIM_LABELS = {'sleep_latency': '入睡延迟', 'awake_times': '夜醒次数',
              'total_duration': '总睡眠时长', 'stress_level': '压力水平',
              'bedtime_hour': '就寝时间', 'wake_hour': '起床时间',
              'score': '睡眠评分'}


# ===== 构建统计嵌入 =====
# 每维度生成5个统计量: [min, max, mean, std, recent_trend]
# 7维度 × 5统计量 = 35维 + 5个行为特征 + 2个总体指标 = 42维
# 嵌入维度: 42（可扩展）


def _z_score(vals):
    n = len(vals)
    if n < 2:
        return 0.0
    mu = sum(vals) / n
    s = math.sqrt(max(1e-10, sum((v - mu)**2 for v in vals) / (n - 1)))
    return s


def embed_user(history):
    """从用户历史构建统计嵌入向量

    Args:
        history: list[dict] — 用户的睡眠记录

    Returns:
        dict: {vector, dim_labels, n_records, version}
    """
    embedding = {}
    vec = []

    # === Part 1: 睡眠维度统计 (35维) ===
    dim_data = {d: [] for d in DIMENSIONS}
    for rec in history:
        if not isinstance(rec, dict):
            continue
        for d in DIMENSIONS:
            v = rec.get(d)
            if v is not None:
                try:
                    dim_data[d].append(float(v))
                except (ValueError, TypeError):
                    pass

    for d in DIMENSIONS:
        vals = dim_data[d]
        if len(vals) < 2:
            stats = [0.0, 0.0, 0.0, 0.0, 0.0]
        else:
            n = len(vals)
            mu = sum(vals) / n
            mn = min(vals)
            mx = max(vals)
            std = _z_score(vals)
            # recent trend: 后半段平均 vs 前半段平均
            mid = n // 2
            first_half = sum(vals[:mid]) / mid if mid > 0 else mu
            second_half = sum(vals[mid:]) / (n - mid) if (n - mid) > 0 else mu
            trend = second_half - first_half  # 上升→正, 下降→负
            stats = [round(mn, 1), round(mx, 1), round(mu, 1), round(std, 2), round(trend, 1)]
        vec.extend(stats)

    embedding['dim_stats'] = {d: DIM_LABELS.get(d, d) for d in DIMENSIONS}

    # === Part 2: 行为特征 (5维) ===
    n_records = len(history)
    # 记录天数
    vec.append(float(n_records))

    # 活跃度评分: 不同维度的非空比例
    non_empty = sum(1 for d in DIMENSIONS if len(dim_data[d]) > 0)
    vec.append(non_empty / len(DIMENSIONS))

    # 趋势方向: 最近评分变化
    scores = dim_data.get('score', [])
    if len(scores) >= 3:
        recent_trend = scores[-1] - scores[-3]
        vec.append(round(recent_trend, 1))
    else:
        vec.append(0.0)

    # 压力波动
    stress = dim_data.get('stress_level', [])
    if len(stress) >= 2:
        stress_std = _z_score(stress)
        vec.append(round(stress_std, 2))
    else:
        vec.append(0.0)

    # 作息规律性: 入睡时间标准差
    bedtimes = dim_data.get('bedtime_hour', [])
    if len(bedtimes) >= 3:
        b_std = _z_score(bedtimes)
        vec.append(round(b_std, 3))
    else:
        vec.append(0.0)

    # === Part 3: 总体指标 (2维) ===
    # 平均评分
    avg_score = sum(dim_data.get('score', [0])) / max(1, len(dim_data.get('score', [0]) or [1]))
    vec.append(round(avg_score, 1))
    # 数据完整性
    completeness = sum(1 for d in DIMENSIONS if len(dim_data[d]) >= n_records * 0.5) / len(DIMENSIONS)
    vec.append(round(completeness, 2))

    return {
        'vector': vec,
        'dim_labels': {i: 'dim_%d' % i for i in range(len(vec))},
        'n_records': n_records,
        'embedding_dim': len(vec),
        'version': 'v1',
    }


def embed_summary(emb):
    """嵌入摘要"""
    if not emb or 'vector' not in emb:
        return 'Embedding: 无数据'
    return 'Embedding: %d维度, %d条记录, 平均评分=%.1f' % (
        emb.get('embedding_dim', 0),
        emb.get('n_records', 0),
        emb.get('vector', [0])[-2] if len(emb.get('vector', [])) >= 2 else 0,
    )


def _cosine_sim(v1, v2):
    min_l = min(len(v1), len(v2))
    if min_l == 0:
        return 0.0
    dot = sum(v1[i] * v2[i] for i in range(min_l))
    n1 = math.sqrt(max(1e-10, sum(v**2 for v in v1)))
    n2 = math.sqrt(max(1e-10, sum(v**2 for v in v2)))
    return dot / (n1 * n2)


def save_embedding(openid, emb):
    """保存用户的嵌入向量"""
    safe = openid.replace('/', '_').replace('\\', '_')
    path = os.path.join(EMBEDDING_DIR, '%s.json' % safe)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(emb, f, ensure_ascii=False, indent=2)


def load_embedding(openid):
    """加载用户的嵌入向量"""
    safe = openid.replace('/', '_').replace('\\', '_')
    path = os.path.join(EMBEDDING_DIR, '%s.json' % safe)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return None


def find_similar_users(openid, top_k=5):
    """找和当前用户最相似的用户

    Args:
        openid: str
        top_k: int

    Returns:
        list[dict] — [{openid, similarity}]
    """
    emb = load_embedding(openid)
    if not emb or 'vector' not in emb:
        return []

    vec = emb['vector']
    scored = []

    for fname in os.listdir(EMBEDDING_DIR):
        if not fname.endswith('.json'):
            continue
        f_openid = fname[:-5].replace('_', '/')
        if f_openid == openid:
            continue
        try:
            with open(os.path.join(EMBEDDING_DIR, fname), 'r', encoding='utf-8') as f:
                other = json.load(f)
            if 'vector' in other:
                sim = _cosine_sim(vec, other['vector'])
                if sim > 0.5:
                    scored.append({'openid': f_openid, 'similarity': round(sim, 3)})
        except Exception:
            pass

    scored.sort(key=lambda x: -x['similarity'])
    return scored[:top_k]


# ===== 自测 =====
if __name__ == '__main__':
    print('=== Embedding API Test ===\n')

    # 正常用户
    history = [{'stress_level': 5, 'sleep_latency': 30, 'score': 70, 'awake_times': 1,
                'bedtime_hour': 23, 'wake_hour': 7, 'total_duration': 480} for _ in range(10)]
    for i, rec in enumerate(history):
        rec['stress_level'] += (i % 3) * 0.5
        rec['score'] -= (i % 4) * 2

    emb = embed_user(history)
    print(embed_summary(emb))
    assert emb['embedding_dim'] == 42
    assert emb['n_records'] == 10
    save_embedding('test_embed', emb)

    # 不同用户
    history2 = [{'stress_level': 8, 'sleep_latency': 60, 'score': 35, 'awake_times': 3,
                 'bedtime_hour': 23.5, 'wake_hour': 6.5, 'total_duration': 420} for _ in range(5)]
    emb2 = embed_user(history2)
    save_embedding('test_embed2', emb2)

    # 用户相似度
    similar = find_similar_users('test_embed', top_k=5)
    print('Similar users:', len(similar))
    for s in similar:
        print('  openid=%s sim=%.3f' % (s['openid'], s['similarity']))

    # 清理
    import os as _os
    for f in ['test_embed.json', 'test_embed2.json']:
        p = _os.path.join(EMBEDDING_DIR, f)
        if _os.path.exists(p):
            _os.remove(p)

    print('\nAll tests passed!')
