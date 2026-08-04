#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
efficient_net.py — 复合缩放架构搜索 Lite (v7.5+)
原理: Google EfficientNet — 用复合系数φ同时缩放深度/宽度/分辨率
落地: 根据用户数据量自动缩放会诊专家的深度(depth)和精度(precision)

用法:
  from efficient_net import compute_scale, scale_summary
  scale = compute_scale(n_records)
  n_experts = scale['active_experts']
"""

import math


def compute_scale(n_records, max_experts=10, min_experts=4, phi_range=(0.0, 2.0)):
    """复合缩放计算

    EfficientNet核心: depth = α^φ, width = β^φ, resolution = γ^φ
    这里: depth(推理深度) = α^φ, precision(精度) = β^φ
    φ由数据量决定: φ = log(活跃度 + 1) / log(30)

    Args:
        n_records: int — 用户历史记录数
        max_experts: int — 最大专家数
        min_experts: int — 最小专家数
        phi_range: tuple — φ范围 (min, max)

    Returns:
        dict: {phi, depth, precision, active_experts, inactive, note}
    """
    if n_records < 1:
        return {
            'phi': 0.0, 'depth': 1, 'precision': 'low',
            'active_experts': min_experts,
            'inactive': max_experts - min_experts,
            'note': '冷启动模式',
        }

    # ===== φ计算 =====
    # 数据量→φ: 0条=0, 5条=0.5, 15条=1.0, 30条=1.5, 50条+=2.0
    raw_phi = math.log(n_records + 1) / math.log(30)  # log30: 30条→1.0
    phi = max(phi_range[0], min(phi_range[1], raw_phi))
    # 使30条→约1.0, 5条→约0.6, 100条→约1.3
    phi = phi * 1.5

    # ===== 复合缩放 =====
    alpha = 1.5  # depth缩放基数
    beta = 1.15  # precision缩放基数

    depth = max(1, round(alpha ** phi))
    precision_raw = beta ** phi

    if precision_raw < 1.2:
        precision = 'low'
    elif precision_raw < 1.5:
        precision = 'medium'
    else:
        precision = 'high'

    # ===== 活跃专家数 =====
    # 随φ从4人逐渐增加到10人
    active_ratio = min(1.0, 0.3 + phi * 0.35)
    active_experts = max(min_experts, min(max_experts,
                                         round(min_experts + (max_experts - min_experts) * active_ratio)))

    # 哪些专家先停用（排序: 冷门专家先停）
    all_experts = [
        'ClinicalPsychologist',  # 主力保留
        'CBT',                    # 主力保留
        'SleepPhysician',         # 主力保留
        'RiskManager',            # 主力保留
        'StressRelaxation',       # 高价值保留
        'TraditionalChinese',     # 次优先
        'Psychoanalysis',         # 次优先
        'HolisticHealth',         # 可选
        'BehavioralTherapist',    # 可选
        'MindfulnessGuide',       # 可选
    ]

    active = all_experts[:active_experts]
    inactive = all_experts[active_experts:]

    return {
        'phi': round(phi, 2),
        'depth': depth,
        'precision': precision,
        'active_experts': active_experts,
        'inactive_count': len(inactive),
        'inactive': inactive,
        'active': active,
        'n_records': n_records,
        'note': 'ok',
    }


def scale_summary(scale):
    """摘要"""
    if scale.get('note') == '冷启动模式':
        return '架构: 冷启动-4专家'
    return '架构: φ=%.1f, %d专%d停, 精度=%s, 深度=%d' % (
        scale['phi'],
        scale['active_experts'],
        scale['inactive_count'],
        scale['precision'],
        scale['depth'],
    )


# ===== 自测 =====
if __name__ == '__main__':
    print('=== EfficientNet Scale Test ===\n')

    # 冷启动: 1条记录
    s1 = compute_scale(1)
    print('1条:', scale_summary(s1))
    assert s1['active_experts'] <= 6

    # 中等用户: 15条
    s2 = compute_scale(15)
    print('15条:', scale_summary(s2))
    assert 5 <= s2['active_experts'] <= 9

    # 重度用户: 50条
    s3 = compute_scale(50)
    print('50条:', scale_summary(s3))
    assert s3['active_experts'] >= 6
    assert s3['precision'] in ('medium', 'high')
    assert s3['depth'] >= 2

    # 0条: 冷启动
    s4 = compute_scale(0)
    print('0条:', scale_summary(s4))
    assert s4['note'] == '冷启动模式'

    # 递增验证
    prev = 0
    for n in [1, 3, 8, 15, 30, 60]:
        s = compute_scale(n)
        assert s['active_experts'] >= prev
        prev = s['active_experts']

    print('\nAll tests passed!')
