#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
online_rl.py — AISleepGen 在线强化学习决策器 v1.0

范式跃迁：系统从"被动等待观测"变成"主动提问来减少不确定性"。

核心思想：
  传统系统等待用户提交数据→分析→出建议。
  RL决策器：主动采样！不确定性高→主动问；效果好→继续做；效果差→换策略。

架构：
  状态空间：4维离散 → 144种状态
  行动空间：6种行动
  Q-learning + Double Q（减少过估计偏置）
  ε-贪婪探索（上下文感知）

集成点：
  - conscious_decider.py: RL建议占35%投票权重
  - dp_router.py: handle_chat / handle_sleep_analyze 中调用
  - chat_prompt_builder.py: 注入RL策略信息到LLM prompt

存储：
  - data/online_rl/{openid}_q.json (Q1,Q2)
  - data/online_rl/{openid}_history.json
"""

import json, os, time, math, logging, random
from datetime import datetime
from collections import defaultdict

_rl_log = logging.getLogger('aisleepgen.online_rl')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data', 'online_rl')

# ==================== 常数 ====================

# 行动空间
ACTIONS = ['ask', 'probe', 'push', 'delay_push', 'skip', 'companion']
ACTION_CN = {
    'ask': '主动提问',
    'probe': '探索性推送',
    'push': '强干预',
    'delay_push': '推迟干预',
    'skip': '什么都不做',
    'companion': '陪伴模式',
}

# 状态离散化 bins
SCORE_BINS = [('<40', 0, 40), ('40-60', 40, 60), ('60-80', 60, 80), ('>80', 80, 101)]
TREND_BINS = [('down', -1), ('flat', 0), ('up', 1)]
UNCERTAINTY_BINS = [('low', 0, 0.3), ('medium', 0.3, 0.6), ('high', 0.6, 1.01)]
EFFECT_BINS = [('effective', 0), ('neutral', 1), ('counter', 2), ('none', 3)]

# 行动索引
ACTION_INDICES = {a: i for i, a in enumerate(ACTIONS)}

# Q-learning 参数
DEFAULT_ALPHA = 0.1
DEFAULT_GAMMA = 0.9
DEFAULT_EPSILON = 0.2
DECAY_RATE = 0.9995  # 每次update后衰减
MIN_EPSILON = 0.05

# Double Q交替周期
DOUBLE_Q_ALTERNATE = 2  # 每N次update交替使用Q1或Q2做选择

# 上下文感知ε探索参数
HIGH_UNCERTAINTY_EPSILON = 0.3
LOW_UNCERTAINTY_EPSILON = 0.1
NEW_USER_EPSILON = 0.4
COUNTER_EFFECT_EPSILON = 0.35

# 新用户阈值（观测数少于多少次视为新用户）
NEW_USER_THRESHOLD = 5
COUNTER_WINDOW = 3  # 最近多少次干预中检查"counter"


# ==================== 奖励参数 ==================== 0.5

REWARDS = {
    'score_observed': 0.5,       # 用户提供了评分观测
    'positive_feedback': 1.0,    # 用户正面反馈
    'negative_feedback': -1.0,   # 用户负面反馈
    'intervention_adopted': 0.3, # 干预被采用（companion_start等）
    'user_silent': -0.5,         # 用户沉默/流失
    'ask_penalty': -0.1,         # 问太多讨人厌
    'push_penalty': -0.2,        # 推太多招人烦
}

# ==================== 状态编码器 ====================


class StateEncoder:
    """状态编码：4维特征 → 一维索引 (0~143)"""

    @staticmethod
    def get_score_bin(score):
        """评分区间"""
        if score <= 0:
            return 0  # <40 (default for unknown)
        for i, (name, lo, hi) in enumerate(SCORE_BINS):
            if lo <= score < hi:
                return i
        return 3  # >80

    @staticmethod
    def get_trend_bin(trend_direction):
        """趋势方向"""
        mapping = {'down': 0, 'flat': 1, 'up': 2}
        return mapping.get(trend_direction, 1)

    @staticmethod
    def get_uncertainty_bin(entropy):
        """不确定性"""
        for i, (name, lo, hi) in enumerate(UNCERTAINTY_BINS):
            if lo <= entropy < hi:
                return i
        return 1  # medium

    @staticmethod
    def get_effect_bin(last_effect):
        """上次干预效果"""
        mapping = {'effective': 0, 'neutral': 1, 'counter': 2, 'none': 3, 'unknown': 3}
        return mapping.get(last_effect, 3)

    @staticmethod
    def encode(score_bin, trend_bin, uncertainty_bin, effect_bin):
        """4维→1维索引 (0~143)"""
        return (score_bin * 3 * 3 * 4
                + trend_bin * 3 * 4
                + uncertainty_bin * 4
                + effect_bin)

    @staticmethod
    def get_state_count():
        return 4 * 3 * 3 * 4  # 144

    @staticmethod
    def from_context(score=None, trend=None, entropy=None, last_effect=None):
        """从context字典直接编码状态"""
        sb = StateEncoder.get_score_bin(score or 0)
        tb = StateEncoder.get_trend_bin(trend or 'flat')
        ub = StateEncoder.get_uncertainty_bin(entropy if entropy is not None else 0.5)
        eb = StateEncoder.get_effect_bin(last_effect or 'none')
        return StateEncoder.encode(sb, tb, ub, eb)


# ==================== 在线RL核心 ====================


class OnlineRL:
    """在线强化学习决策器

    每个用户维护独立Q表（Double Q：Q1和Q2交替更新），
    支持持久化、探索衰减、上下文感知探索。

    Usage:
        rl = OnlineRL()
        action = rl.act(openid, context)
        rl.update(openid, action, reward, next_context)
    """

    def __init__(self, alpha=DEFAULT_ALPHA, gamma=DEFAULT_GAMMA,
                 epsilon=DEFAULT_EPSILON):
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self._q_tables = {}  # {openid: {'Q1': {s_a: q}, 'Q2': {s_a: q}}}
        self._histories = {}  # {openid: [history entries]}
        self._update_counters = {}  # {openid: int} for Double Q alternation
        self._ab_overrides = {}  # {openid: {experiment_id, config}} v5.1 AB框架实验参数覆盖
        os.makedirs(DATA_DIR, exist_ok=True)

    def set_ab_config(self, openid, experiment_id, ab_config):
        """设置AB实验覆盖的RL参数"""
        self._ab_overrides[openid] = {
            'experiment_id': experiment_id,
            'config': ab_config,
        }

    def clear_ab_config(self, openid):
        """清除AB实验覆盖"""
        self._ab_overrides.pop(openid, None)

    def _get_effective_params(self, openid):
        """获取生效的RL参数（base + AB实验覆盖）"""
        params = {
            'alpha': self.alpha,
            'gamma': self.gamma,
            'epsilon': self.epsilon,
            'epsilon_decay_steps': DECAY_RATE,  # DECAY_RATE from module-level
        }
        # AB实验覆盖
        ab_data = self._ab_overrides.get(openid)
        if ab_data:
            config = ab_data['config']
            if 'alpha' in config:
                params['alpha'] = config['alpha']
            if 'gamma' in config:
                params['gamma'] = config['gamma']
            if 'epsilon' in config:
                params['epsilon'] = config['epsilon']
            if 'epsilon_decay_steps' in config:
                params['epsilon_decay_steps'] = config['epsilon_decay_steps']
        return params

    # ==================== 持久化 ====================

    def _q_path(self, openid):
        safe = openid.replace('/', '_').replace('\\', '_')
        return os.path.join(DATA_DIR, f'{safe}_q.json')

    def _history_path(self, openid):
        safe = openid.replace('/', '_').replace('\\', '_')
        return os.path.join(DATA_DIR, f'{safe}_history.json')

    def _load_q(self, openid):
        """从磁盘加载Q表"""
        fp = self._q_path(openid)
        try:
            if os.path.exists(fp):
                with open(fp, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('Q1', {}), data.get('Q2', {})
        except Exception as e:
            _rl_log.warning('[RL] Failed to load Q for %s: %s', openid[:8], e)
        return {}, {}

    def _save_q(self, openid):
        """写入Q表到磁盘"""
        q_tables = self._q_tables.get(openid, {'Q1': {}, 'Q2': {}})
        fp = self._q_path(openid)
        try:
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(q_tables, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _rl_log.warning('[RL] Failed to save Q for %s: %s', openid[:8], e)

    def _load_history(self, openid):
        """从磁盘加载学习历史"""
        fp = self._history_path(openid)
        try:
            if os.path.exists(fp):
                with open(fp, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            _rl_log.warning('[RL] Failed to load history for %s: %s', openid[:8], e)
        return []

    def _save_history(self, openid):
        """写入学习历史到磁盘"""
        history = self._histories.get(openid, [])
        fp = self._history_path(openid)
        try:
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _rl_log.warning('[RL] Failed to save history for %s: %s', openid[:8], e)

    def _ensure_q(self, openid):
        """确保Q表已加载"""
        if openid not in self._q_tables:
            q1, q2 = self._load_q(openid)
            self._q_tables[openid] = {'Q1': q1, 'Q2': q2}
        if openid not in self._update_counters:
            self._update_counters[openid] = 0
        if openid not in self._histories:
            self._histories[openid] = self._load_history(openid)

    # ==================== 状态编码 + 行动查找 ====================

    def _q(self, openid, state_idx, action_idx, table='Q1'):
        """从指定Q表获取Q值"""
        q_tables = self._q_tables.get(openid, {'Q1': {}, 'Q2': {}})
        key = f'{state_idx}_{action_idx}'
        return q_tables.get(table, {}).get(key, 0.0)

    def _set_q(self, openid, state_idx, action_idx, value, table):
        """设置Q表值"""
        q_tables = self._q_tables[openid]
        key = f'{state_idx}_{action_idx}'
        if table not in q_tables:
            q_tables[table] = {}
        q_tables[table][key] = round(value, 4)

    def _get_epsilon(self, openid, entropy=None, n_obs=0, recent_counter=0):
        """上下文感知ε探索率"""
        base = self.epsilon

        # 高不确定 → 多探索
        if entropy is not None and entropy > 0.6:
            base = max(base, HIGH_UNCERTAINTY_EPSILON)
        elif entropy is not None and entropy < 0.3:
            base = min(base, LOW_UNCERTAINTY_EPSILON)

        # 新用户 → 多尝试
        if n_obs < NEW_USER_THRESHOLD:
            base = max(base, NEW_USER_EPSILON)

        # 连续counter → 换方案
        if recent_counter >= 2:
            base = max(base, COUNTER_EFFECT_EPSILON)

        return min(1.0, max(0.01, base))

    def _get_effective_epsilon(self, openid, context=None):
        """从context获取综合ε探索率（优先使用AB实验覆盖参数）"""
        entropy = None
        n_obs = 0
        recent_counter = 0

        if context:
            entropy = context.get('pomdp_entropy')
            n_obs = context.get('n_observations', 0)
            # 检查最近干预效果
            recent_effects = context.get('recent_effects', [])
            recent_counter = sum(1 for e in recent_effects[-COUNTER_WINDOW:]
                                 if e == 'counter')
        else:
            # 从学习历史推断
            history = self._histories.get(openid, [])
            n_obs = len(history)
            recent_effects = [h.get('effect', 'none') for h in history[-COUNTER_WINDOW:]]
            recent_counter = sum(1 for e in recent_effects if e == 'counter')

        # 优先使用AB实验的epsilon
        effective_params = self._get_effective_params(openid)
        ab_epsilon = effective_params.get('epsilon')
        base = ab_epsilon if ab_epsilon is not None else self.epsilon

        # 上下文感知探索
        if entropy is not None and entropy > 0.6:
            base = max(base, HIGH_UNCERTAINTY_EPSILON)
        elif entropy is not None and entropy < 0.3:
            base = min(base, LOW_UNCERTAINTY_EPSILON)

        if n_obs < NEW_USER_THRESHOLD:
            base = max(base, NEW_USER_EPSILON)

        if recent_counter >= 2:
            base = max(base, COUNTER_EFFECT_EPSILON)

        return min(1.0, max(0.01, base))

    def _best_action(self, openid, state_idx, use_q1=True):
        """从指定Q表选最优行动"""
        max_q = -float('inf')
        best_actions = []
        for i, act in enumerate(ACTIONS):
            q = self._q(openid, state_idx, i, 'Q1' if use_q1 else 'Q2')
            if q > max_q:
                max_q = q
                best_actions = [act]
            elif q == max_q:
                best_actions.append(act)
        return random.choice(best_actions) if best_actions else 'skip'

    # ==================== 核心API ====================

    def act(self, openid, context=None):
        """选择行动

        Args:
            openid: 用户ID
            context: dict, 包含评分/趋势/熵/效果等状态信息
                - score: 评分 (0-100)
                - trend: 趋势方向 (down/flat/up)
                - pomdp_entropy: POMDP信念熵 (0~1)
                - last_effect: 上次干预效果 (effective/neutral/counter/none/unknown)
                - n_observations: 总观测数
                - recent_effects: 最近干预效果列表

        Returns:
            str: 行动名 (ask/probe/push/delay_push/skip/companion)
        """
        self._ensure_q(openid)
        state_idx = StateEncoder.from_context(
            score=context.get('score') if context else None,
            trend=context.get('trend') if context else None,
            entropy=context.get('pomdp_entropy') if context else None,
            last_effect=context.get('last_effect') if context else None,
        )

        epsilon = self._get_effective_epsilon(openid, context)
        counter = self._update_counters.get(openid, 0)
        use_q1 = (counter // DOUBLE_Q_ALTERNATE) % 2 == 0

        # ε-贪婪探索
        if random.random() < epsilon:
            action = random.choice(ACTIONS)
            _rl_log.debug('[RL] %s ε-explore(s=%d ε=%.2f) -> %s',
                          openid[:8], state_idx, epsilon, action)
        else:
            action = self._best_action(openid, state_idx, use_q1=use_q1)
            _rl_log.debug('[RL] %s greedy(s=%d qt=%s) -> %s',
                          openid[:8], state_idx, 'Q1' if use_q1 else 'Q2', action)

        return action

    def update(self, openid, action, reward, next_context=None):
        """更新Q值

        Args:
            openid: 用户ID
            action: 执行的行动
            reward: 即时奖励
            next_context: 行动后的新context (用于计算下一状态max Q)
        """
        self._ensure_q(openid)
        counter = self._update_counters[openid]
        use_q1 = (counter // DOUBLE_Q_ALTERNATE) % 2 == 0
        current_table = 'Q1' if use_q1 else 'Q2'
        target_table = 'Q2' if use_q1 else 'Q1'

        # 如果没传next_context，尝试从历史反推（用最近的最佳状态估计）
        if next_context is None:
            history = self._histories.get(openid, [])
            if history:
                last = history[-1]
                # 用上一个状态作为当前状态的近似（行为策略下的next_state）
                next_state_idx = StateEncoder.from_context(
                    score=last.get('score'),
                    trend=last.get('trend'),
                    entropy=last.get('entropy'),
                    last_effect=last.get('effect'),
                )
            else:
                next_state_idx = StateEncoder.from_context()
        else:
            next_state_idx = StateEncoder.from_context(
                score=next_context.get('score'),
                trend=next_context.get('trend'),
                entropy=next_context.get('pomdp_entropy'),
                last_effect=next_context.get('last_effect'),
            )

        action_idx = ACTION_INDICES.get(action, 0)

        # 当前Q值 (当前更新表)
        current_q = self._q(openid, next_state_idx, action_idx, current_table)

        # 下一状态最大Q值 (目标表)
        next_max_q = max(
            self._q(openid, next_state_idx, i, target_table)
            for i in range(len(ACTIONS))
        )

        # 使用AB实验覆盖的参数
        effective_params = self._get_effective_params(openid)
        alpha = effective_params.get('alpha', self.alpha)
        gamma = effective_params.get('gamma', self.gamma)
        epsilon_decay = effective_params.get('epsilon_decay_steps', DECAY_RATE)

        # Q-learning更新: Q(s,a) += α * (r + γ * max(Q(s',a')) - Q(s,a))
        td_error = reward + gamma * next_max_q - current_q
        new_q = current_q + alpha * td_error

        self._set_q(openid, next_state_idx, action_idx, new_q, current_table)

        # 衰减探索率（优先使用AB实验覆盖的decay rate）
        epsilon_decay = effective_params.get('epsilon_decay_steps', DECAY_RATE)
        self.epsilon = max(MIN_EPSILON, self.epsilon * epsilon_decay)

        # 记录历史
        history_entry = {
            'ts': time.time(),
            'datetime': datetime.now().isoformat(),
            'action': action,
            'reward': reward,
            'state_idx': next_state_idx,
            'nd_next_state': next_state_idx,
            'q_before': round(current_q, 4),
            'q_after': round(new_q, 4),
            'td_error': round(td_error, 4),
            'table': current_table,
            'epsilon': round(self.epsilon, 4),
        }
        self._histories.setdefault(openid, []).append(history_entry)
        if len(self._histories[openid]) > 200:
            self._histories[openid] = self._histories[openid][-200:]

        # 周期持久化
        self._update_counters[openid] = counter + 1
        if (counter + 1) % 5 == 0:
            self._save_q(openid)
            self._save_history(openid)

        _rl_log.debug('[RL] %s update: s=%d a=%s r=%.2f td=%.3f q:%.3f->%.3f (ε=%.3f)',
                      openid[:8], next_state_idx, action, reward, td_error,
                      current_q, new_q, self.epsilon)

        return td_error

    def get_action_value(self, openid, action):
        """获取指定行动的当前估计值（取Q1+Q2平均）"""
        self._ensure_q(openid)
        action_idx = ACTION_INDICES.get(action, 0)
        n_states = StateEncoder.get_state_count()

        total_q = 0.0
        count = 0
        q_tables = self._q_tables.get(openid, {'Q1': {}, 'Q2': {}})
        for s in range(n_states):
            key = f'{s}_{action_idx}'
            q1 = q_tables['Q1'].get(key, 0.0)
            q2 = q_tables['Q2'].get(key, 0.0)
            avg = (q1 + q2) / 2
            if avg != 0.0 or key in q_tables['Q1'] or key in q_tables['Q2']:
                total_q += avg
                count += 1

        if count == 0:
            return 0.0
        return round(total_q / count, 4)

    def get_policy_summary(self, openid):
        """获取当前策略统计

        Returns:
            dict: {
                'total_updates': int,
                'epsilon': float,
                'best_action': str,
                'best_q': float,
                'action_stats': {action: {'count': int, 'avg_reward': float}},
                'exploration_rate': float,
                'double_q_diverge': bool (Q1和Q2有显著差异吗),
            }
        """
        self._ensure_q(openid)
        history = self._histories.get(openid, [])

        # 行动统计
        action_stats = {}
        for a in ACTIONS:
            action_stats[a] = {'count': 0, 'rewards': []}
        for h in history:
            a = h.get('action', 'skip')
            r = h.get('reward', 0)
            if a in action_stats:
                action_stats[a]['count'] += 1
                action_stats[a]['rewards'].append(r)

        for a in ACTIONS:
            rewards = action_stats[a]['rewards']
            action_stats[a]['avg_reward'] = round(
                sum(rewards) / len(rewards), 4) if rewards else 0.0
            del action_stats[a]['rewards']

        # 最佳行动（取所有状态下Q1+Q2平均最高）
        q_tables = self._q_tables.get(openid, {'Q1': {}, 'Q2': {}})
        action_q_total = {a: 0.0 for a in ACTIONS}
        action_q_count = {a: 0 for a in ACTIONS}
        n_states = StateEncoder.get_state_count()

        for s in range(n_states):
            for i, a in enumerate(ACTIONS):
                key = f'{s}_{i}'
                q1 = q_tables['Q1'].get(key, 0.0)
                q2 = q_tables['Q2'].get(key, 0.0)
                if q1 != 0.0 or q2 != 0.0 or key in q_tables['Q1'] or key in q_tables['Q2']:
                    action_q_total[a] += (q1 + q2) / 2
                    action_q_count[a] += 1

        best_action = max(ACTIONS,
                          key=lambda a: action_q_total.get(a, 0) /
                          max(action_q_count.get(a, 0), 1))
        best_q = (action_q_total.get(best_action, 0) /
                  max(action_q_count.get(best_action, 0), 1))

        # Double Q差异检测
        diverge = False
        diff_count = 0
        all_keys = set(list(q_tables['Q1'].keys()) + list(q_tables['Q2'].keys()))
        # 只检查那些至少一个表有非零值的状态-行动对
        check_keys = {k for k in all_keys if abs(q_tables['Q1'].get(k, 0.0)) > 0.01 or abs(q_tables['Q2'].get(k, 0.0)) > 0.01}
        for key in check_keys:
            q1 = q_tables['Q1'].get(key, 0.0)
            q2 = q_tables['Q2'].get(key, 0.0)
            if abs(q1 - q2) > 0.1:
                diff_count += 1
        if check_keys and diff_count >= len(check_keys) * 0.5:
            diverge = True

        return {
            'total_updates': len(history),
            'epsilon': round(self.epsilon, 4),
            'best_action': best_action,
            'best_q': round(best_q, 4),
            'action_stats': action_stats,
            'exploration_rate': round(
                sum(1 for h in history[-20:] if h.get('epsilon', 0) > self.epsilon) /
                max(len(history[-20:]), 1), 4) if history else 0,
            'double_q_diverge': diverge,
            'last_update': history[-1].get('datetime', '') if history else '',
        }

    def reset_q(self, openid):
        """重置用户的Q表"""
        self._q_tables[openid] = {'Q1': {}, 'Q2': {}}
        self._update_counters[openid] = 0
        self._save_q(openid)
        # 保留history作为参考
        _rl_log.info('[RL] Q table reset for %s', openid[:8])


# ==================== 全局实例 ====================

_online_rl_instance = None


def get_online_rl(alpha=DEFAULT_ALPHA, gamma=DEFAULT_GAMMA, epsilon=DEFAULT_EPSILON):
    """获取全局OnlineRL实例"""
    global _online_rl_instance
    if _online_rl_instance is None:
        _online_rl_instance = OnlineRL(alpha, gamma, epsilon)
    return _online_rl_instance


# ==================== 实用函数 ====================

def extract_reward_from_outcome(openid, action, outcome_context):
    """从干预结果中提取奖励值

    Args:
        openid: 用户ID
        action: 执行的行动 (ask/probe/push/delay_push/skip/companion)
        outcome_context: dict 干预结果
            - score_observed: bool 是否获得了评分观测
            - feedback: int or None 用户反馈 (负数=负面, 0=中性, 正数=正面)
            - intervention_adopted: bool 干预是否被采用
            - user_silent: bool 用户是否沉默

    Returns:
        float: 即时奖励
    """
    reward = 0.0

    if not outcome_context:
        return reward

    # 信息增益：用户提供了评分
    if outcome_context.get('score_observed'):
        reward += REWARDS['score_observed']

    # 用户反馈
    feedback = outcome_context.get('feedback')
    if feedback is not None:
        if isinstance(feedback, (int, float)):
            if feedback > 0:
                reward += REWARDS['positive_feedback']
            elif feedback < 0:
                reward += REWARDS['negative_feedback']

    # 干预被采用
    if outcome_context.get('intervention_adopted'):
        reward += REWARDS['intervention_adopted']

    # 用户沉默/流失
    if outcome_context.get('user_silent'):
        reward += REWARDS['user_silent']

    # 行动特殊惩罚
    if action == 'ask':
        reward += REWARDS['ask_penalty']
    elif action == 'push':
        reward += REWARDS['push_penalty']

    return round(reward, 4)


# ==================== 自测 ====================

if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING,
                        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')

    print('=' * 60)
    print('Online RL Self-Test')
    print('=' * 60)

    rl = OnlineRL(epsilon=0.2)

    # Test 1: 空用户 → 随机探索
    print('\n1. Empty user (no history):')
    ctx_empty = {}
    a1 = rl.act('test_empty', ctx_empty)
    e = rl._get_effective_epsilon('test_empty', ctx_empty)
    print(f'   Action: {a1} (ε={e:.2f}) — should be random exploration')
    assert e >= 0.3, f'Empty user epsilon should be high, got {e}'
    print(f'   PASS: ε={e:.2f} >= 0.3 (NEW_USER_EPSILON)')

    # Test 2: 有数据用户 → greedy
    print('\n2. User with Q values:')
    rl._ensure_q('test_greedy')
    # 手动注入Q值让"ask"最优
    for s in range(StateEncoder.get_state_count()):
        for i, a in enumerate(ACTIONS):
            q_ask = 1.5 if a == 'ask' else 0.5
            rl._q_tables['test_greedy']['Q1'][f'{s}_{i}'] = q_ask
            rl._q_tables['test_greedy']['Q2'][f'{s}_{i}'] = q_ask
    rl._update_counters['test_greedy'] = 100  # 让ε衰减
    rl.epsilon = 0.05  # 低探索率

    ctx_known = {'score': 75, 'trend': 'flat', 'pomdp_entropy': 0.2, 'last_effect': 'effective', 'n_observations': 20}
    results = {}
    for _ in range(100):
        a = rl.act('test_greedy', ctx_known)
        results[a] = results.get(a, 0) + 1
    best = max(results, key=results.get)
    print(f'   Actions: {results}')
    print(f'   Best action: {best} (should be ask, Q=1.5)')
    assert best == 'ask', f'Expected ask, got {best}'
    print('   PASS: greedy selects best Q action')

    # Test 3: Double Q — Q1和Q2出现偏差
    print('\n3. Double Q divergence:')
    rl._ensure_q('test_dq')
    rl._q_tables['test_dq'] = {
        'Q1': {'0_0': 1.0, '0_1': 0.5},
        'Q2': {'0_0': 1.5, '0_1': -0.2},
    }
    for s in range(StateEncoder.get_state_count()):
        for i in range(len(ACTIONS)):
            k = f'{s}_{i}'
            if k not in rl._q_tables['test_dq']['Q1']:
                rl._q_tables['test_dq']['Q1'][k] = 0.0
            if k not in rl._q_tables['test_dq']['Q2']:
                rl._q_tables['test_dq']['Q2'][k] = 0.0
    sum_q = rl.get_policy_summary('test_dq')
    print(f'   Double Q diverge: {sum_q["double_q_diverge"]} (should be True)')
    assert sum_q['double_q_diverge'], 'Q1 and Q2 should diverge'
    print('   PASS: Double Q tables show divergence')

    # Test 4: 奖励函数 — 正反馈Q升，负反馈Q降
    print('\n4. Reward function:')
    rl._ensure_q('test_reward')

    # 正反馈：update写入Q1表，读取对应key
    rl.update('test_reward', 'ask', 1.0, {'score': 70, 'pomdp_entropy': 0.4, 'trend': 'flat', 'last_effect': 'none'})
    # 写入后的状态: score=70→bin2, trend=flat→bin1, entropy=0.4→bin1, effect=none→bin3
    # state_idx = 2*3*3*4 + 1*3*4 + 1*4 + 3 = 72+12+4+3 = 91
    # action 'ask' → idx 0
    # key = '91_0' in Q1
    expected_state = StateEncoder.encode(2, 1, 1, 3)  # 60-80, flat, medium, none
    q_after = rl._q('test_reward', expected_state, 0, 'Q1')
    print(f'   Positive reward: Q={q_after:.3f} (should be > 0)')
    assert q_after > 0, f'Q should be positive after +1.0 reward, got {q_after}'
    print('   PASS: Q increased on positive reward')

    # 负反馈
    rl.update('test_reward', 'probe', -1.0, {'score': 50, 'pomdp_entropy': 0.5, 'trend': 'flat', 'last_effect': 'none'})
    # score=50→bin1, trend=flat→bin1, entropy=0.5→bin1, effect=none→bin3
    # state_idx = 1*3*3*4 + 1*3*4 + 1*4 + 3 = 36+12+4+3 = 55
    # action 'probe' → idx 1
    expected_state2 = StateEncoder.encode(1, 1, 1, 3)  # 40-60, flat, medium, none
    q_after2 = rl._q('test_reward', expected_state2, 1, 'Q1')
    print(f'   Negative reward: Q={q_after2:.3f} (should be < 0)')
    assert q_after2 < 0, f'Q should be negative after -1.0 reward, got {q_after2}'
    print('   PASS: Q decreased on negative reward')

    # Test 5: 探索衰减
    print('\n5. Exploration decay:')
    rl2 = OnlineRL(epsilon=0.2)
    initial_eps = rl2.epsilon
    print(f'   Initial ε: {initial_eps}')
    for _ in range(5000):
        rl2.update('test_decay', 'skip', 0.0, {'score': 50})
    final_eps = rl2.epsilon
    print(f'   After 5000 updates, ε: {final_eps:.4f}')
    assert final_eps < initial_eps, f'ε should decay over time, got {final_eps} >= {initial_eps}'
    assert final_eps <= MIN_EPSILON + 0.01, f'ε should approach min={MIN_EPSILON}, got {final_eps}'
    print(f'   PASS: ε decayed from {initial_eps} to {final_eps}')

    # Test 6: 上下文感知 — 高熵ε=0.3，低熵ε=0.1
    print('\n6. Context-aware epsilon:')
    rl3 = OnlineRL(epsilon=0.2)
    high_e = rl3._get_epsilon('test_ctx', entropy=0.8, n_obs=20, recent_counter=0)
    low_e = rl3._get_epsilon('test_ctx', entropy=0.1, n_obs=20, recent_counter=0)
    new_e = rl3._get_epsilon('test_ctx', entropy=0.5, n_obs=2, recent_counter=0)
    counter_e = rl3._get_epsilon('test_ctx', entropy=0.5, n_obs=20, recent_counter=3)
    print(f'   High entropy: ε={high_e:.2f} (should be 0.30)')
    print(f'   Low entropy: ε={low_e:.2f} (should be ~0.10)')
    print(f'   New user: ε={new_e:.2f} (should be 0.40)')
    print(f'   Counter effect: ε={counter_e:.2f} (should be 0.35)')
    assert high_e >= 0.29, f'High entropy ε should be >= 0.3, got {high_e}'
    assert low_e <= 0.11, f'Low entropy ε should be ~0.1, got {low_e}'
    assert new_e >= 0.39, f'New user ε should be 0.4, got {new_e}'
    assert counter_e >= 0.34, f'Counter effect ε should be 0.35, got {counter_e}'
    print('   PASS: Context-aware epsilon accurate')

    # Test 7: 持久化 — Q表写入文件后可恢复
    print('\n7. Persistence:')
    rl._ensure_q('test_persist')
    # 写入已知Q值
    rl._q_tables['test_persist']['Q1']['5_2'] = 2.5
    rl._q_tables['test_persist']['Q2']['5_2'] = 1.8
    rl._save_q('test_persist')

    # 创建新实例，重新加载
    rl4 = OnlineRL()
    rl4._ensure_q('test_persist')
    restored = rl4._q('test_persist', 5, 2, 'Q1')
    restored2 = rl4._q('test_persist', 5, 2, 'Q2')
    print(f'   Q1 restored: {restored} (should be 2.5)')
    print(f'   Q2 restored: {restored2} (should be 1.8)')
    assert abs(restored - 2.5) < 0.01, f'Q1 restore failed, got {restored}'
    assert abs(restored2 - 1.8) < 0.01, f'Q2 restore failed, got {restored2}'
    print('   PASS: Q table persisted and restored')

    # Test 8: 差分更新 — 同(s,a)连续更新，Q值收敛
    print('\n8. Differential update (convergence):')
    rl5 = OnlineRL(alpha=0.1, epsilon=0.0)
    rl5._ensure_q('test_conv')
    q_values = []
    for step in range(500):
        rl5.update('test_conv', 'ask', 1.0, {'score': 75, 'pomdp_entropy': 0.4, 'last_effect': 'effective', 'trend': 'flat'})
        # score=75→bin2, trend=flat→bin1, entropy=0.4→bin1, effect=effective→bin0
        # state_idx = 2*3*3*4 + 1*3*4 + 1*4 + 0 = 72+12+4+0 = 88
        q = rl5._q('test_conv', 88, 0, 'Q1')
        q_values.append(q)
    final_q = q_values[-1]
    deltas = [abs(q_values[i] - q_values[i-1]) for i in range(1, len(q_values))]
    avg_last_20_delta = sum(deltas[-20:]) / 20 if len(deltas) >= 20 else 0
    print(f'   Q after 500 updates: {final_q:.4f} (avg last 20 delta: {avg_last_20_delta:.6f})')
    assert avg_last_20_delta < 0.02, f'Q should be converging, avg last 20 delta={avg_last_20_delta}'
    print('   PASS: Q converges with repeated updates')

    # Test 9: extract_reward_from_outcome 正确性
    print('\n9. Reward extraction:')
    r_positive = extract_reward_from_outcome('test', 'ask', {
        'score_observed': True,
        'feedback': 1,
        'intervention_adopted': True,
    })
    # ask: score_observed(0.5) + positive_feedback(1.0) + adopted(0.3) + ask_penalty(-0.1) = 1.7
    expected_pos = 0.5 + 1.0 + 0.3 - 0.1
    print(f'   Positive reward: {r_positive} (expected {expected_pos})')
    assert abs(r_positive - expected_pos) < 0.01, f'Expected {expected_pos}, got {r_positive}'

    r_negative = extract_reward_from_outcome('test', 'push', {
        'feedback': -1,
        'user_silent': True,
    })
    # push: negative_feedback(-1.0) + silent(-0.5) + push_penalty(-0.2) = -1.7
    expected_neg = -1.0 + -0.5 + -0.2
    print(f'   Negative reward: {r_negative} (expected {expected_neg})')
    assert abs(r_negative - expected_neg) < 0.01, f'Expected {expected_neg}, got {r_negative}'

    r_mixed = extract_reward_from_outcome('test', 'ask', {
        'score_observed': True,
        'feedback': 1,
    })
    # ask: score_observed(0.5) + feedback(1.0) + ask_penalty(-0.1) = 1.4
    expected_mixed = 0.5 + 1.0 - 0.1
    print(f'   Mixed reward: {r_mixed} (expected {expected_mixed})')
    assert abs(r_mixed - expected_mixed) < 0.01, f'Expected {expected_mixed}, got {r_mixed}'
    print('   PASS: Reward extraction correct')

    # Test 10: 集成 — 完整RL决策循环
    print('\n10. Full RL decision loop:')
    rl_loop = OnlineRL(epsilon=0.3)
    actions_log = []
    for step in range(10):
        ctx = {'score': 60 + (step % 5) * 5,
               'trend': 'flat' if step < 5 else 'down',
               'pomdp_entropy': 0.5 + (step / 20),
               'last_effect': 'none' if step == 0 else 'effective',
               'n_observations': 3 + step}
        action = rl_loop.act('test_loop', ctx)
        # 模拟结果（随机）
        reward = 0.5 if action in ('ask', 'probe') else -0.2 if action == 'push' else 0.0
        next_ctx = {'score': ctx['score'] + 5,
                    'trend': 'up',
                    'pomdp_entropy': max(0.1, ctx['pomdp_entropy'] - 0.1),
                    'last_effect': 'effective',
                    'n_observations': ctx['n_observations'] + 1}
        rl_loop.update('test_loop', action, reward, next_ctx)
        actions_log.append(action)
    summary = rl_loop.get_policy_summary('test_loop')
    print(f'   Actions taken: {actions_log}')
    print(f'   Total updates: {summary["total_updates"]}')
    print(f'   Epsilon: {summary["epsilon"]:.4f}')
    print(f'   Best action: {summary["best_action"]} (Q={summary["best_q"]})')
    print(f'   Action stats: {summary["action_stats"]}')
    assert summary['total_updates'] == 10, f'Expected 10 updates, got {summary["total_updates"]}'
    assert summary['epsilon'] < 0.3, f'ε should have decayed, got {summary["epsilon"]}'
    print('   PASS: Full RL loop works')

    # Cleanup test files
    import os, shutil
    test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'online_rl')
    for fname in os.listdir(test_dir):
        if fname.startswith('test_'):
            os.remove(os.path.join(test_dir, fname))

    print('\n' + '=' * 60)
    print('All 10 tests PASS!')
    print('=' * 60)