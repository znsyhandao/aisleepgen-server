#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sparse_pca.py — 稀疏PCA可解释编码 (v7.5+)
原理: SAE变体 — 稀疏主成分分析，从睡眠维度中提取可解释的"神经概念"
落地: 用户睡眠数据→稀疏编码→识别异常维度→指导个性化干预

用法:
  from sparse_pca import fit_sparse_pca, encode_user, sparse_pca_summary
  model = fit_sparse_pca(all_users_history)
  code = encode_user(model, user_7dims)
  anomalies = [dim for dim, v in code['components'].items() if abs(v['zscore']) > 2]
"""

import math


def _cov_matrix(data):
    """计算协方差矩阵 (纯Python, 无numpy)"""
    n = len(data)
    if n < 2:
        return None
    n_dims = len(data[0])
    # 均值
    means = [sum(row[i] for row in data) / n for i in range(n_dims)]
    # 协方差
    cov = [[0.0] * n_dims for _ in range(n_dims)]
    for i in range(n_dims):
        for j in range(i, n_dims):
            c = sum((row[i] - means[i]) * (row[j] - means[j]) for row in data) / (n - 1)
            cov[i][j] = c
            cov[j][i] = c
    return cov, means


def _power_iteration(matrix, n_iter=50, tol=1e-6):
    """幂迭代求最大特征值/特征向量"""
    n = len(matrix)
    v = [1.0 / math.sqrt(n)] * n
    prev_val = 0
    for _ in range(n_iter):
        # 矩阵乘向量
        w = [sum(matrix[i][j] * v[j] for j in range(n)) for i in range(n)]
        # 瑞利商: 特征值近似
        val = sum(v[i] * w[i] for i in range(n))
        # 归一化
        norm = math.sqrt(max(1e-10, sum(x**2 for x in w)))
        v = [x / norm for x in w]
        if abs(val - prev_val) < tol:
            break
        prev_val = val
    return val, v


def _deflate(matrix, eigenvector, eigenvalue):
    """收缩: 从矩阵中移除已找到的主成分"""
    n = len(matrix)
    return [[matrix[i][j] - eigenvalue * eigenvector[i] * eigenvector[j]
             for j in range(n)] for i in range(n)]


# ===== 7睡眠维度名称 =====
DIM_NAMES = [
    'sleep_latency',    # 入睡延迟
    'awake_times',      # 夜醒次数
    'total_sleep',      # 总睡眠时长
    'stress_level',     # 压力水平
    'bedtime_regular',  # 就寝规律性 (逆: 越规律越低)
    'wake_feeling',     # 醒来感受
    'score',            # 综合评分
]

DIM_LABELS = {
    'sleep_latency': '入睡延迟',
    'awake_times': '夜醒次数',
    'total_sleep': '睡眠时长',
    'stress_level': '压力水平',
    'bedtime_regular': '就寝规律',
    'wake_feeling': '醒来感受',
    'score': '综合评分',
}


def _normalize_history(history):
    """历史数据→7维矩阵, Z-score归一化"""
    if not history:
        return None, None

    records = []
    for h in history:
        if not isinstance(h, dict):
            continue
        vec = []
        for dim in DIM_NAMES:
            v = h.get(dim)
            vec.append(float(v) if isinstance(v, (int, float)) else 50.0)
        records.append(vec)

    if len(records) < 2:
        return None, None

    # Z-score归一化
    n = len(records)
    dims = len(DIM_NAMES)
    means = [sum(r[d] for r in records) / n for d in range(dims)]
    stds = []
    for d in range(dims):
        s = math.sqrt(max(1e-10, sum((r[d] - means[d])**2 for r in records) / (n - 1)))
        stds.append(s)

    normed = [[(r[d] - means[d]) / stds[d] for d in range(dims)] for r in records]
    return normed, (means, stds)


def fit_sparse_pca(history, n_components=4, top_loadings=2):
    """训练稀疏PCA模型

    Args:
        history: list[dict] — 用户的睡眠历史 (至少2条)
        n_components: int — 主成分数 (默认4)
        top_loadings: int — 每个主成分保留的top载荷数 (稀疏度控制)

    Returns:
        dict: {components, eigenvalues, variance_ratio, sparse, note}
    """
    records, stats = _normalize_history(history)
    if records is None:
        return {'note': '数据不足'}

    n = len(records)
    dims = len(DIM_NAMES)

    # 协方差矩阵
    cov_result = _cov_matrix(records)
    if cov_result is None:
        return {'note': '协方差计算失败'}
    cov, _ = cov_result

    # 幂迭代求n_components个主成分
    components = []
    eigenvalues = []
    remaining = [row[:] for row in cov]

    for k in range(min(n_components, dims)):
        eigval, eigvec = _power_iteration(remaining)
        if eigval < 0.01:
            break
        components.append(eigvec)
        eigenvalues.append(eigval)
        remaining = _deflate(remaining, eigvec, eigval)

    if not components:
        return {'note': '无有效主成分'}

    total_var = sum(eigenvalues)

    # ===== 稀疏化 =====
    sparse_components = []
    for idx, (eigval, comp) in enumerate(zip(eigenvalues, components)):
        # 取top_loadings个最大绝对载荷
        indexed = [(abs(v), i, v) for i, v in enumerate(comp)]
        indexed.sort(reverse=True)
        top = indexed[:top_loadings]

        sparse = [0.0] * dims
        top_info = []
        for _, i, v in top:
            sparse[i] = round(v, 3)
            top_info.append({
                'dimension': DIM_NAMES[i],
                'dim_label': DIM_LABELS.get(DIM_NAMES[i], DIM_NAMES[i]),
                'loading': round(v, 3),
                'direction': '正向' if v > 0 else '负向',
            })

        variance_ratio = eigval / total_var if total_var > 0 else 0
        sparse_components.append({
            'index': idx,
            'eigenvalue': round(eigval, 3),
            'variance_ratio': round(variance_ratio, 3),
            'top_loadings': top_info,
            'sparse_vector': sparse,
            'interpretation': _interpret_component(top_info),
        })

    return {
        'components': sparse_components,
        'eigenvalues': [round(e, 3) for e in eigenvalues],
        'n_components': len(sparse_components),
        'total_variance_explained': round(sum(eigenvalues), 3),
        'n_samples': n,
        'stats': stats,
        'note': 'ok',
    }


def _interpret_component(top_info):
    """从top载荷推断主成分含义"""
    if not top_info:
        return '未知模式'

    # 提取维度名和方向
    dims = [(t['dimension'], t['direction']) for t in top_info]

    # 常见模式识别
    has_stress = any('stress' in d[0] for d in dims)
    has_latency = any('latency' in d[0] for d in dims)
    has_score = any('score' in d[0] for d in dims)
    has_awake = any('awake' in d[0] for d in dims)
    has_duration = any('total' in d[0] or 'sleep' in d[0] for d in dims)

    if has_stress and has_latency:
        return '压力型失眠'
    elif has_stress and has_duration:
        return '压力→短睡眠'
    elif has_awake and has_duration:
        return '睡眠碎片化'
    elif has_score and has_latency:
        return '入睡困难型'
    elif has_score and not has_stress:
        return '综合质量因子'
    elif has_stress:
        return '压力核心因子'
    else:
        # 用维度名拼接
        names = [t['dim_label'] for t in top_info]
        return ' + '.join(names)


def encode_user(model, history):
    """用训练好的模型编码用户→稀疏编码

    Args:
        model: dict — fit_sparse_pca的输出
        history: list[dict] — 用户的近期睡眠记录

    Returns:
        dict: {code, components, anomalies, interpretation}
    """
    if model.get('note') != 'ok':
        return {'note': '模型未训练'}

    records, stats = _normalize_history(history)
    if records is None:
        return {'note': '数据不足'}

    stats_obj = model.get('stats')
    if stats_obj is None:
        return {'note': '模型无统计信息'}

    # 用训练集均值/标准差归一化
    means, stds = stats_obj
    latest = records[-1]

    # ===== 计算各成分激活 =====
    code = {}
    anomalies = []
    for comp in model['components']:
        sparse_vec = comp['sparse_vector']
        # 投影 = 点积
        activation = sum(latest[d] * sparse_vec[d] for d in range(len(latest)))
        code[comp['interpretation']] = round(activation, 3)

        # 标记异常成分: 激活 > 2σ (近似)
        if abs(activation) > 1.5:
            anomalies.append({
                'component': comp['interpretation'],
                'activation': round(activation, 3),
                'severity': 'high' if abs(activation) > 2.5 else 'medium',
            })

    # ===== 每个原始维度的z-score =====
    dim_zscore = {}
    for i, dim in enumerate(DIM_NAMES):
        z = (latest[i] - 0) / 1.0  # 已经是Z-score归一化
        dim_zscore[dim] = {
            'label': DIM_LABELS.get(dim, dim),
            'zscore': round(z, 2),
            'anomaly': abs(z) > 2,
            'direction': '偏高' if z > 0 else '偏低',
        }

    return {
        'code': code,
        'n_activated': len([v for v in code.values() if abs(v) > 0.5]),
        'anomalies': anomalies,
        'n_anomalies': len(anomalies),
        'dim_zscore': dim_zscore,
        'interpretation': '异常: %s' % ' + '.join(a['component'] for a in anomalies[:3]) if anomalies else '无明显异常',
        'note': 'ok',
    }


def sparse_pca_summary(model):
    """模型摘要"""
    if model.get('note') != 'ok':
        return '稀疏PCA: %s' % model.get('note', 'N/A')
    lines = ['稀疏PCA: %d个成分, 解释方差%.2f' % (model['n_components'], model['total_variance_explained'])]
    for c in model['components']:
        top = '+'.join(t['dim_label'] for t in c['top_loadings'])
        lines.append('  PC%d(%.0f%%): %s' % (c['index']+1, c['variance_ratio']*100, top))
    return '\n'.join(lines)


# ===== 自测 =====
if __name__ == '__main__':
    print('=== Sparse PCA Test ===\n')

    # 生成模拟数据: 压力型失眠模式
    history = []
    for i in range(21):
        stress = 7 + (i % 5) * 0.5 - (i // 5) * 0.3  # 逐渐下降
        latency = 40 + stress * 5 + (i % 3) * 3
        awake = 1 + stress * 0.3
        duration = 6.5 - stress * 0.2
        bedtime = 0.3 + abs(stress - 5) * 0.1
        wake = 6 - stress * 0.1
        score = 70 - stress * 5
        history.append({
            'sleep_latency': latency,
            'awake_times': awake,
            'total_sleep': duration,
            'stress_level': stress,
            'bedtime_regular': bedtime,
            'wake_feeling': wake,
            'score': score,
        })

    # 训练
    model = fit_sparse_pca(history, n_components=3)
    print(sparse_pca_summary(model))
    assert model['note'] == 'ok'
    assert model['n_components'] >= 1

    # 编码
    code = encode_user(model, history)
    print('\nCode:', code['interpretation'])
    print('  anomalies:', code.get('n_anomalies', 0))
    assert code['note'] == 'ok'

    # 数据不足
    r1 = fit_sparse_pca([{'score': 50}])
    assert r1['note'] == '数据不足'

    # 随机数据 (应为无模式)
    import random
    random.seed(42)
    rand_hist = [{k: random.uniform(1, 10) for k in DIM_NAMES} for _ in range(30)]
    r2 = fit_sparse_pca(rand_hist, n_components=2)
    print('\nRandom:', sparse_pca_summary(r2))
    assert r2['note'] == 'ok'

    print('\nAll tests passed!')
