#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
relpath_learner.py — RelPath关系路径学习 (v8.0)
【共享库版本】底层算法已提取到 nexus-algos/nexus_algos/relpath/core.py
所有项目共享同一份 RelPath 算法实现。

用法不变:
  from relpath_learner import build_relpath_graph, get_path_insight, relpath_summary
"""
import sys, os
# 确保 nexus-algos 在路径中
_ALGO_DIR = r'D:\nexus-algos'
if _ALGO_DIR not in sys.path:
    sys.path.insert(0, _ALGO_DIR)

from nexus_algos.relpath.domains.sleep import (
    build_relpath_graph, get_path_insight, relpath_summary,
    DIMENSIONS, DIM_LABELS,
)


# ===== 自测 =====
if __name__ == '__main__':
    import random
    random.seed(42)

    # 模拟数据: stress→latency→score 路径
    records = []
    for i in range(30):
        stress = random.gauss(5, 2)
        latency = 30 + stress * 3 + random.gauss(0, 8)
        awake = max(0, stress * 0.3 + random.gauss(0, 0.8))
        dur = 450 - stress * 8 + random.gauss(0, 25)
        score = 75 - stress * 3 - latency * 0.1 + random.gauss(0, 6)
        records.append({
            'stress_level': stress, 'sleep_latency': latency,
            'score': score, 'awake_times': awake,
            'total_duration': dur,
            'bedtime_hour': 23 + random.gauss(0, 0.5),
            'wake_hour': 7 + random.gauss(0, 0.3),
        })

    graph = build_relpath_graph(records)
    print(relpath_summary(graph))
    print()
    print('Latency path:', get_path_insight(graph, 'sleep_latency'))
    print('Score path:', get_path_insight(graph, 'score'))

    assert 'paths' in graph
    print('\nAll tests passed!')
