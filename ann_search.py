#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ann_search.py — FAISS / 近似最近邻搜索 (v7.5+)
原理: Meta FAISS — 用LSH索引做近似最近邻搜索，O(log n)而不是O(n)
落地: 从用户历史中找"和今晚最相似的过去夜晚"，参考其评分和结果

用法:
  from ann_search import build_ann_index, search_similar_nights, ann_summary
  index = build_ann_index(records)
  similar = search_similar_nights(index, tonight_data)
"""

import hashlib
import math
import random
from collections import defaultdict

DIMENSIONS = [
    'sleep_latency', 'awake_times', 'total_duration',
    'stress_level', 'bedtime_hour', 'wake_hour', 'score',
]


def _to_vector(rec, dims=None):
    if dims is None:
        dims = DIMENSIONS
    vec = []
    for d in dims:
        v = rec.get(d) if isinstance(rec, dict) else 0
        if v is not None:
            try:
                vec.append(float(v))
            except (ValueError, TypeError):
                vec.append(0.0)
        else:
            vec.append(0.0)
    return vec


def _normalize(vec):
    norm = math.sqrt(max(1e-10, sum(v ** 2 for v in vec)))
    return [v / norm for v in vec]


def _cosine_sim(a, b):
    min_len = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(min_len))
    na = math.sqrt(max(1e-10, sum(v ** 2 for v in a)))
    nb = math.sqrt(max(1e-10, sum(v ** 2 for v in b)))
    return dot / (na * nb)


def _lsh_hash(vec, n_hash_bits=6, seed=42):
    """用随机超平面生成LSH签名 (simhash)"""
    rng = random.Random(seed)
    dim = len(vec)
    bits = []
    for b in range(n_hash_bits):
        # 随机超平面
        plane = [rng.gauss(0, 1) for _ in range(dim)]
        dot = sum(vec[i] * plane[i] for i in range(dim))
        bits.append('1' if dot >= 0 else '0')
    return ''.join(bits)


def _multi_lsh(vec, n_tables=3, bits_per_table=4):
    """多表LSH"""
    signatures = []
    for t in range(n_tables):
        sig = _lsh_hash(vec, bits_per_table, seed=t * 100 + 42)
        signatures.append((t, sig))
    return signatures


def build_ann_index(records, n_tables=3, bits_per_table=4):
    """构建ANN索引

    用多表LSH: 每个hash表是一个桶映射

    Args:
        records: list[dict] — 历史睡眠记录（必须含index或有序）
        n_tables: int — hash表数量
        bits_per_table: int — 每个hash表的位数

    Returns:
        dict: {hash_tables, vectors, n_records, active_dims}
    """
    # 确定活跃维度
    vecs_by_dim = {d: [] for d in DIMENSIONS}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for d in DIMENSIONS:
            v = rec.get(d)
            if v is not None:
                try:
                    vecs_by_dim[d].append(float(v))
                except (ValueError, TypeError):
                    pass

    active = [d for d in DIMENSIONS if len(vecs_by_dim[d]) >= 2]
    if len(active) < 3:
        return {'error': '数据不足', 'n_records': len(records)}

    # 构建hash表
    hash_tables = [defaultdict(list) for _ in range(n_tables)]
    vectors = []

    for idx, rec in enumerate(records):
        vec = _to_vector(rec, active)
        vec_norm = _normalize(vec)
        vectors.append({'vec': vec_norm, 'record': rec, 'idx': idx})

        sigs = _multi_lsh(vec_norm, n_tables, bits_per_table)
        for t, sig in sigs:
            hash_tables[t][sig].append(idx)

    return {
        'hash_tables': [{k: v for k, v in table.items()} for table in hash_tables],
        'vectors': vectors,
        'n_records': len(records),
        'active_dims': active,
        'n_tables': n_tables,
        'bits_per_table': bits_per_table,
    }


def search_similar_nights(index, query, top_k=3, max_bucket_scan=50):
    """搜索最相似的夜晚

    Args:
        index: dict — build_ann_index 的返回
        query: dict — 今晚的数据
        top_k: int — 返回前K个最相似的
        max_bucket_scan: int — 最多扫描多少候选

    Returns:
        list[dict] — [{idx, score, record}, ...]
    """
    if 'error' in index:
        return []

    active = index.get('active_dims', [])
    if not active:
        return []

    vec = _to_vector(query, active)
    vec_norm = _normalize(vec)
    if not vec_norm:
        return []

    hash_tables = index.get('hash_tables', [])
    vectors = index.get('vectors', [])

    # 多表LSH：从所有同桶中收集候选
    candidates = set()
    sigs = _multi_lsh(vec_norm, len(hash_tables), index.get('bits_per_table', 4))
    for t, sig in sigs:
        if t < len(hash_tables):
            bucket = hash_tables[t].get(sig, [])
            candidates.update(bucket)

    # 如果候选太少，fallback到随机采样
    if len(candidates) < top_k:
        candidates = set(range(len(vectors)))
        if len(candidates) > max_bucket_scan:
            candidates = set(random.sample(list(candidates), max_bucket_scan))

    # 对候选计算精确余弦相似度
    scored = []
    for idx in candidates:
        if idx >= len(vectors):
            continue
        sim = _cosine_sim(vec_norm, vectors[idx]['vec'])
        scored.append({
            'idx': idx,
            'score': round(sim, 3),
            'record': vectors[idx]['record'],
        })

    scored.sort(key=lambda x: -x['score'])
    return scored[:top_k]


def ann_summary(index):
    """摘要"""
    if 'error' in index:
        return 'ANN: %s' % index['error']
    return 'ANN: %d条记录, %d个hash表, %d位/表' % (
        index.get('n_records', 0),
        index.get('n_tables', 0),
        index.get('bits_per_table', 0),
    )


# ===== 自测 =====
if __name__ == '__main__':
    import random
    random.seed(42)

    # 模拟数据
    records = []
    for i in range(50):
        stress = random.gauss(5, 2)
        latency = 30 + stress * 3 + random.gauss(0, 8)
        score = 75 - stress * 3 - latency * 0.1 + random.gauss(0, 6)
        records.append({
            'date': 'day_%d' % i,
            'stress_level': stress,
            'sleep_latency': latency,
            'score': max(10, min(100, score)),
            'awake_times': max(0, stress * 0.3 + random.gauss(0, 0.5)),
            'total_duration': 480 - stress * 10 + random.gauss(0, 20),
            'bedtime_hour': 23 + random.gauss(0, 0.5),
            'wake_hour': 7 + random.gauss(0, 0.3),
        })

    index = build_ann_index(records)
    print(ann_summary(index))

    # 查询: 今晚压力大
    tonight = {'stress_level': 8.5, 'sleep_latency': 55, 'score': 40}
    similar = search_similar_nights(index, tonight, top_k=3)

    for s in similar:
        rec = s['record']
        print('  sim=%.3f: stress=%.1f latency=%.1f score=%.0f' % (
            s['score'], rec.get('stress_level', 0),
            rec.get('sleep_latency', 0), rec.get('score', 0)))

    assert len(similar) > 0
    assert 'error' not in index

    # 测试数据不足
    m2 = build_ann_index([{'stress_level': 5}])
    assert 'error' in m2

    print('\nAll tests passed!')
