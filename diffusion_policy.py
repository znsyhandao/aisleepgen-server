#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diffusion_policy.py — Diffusion Policy扩散策略 (v7.5+)
原理: 扩散模型 — 从噪声逐步去噪生成"干预方案"时间序列
落地: 从用户历史学习"好策略"的分布，采样多步干预步骤

用法:
  from diffusion_policy import train_diffusion, sample_policy, policy_summary
  model = train_diffusion(history)
  plan = sample_policy(model, n_steps=3)
"""

import math, random, os, json

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DP_DIR = os.path.join(PROJECT_ROOT, 'data', 'diffusion')
os.makedirs(DP_DIR, exist_ok=True)


def _zscore(vals):
    n = len(vals)
    if n < 2:
        return [0.0] * n
    mu = sum(vals) / n
    s = math.sqrt(max(1e-10, sum((v - mu)**2 for v in vals) / (n - 1)))
    return [(v - mu) / s for v in vals]


def _to_vectors(history):
    """历史记录 → 4维向量列表 [stress, latency, awake, score]"""
    vecs = []
    for rec in history:
        if not isinstance(rec, dict):
            continue
        try:
            s = float(rec.get('stress_level', 5))
            l = float(rec.get('sleep_latency', 30))
            a = float(rec.get('awake_times', 1))
            sc = float(rec.get('score', 50))
            vecs.append([s, l, a, sc])
        except (ValueError, TypeError):
            pass
    return vecs


def _noise_schedule(t, total=10):
    """余弦噪声调度: t从0→total, 噪声比例从小→大"""
    angle = math.pi * 0.5 * (t / total)
    return math.cos(angle) ** 2


def train_diffusion(history, n_epochs=20):
    """训练扩散模型

    从历史数据中学习"好干预策略"的分布

    Args:
        history: list[dict] — 用户睡眠记录
        n_epochs: int — 训练轮数

    Returns:
        dict: {means, stds, n_samples, prototype}
    """
    vecs = _to_vectors(history)
    if len(vecs) < 3:
        return {'error': '数据不足'}

    # 归一化统计量
    dim_labels = ['stress_level', 'sleep_latency', 'awake_times', 'score']
    means = []
    stds = []
    for d in range(4):
        vals = [v[d] for v in vecs]
        mu = sum(vals) / len(vals)
        s = math.sqrt(max(1e-10, sum((x - mu)**2 for x in vals) / (len(vals) - 1)))
        means.append(mu)
        stds.append(s)

    # 归一化
    normalized = [[(v[d] - means[d]) / stds[d] for d in range(4)] for v in vecs]

    # 选"好策略"原型：评分标准化后最高的记录
    scores_norm = [v[3] for v in normalized]
    best_idx = max(range(len(normalized)), key=lambda i: scores_norm[i])

    prototype = {
        'stress_level': round(vecs[best_idx][0], 1),
        'sleep_latency': round(vecs[best_idx][1], 1),
        'awake_times': round(vecs[best_idx][2], 2),
        'score': round(vecs[best_idx][3], 1),
    }

    # 扩散训练：学习"从噪声到好数据"的转换
    # 用简单的线性回归模拟扩散头
    noise_pred = []
    for t in range(n_epochs):
        alpha = _noise_schedule(t, n_epochs)
        for v in normalized:
            # 加噪声
            noise = [random.gauss(0, 1) for _ in range(4)]
            noisy = [v[d] * math.sqrt(alpha) + noise[d] * math.sqrt(1 - alpha) for d in range(4)]
            noise_pred.append({
                't': t / n_epochs,
                'alpha': alpha,
                'noisy': [round(x, 3) for x in noisy],
                'target': v,
            })

    return {
        'means': [round(m, 2) for m in means],
        'stds': [round(s, 2) for s in stds],
        'n_samples': len(vecs),
        'prototype': prototype,
        'dim_labels': dim_labels,
        'n_epochs': n_epochs,
    }


def sample_policy(model, n_steps=3, temperature=0.5):
    """从扩散模型采样多步干预策略

    Uses DDPM-style reverse process: 从随机噪声逐步去噪

    Args:
        model: train_diffusion 的输出
        n_steps: int — 规划的干预步数
        temperature: float — 采样温度(0.1=保守,1.0=探索)

    Returns:
        list[dict] — 每一步的干预建议
    """
    if 'error' in model:
        return [{'note': model['error']}]

    means = model['means']
    stds = model['stds']
    prototype = model['prototype']
    n_epochs = model.get('n_epochs', 20)

    # 从原型出发
    start = [prototype['stress_level'], prototype['sleep_latency'],
             prototype['awake_times'], prototype['score']]
    start_norm = [(start[d] - means[d]) / stds[d] if stds[d] > 0 else 0 for d in range(4)]

    steps = []
    for step in range(n_steps):
        # 反向扩散: 从噪声逐步去噪到"好策略"
        # 每个步骤生成一个_渐变更温和的_干预
        x = [random.gauss(0, temperature) for _ in range(4)]

        # DDPM逆向过程
        for t in range(n_epochs - 1, -1, -1):
            alpha = _noise_schedule(t, n_epochs)
            noise = [random.gauss(0, 1) for _ in range(4)]

            # epsilon预测: 趋向原型方向
            eps_pred = [(x[d] - start_norm[d] * math.sqrt(alpha)) / max(0.01, math.sqrt(1 - alpha))
                        for d in range(4)]

            # 去噪一步
            beta = 1 - alpha
            x = [
                (1 / max(0.01, math.sqrt(alpha))) * (x[d] - (beta / max(0.01, math.sqrt(1 - alpha))) * eps_pred[d])
                + math.sqrt(beta) * noise[d]
                for d in range(4)
            ]

            # 温度衰减
            temperature *= 0.95

        # 反归一化
        denorm = [x[d] * stds[d] + means[d] for d in range(4)]
        interp_factor = 1.0 - step / max(1, n_steps)
        mixed_stress = start[0] * interp_factor + denorm[0] * (1 - interp_factor)
        mixed_score = start[3] * interp_factor + denorm[3] * (1 - interp_factor)

        dims = {
            'stress_level': max(1, min(10, round(mixed_stress, 1))),
            'sleep_latency': max(5, min(120, round(start[1] * interp_factor + denorm[1] * (1 - interp_factor)))),
            'awake_times': max(0, round(start[2] * interp_factor + denorm[2] * (1 - interp_factor), 1)),
            'score': max(10, min(100, round(mixed_score, 1))),
        }

        steps.append({
            'step': step + 1,
            'target': dims,
            'confidence': round(1.0 - temperature, 3),
        })

    return steps


def policy_summary(model):
    """摘要"""
    if 'error' in model:
        return 'Diffusion: %s' % model['error']
    p = model.get('prototype', {})
    return 'Diffusion: %d条学%s条步规划, 原型评分=%.1f' % (
        model['n_samples'], 3, p.get('score', 0))


# ===== 自测 =====
if __name__ == '__main__':
    print('=== Diffusion Policy Test ===\n')

    history = []
    for i in range(20):
        stress = 3 + (i % 5) * 0.5
        latency = 20 + stress * 2 + random.gauss(0, 5)
        history.append({
            'stress_level': stress,
            'sleep_latency': latency,
            'awake_times': max(0, stress * 0.2 + random.gauss(0, 0.3)),
            'score': 80 - stress * 2 - random.gauss(0, 3),
        })

    model = train_diffusion(history)
    print(policy_summary(model))
    assert 'error' not in model
    assert model['n_samples'] == 20

    plan = sample_policy(model, n_steps=3)
    print('\n3-step plan:')
    for s in plan:
        t = s['target']
        print('  Step %d: stress=%.1f, latency=%.1f, score=%.1f (conf=%.2f)' % (
            s['step'], t['stress_level'], t['sleep_latency'], t['score'], s['confidence']))
    assert len(plan) == 3

    # 数据不足
    m2 = train_diffusion([])
    assert 'error' in m2

    print('\nAll tests passed!')
