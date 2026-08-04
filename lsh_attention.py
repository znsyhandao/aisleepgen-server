#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lsh_attention.py — Reformer / LSH高效注意力 (v7.5+)
原理: Google Reformer — 用评分相似度+内容亲和度降维注意力
落地: 在10位专家的交互中找到最相关的专家对

用法:
  from lsh_attention import get_expert_peers, lsh_summary
  peers = get_expert_peers(expert_scores)
"""

import hashlib
from collections import defaultdict

EXPERT_PROFILES = {
    'ClinicalPsychologist': {'mood', 'stress', 'anxiety', 'depression', 'cognition'},
    'CBT': {'insomnia', 'latency', 'awake', 'sleep_effort', 'maladaptive'},
    'SleepPhysician': {'apnea', 'hypoxia', 'sas', 'rls', 'disorder'},
    'Chronobiologist': {'circadian', 'rhythm', 'bedtime', 'wake_time', 'phase'},
    'LifeScientist': {'efficiency', 'hrv', 'recovery', 'longevity', 'inflammation'},
    'RiskManager': {'risk', 'flag', 'comorbidity', 'cumulative', 'emergent'},
    'StressRelaxation': {'stress', 'relaxation', 'tension', 'overactive', 'breathing'},
    'ExerciseRehab': {'exercise', 'activity', 'movement', 'sedentary', 'rehab'},
    'CardiacMonitor': {'cardiac', 'heart', 'hrv', 'arrhythmia', 'cardiovascular'},
    'NutriMetabolism': {'nutrition', 'diet', 'metabolism', 'melatonin', 'caffeine'},
}


def _jaccard_similarity(set_a, set_b):
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / max(len(set_a | set_b), 1)


def get_expert_peers(scores_dict, top_n=3):
    """获取每位专家最相关的同行（基于评分相似度+内容亲和度）

    Args:
        scores_dict: dict {expert_name: score}
        top_n: int — 最多N个同行

    Returns:
        dict: {expert_name: [(peer, score_sim, content_sim), ...]}
    """
    if not scores_dict:
        return {}

    peers = {}
    names = list(scores_dict.keys())
    for name in names:
        scored = []
        for other in names:
            if other == name:
                continue
            score_sim = round(1.0 - abs(scores_dict.get(name, 0.5) - scores_dict.get(other, 0.5)), 3)
            content_sim = round(_jaccard_similarity(
                EXPERT_PROFILES.get(name, set()),
                EXPERT_PROFILES.get(other, set()),
            ), 3)
            combined = round(score_sim * 0.6 + content_sim * 0.4, 3)
            scored.append((other, score_sim, content_sim, combined))
        scored.sort(key=lambda x: -x[3])
        peers[name] = scored[:top_n]
    return peers


def lsh_summary(peers):
    """摘要"""
    if not peers:
        return 'LSH: 无数据'
    lines = ['LSH高效注意力 (评分相似度+内容亲和度):']
    for expert, p_list in peers.items():
        if p_list:
            peers_str = ', '.join('%s(sc=%.2f,co=%.2f)' % (p[0][:6], p[1], p[2]) for p in p_list)
            lines.append('  %s <-> %s' % (expert, peers_str))
    return '\n'.join(lines)


# ===== 自测 =====
if __name__ == '__main__':
    scores = {
        'ClinicalPsychologist': 0.55, 'CBT': 0.47,
        'SleepPhysician': 0.71, 'Chronobiologist': 0.63,
        'LifeScientist': 0.58, 'RiskManager': 0.42,
        'StressRelaxation': 0.68, 'ExerciseRehab': 0.55,
        'CardiacMonitor': 0.51, 'NutriMetabolism': 0.49,
    }
    peers = get_expert_peers(scores)
    print(lsh_summary(peers))
    assert len(peers) == 10
    # 每位专家至少有个peer(10位数据肯定都有)
    all_have = all(len(v) > 0 for v in peers.values())
    print('All have peers:', all_have)
    assert all_have
    print('\nAll tests passed!')
