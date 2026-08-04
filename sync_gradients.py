#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_gradients.py — Synthetic Gradients / 同步梯度 (v7.5+)
原理: DeepMind Synthetic Gradients — 让模块异步更新，不用等待真实梯度
落地: 让10位专家不用彼此等待就能输出初步评估，降低延迟

用法:
  from sync_gradients import async_expert_eval, sync_aggregate
  results = async_expert_eval(sleep_data, profile)
  final = sync_aggregate(results, async_results)
"""

import random
import time
import json
import os
from collections import defaultdict

SYNC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'sync_grad')
os.makedirs(SYNC_DIR, exist_ok=True)

# 专家分组（独立组可以同时运行）
EXPERT_GROUPS = {
    'mental': ['ClinicalPsychologist', 'CBT'],
    'physical': ['SleepPhysician', 'CardiacMonitor'],
    'rhythm': ['Chronobiologist', 'LifeScientist'],
    'wellness': ['StressRelaxation', 'ExerciseRehab', 'NutriMetabolism'],
    'risk': ['RiskManager'],
}

# ===== 缓存预测器（模拟合成梯度） =====
# 用历史数据预测专家的初评分数，避免等待真实结果


def _predict_from_cache(openid, expert_name):
    """从缓存中预测专家评分（合成梯度的核心）"""
    path = os.path.join(SYNC_DIR, '%s_cache.json' % openid.replace('/', '_'))
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        return cache.get(expert_name)
    except Exception:
        return None


def _update_cache(openid, expert_name, result):
    """更新预测缓存"""
    if not openid:
        return
    path = os.path.join(SYNC_DIR, '%s_cache.json' % openid.replace('/', '_'))
    try:
        cache = {}
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        cache[expert_name] = {
            'score': result.get('score', 0.5),
            'confidence': result.get('confidence', 0.3),
            'findings': result.get('findings', [])[:2],
            'risk_flags': result.get('risk_flags', [])[:2],
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


async def async_eval_group(group_name, expert_names, sleep_data, profile):
    """异步评估一组专家（模拟不阻塞）

    实际：用缓存预测快速返回，真实结果后台更新

    Returns:
        dict: {expert_name: {score, confidence, findings, risk_flags, async: True}}
    """
    results = {}
    for name in expert_names:
        # 尝试从缓存快速预测
        cached = _predict_from_cache(profile.get('openid', ''), name) if profile else None
        if cached:
            results[name] = {
                'score': cached.get('score', 0.5),
                'confidence': cached.get('confidence', 0.3),
                'findings': cached.get('findings', []),
                'risk_flags': cached.get('risk_flags', []),
                'async': True,
            }
        else:
            # 无缓存时用中性默认
            results[name] = {
                'score': 0.5,
                'confidence': 0.2,
                'findings': [],
                'risk_flags': [],
                'async': True,
            }
    return results


def merge_async_results(real_results, async_results):
    """合并真实结果（优先）和异步预测（降级）

    real_results: 真实comprehensive_analysis的round2
    async_results: async_eval_group的预测

    Returns:
        dict — 合并后的结果
    """
    merged = {}
    all_names = set(list(real_results.keys()) + list(async_results.keys()))

    for name in all_names:
        if name in real_results:
            merged[name] = real_results[name]
        elif name in async_results:
            merged[name] = async_results[name]

    return merged


def get_group_sync_status(openid):
    """获取异步状态"""
    path = os.path.join(SYNC_DIR, '%s_cache.json' % openid.replace('/', '_'))
    if not os.path.exists(path):
        return {'cached': 0, 'groups': len(EXPERT_GROUPS)}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        return {'cached': len(cache), 'groups': len(EXPERT_GROUPS)}
    except Exception:
        return {'cached': 0, 'groups': len(EXPERT_GROUPS)}


# ===== 自测 =====
if __name__ == '__main__':
    import asyncio
    print('=== Synthetic Gradients Test ===\n')

    # 测试1: 异步评估（无缓存时用默认）
    async def test():
        results = await async_eval_group('mental', ['CBT', 'ClinicalPsychologist'],
                                          {'sleep_latency': 60}, {'openid': 'test_sync'})
        for name, r in results.items():
            print('Test 1 (%s): async=%s, score=%.2f' % (name, r.get('async'), r['score']))
        assert len(results) == 2
        assert all(r.get('async') for r in results.values())

        # 测试2: 缓存写入
        _update_cache('test_sync', 'CBT', {'score': 0.7, 'confidence': 0.8, 'findings': ['test'], 'risk_flags': []})
        cached = await async_eval_group('mental', ['CBT'], {'sleep_latency': 60}, {'openid': 'test_sync'})
        print('Test 2 (cached): CBT score=%.2f' % cached['CBT']['score'])
        assert cached['CBT']['score'] == 0.7
        assert cached['CBT'].get('async')

        # 测试3: 合并
        real = {'CBT': {'score': 0.8, 'confidence': 0.9, 'findings': ['real'], 'risk_flags': []}}
        merged = merge_async_results(real, {'ClinicalPsychologist': {'score': 0.5, 'confidence': 0.3, 'findings': [], 'risk_flags': [], 'async': True}})
        print('Test 3 (merge): CBT=%.2f, CP=%.2f' % (merged['CBT']['score'], merged['ClinicalPsychologist']['score']))
        assert merged['CBT']['score'] == 0.8  # 真实结果优先
        assert merged['ClinicalPsychologist']['async']  # 异步降级

        # 清理
        import os as _os
        _p = os.path.join(SYNC_DIR, 'test_sync_cache.json')
        if _os.path.exists(_p):
            _os.remove(_p)

        print('\nAll tests passed!')

    asyncio.run(test())
