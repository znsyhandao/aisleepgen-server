#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
meta_rl.py — Meta-RL元强化学习 (v7.5+)
原理: Meta RL — 从历史反馈中学习策略向量，用Q-learning更新
落地: 基于用户的rating反馈，自动学习"高评分场景下应该加强哪个专家"

用法:
  from meta_rl import learn_strategy, get_policy, rl_summary
  policy = learn_strategy(openid, context, reward)
  probs = get_policy(openid)
"""

import json, os, math, random

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RL_DIR = os.path.join(PROJECT_ROOT, 'data', 'meta_rl')
os.makedirs(RL_DIR, exist_ok=True)

EXPERT_NAMES = [
    'ClinicalPsychologist', 'CBT', 'SleepPhysician', 'Chronobiologist',
    'LifeScientist', 'RiskManager', 'StressRelaxation',
    'ExerciseRehab', 'CardiacMonitor', 'NutriMetabolism',
]

# 状态映射: 用户压力水平分类（低/中/高）
STRESS_BINS = [0, 4, 7, 10]  # [0-4), [4-7), [7-10]
STRESS_LABELS = ['low_stress', 'medium_stress', 'high_stress']

# 动作: 专家权重调整方向（10个专家 × 3个方向 = 30个动作）
ACTION_DIM = 30


def _to_state(profile):
    """从profile提取状态向量

    3维: [stress_level_bin, n_records_bin, avg_score_bin]
    """
    if not isinstance(profile, dict):
        return [0, 0, 0]

    # 压力 bin
    stress = profile.get('recent_stress', profile.get('stress_level', 5))
    try:
        stress = float(stress)
    except (ValueError, TypeError):
        stress = 5
    s_bin = max(0, min(2, sum(1 for b in STRESS_BINS if stress >= b) - 1))

    # 数据量 bin
    history = profile.get('history', [])
    n = len(history) if isinstance(history, list) else 0
    n_bin = 0 if n < 5 else (1 if n < 15 else 2)

    # 评分 bin
    scores = [r.get('score', 50) for r in history if isinstance(r, dict)] if isinstance(history, list) else []
    if scores:
        avg = sum(scores) / len(scores)
    else:
        avg = 50
    sc_bin = 0 if avg < 40 else (1 if avg < 70 else 2)

    return [s_bin, n_bin, sc_bin]


def _state_id(state):
    """状态编码: 3维各3bin = 27种状态"""
    return state[0] * 9 + state[1] * 3 + state[2]


def _action_name(action_idx):
    """动作名称: 专家_方向"""
    expert_idx = action_idx // 3
    direction_idx = action_idx % 3
    if expert_idx >= len(EXPERT_NAMES):
        return 'unknown'
    expert = EXPERT_NAMES[expert_idx]
    dirs = ['boost', 'reduce', 'neutral']
    return '%s_%s' % (expert, dirs[direction_idx])


def _parse_action_name(name):
    """从动作名称解析索引"""
    parts = name.rsplit('_', 1)
    if len(parts) != 2:
        return 0
    expert, direction = parts
    if expert not in EXPERT_NAMES:
        return 0
    expert_idx = EXPERT_NAMES.index(expert)
    dirs = {'boost': 0, 'reduce': 1, 'neutral': 2}
    d = dirs.get(direction, 2)
    return expert_idx * 3 + d


def _user_path(openid):
    safe = openid.replace('/', '_').replace('\\', '_')
    return os.path.join(RL_DIR, '%s.json' % safe)


def _load(openid):
    path = _user_path(openid)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    # 初始化Q表: 27状态 × 30动作
    return {
        'q_table': [[0.0] * ACTION_DIM for _ in range(27)],
        'n_updates': 0,
        'epsilon': 0.3,  # 探索率
        'alpha': 0.1,    # 学习率
        'gamma': 0.9,    # 折扣因子
        'history': [],
        'last_state': None,
        'last_action': None,
    }


def _save(openid, data):
    with open(_user_path(openid), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _choose_action(data, state_id):
    """ε-greedy策略"""
    if random.random() < data['epsilon']:
        return random.randint(0, ACTION_DIM - 1)  # 探索
    # 利用: 选最大Q值
    q = data['q_table'][state_id]
    best_val = max(q)
    best_actions = [i for i, v in enumerate(q) if v == best_val]
    return random.choice(best_actions)


def learn_strategy(openid, profile, reward):
    """从一次反馈学习策略

    Args:
        openid: str
        profile: dict — 用户上下文
        reward: float — 0~1, 基于rating归一化
    """
    if not openid:
        return

    data = _load(openid)
    state = _to_state(profile)
    s_id = _state_id(state)

    # 选动作
    action = _choose_action(data, s_id)

    # Q-learning更新
    old_q = data['q_table'][s_id][action]
    max_next = max(data['q_table'][s_id])
    new_q = old_q + data['alpha'] * (reward + data['gamma'] * max_next - old_q)
    data['q_table'][s_id][action] = round(new_q, 4)

    data['n_updates'] += 1

    # 衰减探索率
    data['epsilon'] = max(0.05, data['epsilon'] * 0.998)

    data['last_state'] = state
    data['last_action'] = action
    data['history'].append({
        'state': state,
        'action': action,
        'action_name': _action_name(action),
        'reward': round(reward, 3),
    })

    if len(data['history']) > 200:
        data['history'] = data['history'][-200:]

    _save(openid, data)
    return action


def get_policy(openid):
    """获取当前策略（Q表摘要）

    Returns: dict {状态: 最优动作的详细信息}
    """
    data = _load(openid)
    q_table = data['q_table']

    policy = {}
    for s_id in range(27):
        q = q_table[s_id]
        if max(q) == 0:
            continue
        best_a = max(range(len(q)), key=lambda i: q[i])
        best_q = q[best_a]
        if best_q > 0.01:
            # 解析状态
            s_bin = s_id // 9
            n_bin = (s_id % 9) // 3
            sc_bin = s_id % 3
            policy[str(s_id)] = {
                'state_label': 'stress=%s,records=%s,score=%s' % (
                    STRESS_LABELS[s_bin], ['<5', '5-15', '15+'][n_bin],
                    ['<40', '40-70', '70+'][sc_bin]),
                'best_action': _action_name(best_a),
                'q_value': round(best_q, 3),
            }

    return {
        'policy': policy,
        'n_updates': data['n_updates'],
        'epsilon': round(data['epsilon'], 3),
        'n_actions_learned': len(policy),
    }


def rl_summary(openid):
    """摘要"""
    policy = get_policy(openid)
    return 'Meta-RL: %d次更新, ε=%.2f, %d条策略' % (
        policy['n_updates'], policy['epsilon'], policy['n_actions_learned'])


# ===== 自测 =====
if __name__ == '__main__':
    print('=== Meta-RL Test ===\n')

    # 模拟: 高压力用户喜欢RiskManager被boost
    profile_high_stress = {'recent_stress': 8, 'history': [{'score': 35} for _ in range(3)]}
    profile_low_stress = {'recent_stress': 2, 'history': [{'score': 85} for _ in range(20)]}

    for _ in range(50):
        learn_strategy('test_rl', profile_high_stress, 0.8)
    for _ in range(30):
        learn_strategy('test_rl', profile_low_stress, 0.2)

    policy = get_policy('test_rl')
    print('Updates:', policy['n_updates'])
    print('Epsilon:', policy['epsilon'])
    print('Learned policies:', policy['n_actions_learned'])
    for s_id, info in list(policy['policy'].items())[:3]:
        print('  state=%s: %s -> %s (Q=%.3f)' % (s_id, info['state_label'], info['best_action'], info['q_value']))

    assert policy['n_updates'] == 80
    assert policy['n_actions_learned'] >= 1

    sm = rl_summary('test_rl')
    print('\nSummary:', sm)

    # 清理
    import os as _os
    for f in ['test_rl.json']:
        p = _os.path.join(RL_DIR, f)
        if _os.path.exists(p):
            _os.remove(p)

    print('\nAll tests passed!')
