#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
working_memory.py — AISleepGen 短期工作记忆模块 v1.0

范式跃迁：将"短期工作记忆"与"长期POMDP信念"分离。

问题：
  用户连聊5天都好，第6天崩了——POMDP因为长期信念(λ=0.9)还没降下来，
  继续输出"状态不错"。需要短期工作记忆 + 长期信念分离。

核心设计：
  - WorkingMemory 类，每个用户一个实例
  - 维护最近N次交互的滑动窗口（默认N=10）
  - 短期信念：只基于最近5次交互的加权平均（最新权重大）
  - 长期信念：由POMDP引擎的 λ=0.9 遗忘因子维护
  - 趋势检测：最近3次评分的线性趋势

集成点：
  - pomdp_learner.py: observe_text/observe_survey 时自动 push
  - chat_prompt_builder.py: build_pomdp_context 追加短期记忆信息
  - conscious_decider.py: 新增短期记忆投票因子
  - meta_learner.py: 新增 short_term_volatility 指标
"""

import json, os, time, math, logging
from statistics import mean, stdev
from datetime import datetime
from collections import defaultdict, deque

_wm_log = logging.getLogger('aisleepgen.working_memory')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ==================== 工作记忆 ====================

DEFAULT_WINDOW_SIZE = 10


class WorkingMemory:
    """短期工作记忆——每个用户一个实例

    维护最近N次交互的滑动窗口，提供短期趋势、短期信念等。
    与POMDP引擎的长期信念（λ=0.9）完全独立。
    """

    def __init__(self, max_window=DEFAULT_WINDOW_SIZE):
        self.max_window = max_window
        # {openid: deque of entries, maxlen=max_window}
        self._windows = {}
        # 持久化路径
        self._dir = os.path.join(PROJECT_ROOT, 'data', 'working_memory')
        os.makedirs(self._dir, exist_ok=True)

    def _get_deque(self, openid):
        """获取用户的滑动窗口deque（lazy init + 从磁盘恢复）"""
        if openid not in self._windows:
            self._windows[openid] = self._load(openid)
        return self._windows[openid]

    def _path(self, openid):
        safe = openid.replace('/', '_').replace('\\', '_')
        return os.path.join(self._dir, f'{safe}.json')

    def _load(self, openid):
        """从磁盘恢复用户的滑动窗口"""
        d = deque(maxlen=self.max_window)
        fp = self._path(openid)
        try:
            if os.path.exists(fp):
                with open(fp, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for entry in data:
                    d.append(entry)
        except (json.JSONDecodeError, IOError) as e:
            _wm_log.warning('[WM] Failed to load %s: %s', openid[:8], e)
        return d

    def _save(self, openid):
        """持久化用户的滑动窗口"""
        d = self._get_deque(openid)
        fp = self._path(openid)
        try:
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(list(d), f, ensure_ascii=False, indent=2)
        except IOError as e:
            _wm_log.warning('[WM] Failed to save %s: %s', openid[:8], e)

    def push(self, openid, entry):
        """添加一次交互

        Args:
            openid: 用户ID
            entry: dict, 包含 timestamp, text, score_obs, emotion, intervention, outcome
                - timestamp: ISO格式时间串 (自动填充如果缺失)
                - text: 用户消息文本
                - score_obs: 本次观测的评分 (0-100)
                - emotion: 情绪标签 (positive/negative/neutral)
                - intervention: 本次采用的干预类型 (push/chat/probe/delay_push/skip/none)
                - outcome: 干预结果 (effective/neutral/counter/none)
        """
        if 'timestamp' not in entry:
            entry['timestamp'] = datetime.now().isoformat()

        d = self._get_deque(openid)
        d.append(entry)
        self._save(openid)

    def recent(self, openid, n=5):
        """最近N次交互列表

        Args:
            openid: 用户ID
            n: 返回条数（默认5，不超过窗口大小）

        Returns:
            list[dict]: 最近n条，按时间从新到旧
        """
        d = self._get_deque(openid)
        if not d:
            return []
        n = min(n, len(d))
        return list(d)[-n:][::-1]

    def recent_trend(self, openid):
        """最近3次的评分趋势

        Returns:
            dict: {
                'direction': 'up' | 'down' | 'flat',
                'slope': float,  # 斜率（分/次）
                'scores': list[float],  # 最近3次评分
                'n': int,  # 实际数据点数
            }
        """
        d = self._get_deque(openid)
        n_all = len(d)
        if n_all < 2:
            scores = [e.get('score_obs', 50) for e in d]
            return {
                'direction': 'flat',
                'slope': 0.0,
                'scores': scores,
                'n': n_all,
            }

        # 取最近3次
        n = min(3, n_all)
        entries = list(d)[-n:]
        scores = [e.get('score_obs', 50) for e in entries]

        # 简单线性回归：slope = (n*Σxy - Σx*Σy) / (n*Σx² - (Σx)²)
        # x = 0,1,2（从远到近）
        x_vals = list(range(n))
        y_vals = scores

        n_len = len(x_vals)
        sum_x = sum(x_vals)
        sum_y = sum(y_vals)
        sum_xy = sum(x * y for x, y in zip(x_vals, y_vals))
        sum_x2 = sum(x * x for x in x_vals)

        denominator = n_len * sum_x2 - sum_x * sum_x
        if abs(denominator) < 1e-10:
            slope = 0.0
        else:
            slope = (n_len * sum_xy - sum_x * sum_y) / denominator

        if slope > 1.0:
            direction = 'up'
        elif slope < -1.0:
            direction = 'down'
        else:
            direction = 'flat'

        return {
            'direction': direction,
            'slope': round(slope, 2),
            'scores': scores,
            'n': n,
        }

    def short_term_belief(self, openid):
        """只基于最近5次交互计算的"短期信念"

        方法：简单加权平均，越新的交互权重越大。
        权重分配：1, 2, 3, 4, 5（从旧到新）

        Returns:
            dict: {
                'weighted_score': float,  # 加权平均评分
                'n': int,  # 实际数据点数
                'weights': list[float],  # 实际使用的权重
                'scores': list[float],  # 实际使用的评分
            }
        """
        d = self._get_deque(openid)
        n_all = len(d)
        if n_all == 0:
            return {'weighted_score': 50.0, 'n': 0, 'weights': [], 'scores': []}

        n = min(5, n_all)
        entries = list(d)[-n:]
        scores = [e.get('score_obs', 50) for e in entries]

        # 权重：1,2,3,4,5 ∈ 从旧到新
        weights = [float(i + 1) for i in range(n)]
        total_weight = sum(weights)

        weighted_score = sum(s * w for s, w in zip(scores, weights)) / total_weight

        return {
            'weighted_score': round(weighted_score, 1),
            'n': n,
            'weights': [round(w / total_weight, 3) for w in weights],
            'scores': scores,
        }

    def recent_interventions(self, openid, n=3):
        """最近N次采用的干预类型

        Args:
            openid: 用户ID
            n: 返回条数（默认3）

        Returns:
            list[str]: 最近n次干预类型（逆序，最新的在前）
        """
        d = self._get_deque(openid)
        if not d:
            return []
        n = min(n, len(d))
        entries = list(d)[-n:][::-1]
        return [e.get('intervention', 'none') for e in entries]

    # ==================== v3.21: 时序深度增强 ====================

    def temporal_signature(self, openid):
        """时序特征签名

        计算速度、加速度、波动率、周期性。

        Returns:
            dict: {
                'velocity': float,      # 一阶差分均值（分/天）
                'acceleration': float,  # 二阶差分均值（趋势变化速度）
                'volatility': float,    # 评分标准差
                'periodicity': str,     # 'weekly' | 'random' | 'unknown'
            }
        """
        d = self._get_deque(openid)
        all_entries = list(d)
        scores = [e.get('score_obs', 50) for e in all_entries if e.get('score_obs') is not None]

        if len(scores) < 3:
            return {
                'velocity': 0.0,
                'acceleration': 0.0,
                'volatility': 0.0,
                'periodicity': 'unknown',
            }

        # 速度：一阶差分均值
        diffs = [scores[i+1] - scores[i] for i in range(len(scores)-1)]
        velocity = mean(diffs) if diffs else 0.0

        # 加速度：二阶差分均值
        acc_diffs = [diffs[i+1] - diffs[i] for i in range(len(diffs)-1)]
        acceleration = mean(acc_diffs) if acc_diffs else 0.0

        # 波动率：标准差
        vol = stdev(scores) if len(scores) >= 2 else 0.0

        # 周期性：检查是否有7天周期
        periodicity = 'unknown'
        if len(scores) >= 14:
            # 检查7天自相关
            lag7_diffs = []
            for i in range(7, len(scores)):
                lag7_diffs.append(abs(scores[i] - scores[i-7]))
            avg_lag7 = mean(lag7_diffs) if lag7_diffs else 100
            if avg_lag7 < 10:
                periodicity = 'weekly'

        return {
            'velocity': round(velocity, 2),
            'acceleration': round(acceleration, 2),
            'volatility': round(vol, 2),
            'periodicity': periodicity,
        }

    def state_context(self, openid):
        """时序状态上下文描述

        基于速度+加速度的组合判断用户的"状态语境"。

        States:
          - "正在改善": acc >= 0 and vel > 5
          - "正在恶化": acc <= 0 and vel < -5
          - "触底反弹": acc > 0 and vel < 0
          - "高位回落": acc < 0 and vel > 0
          - "持平震荡": 其他

        Returns:
            str: 状态文本描述
        """
        sig = self.temporal_signature(openid)
        vel = sig['velocity']
        acc = sig['acceleration']

        # 优先级：触底反弹、高位回落、正在改善、正在恶化
        if acc > 0 and vel < 0 and abs(vel) > 1:
            return '触底反弹'
        elif acc < 0 and vel > 0 and abs(vel) > 1:
            return '高位回落'
        elif vel < -3:
            return '正在恶化'
        elif vel > 3:
            return '正在改善'
        else:
            return '持平震荡'

    @property
    def short_term_volatility(self):
        """最近N次评分的标准差（用于meta_learner）

        Returns:
            float: 标准差（如果数据不足返回0）
        """
        return self._compute_volatility()

    def _compute_volatility(self, openid=None):
        """计算最近所有评分数据的标准差

        如果提供openid，基于该用户的评分；否则基于所有用户的评分（用于回顾）。
        实际在meta_learner中使用时传入openid。
        """
        if openid is None:
            # 全量计算：所有用户的评分
            all_scores = []
            for oid, d in self._windows.items():
                for e in d:
                    s = e.get('score_obs')
                    if s is not None:
                        all_scores.append(s)
            if not all_scores:
                return 0.0
            scores = all_scores
        else:
            d = self._get_deque(openid)
            scores = [e.get('score_obs', 50) for e in d if e.get('score_obs') is not None]

        if len(scores) < 2:
            return 0.0

        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        return round(math.sqrt(variance), 2)

    def get_volatility(self, openid):
        """获取指定用户的评分波动率（标准差）"""
        return self._compute_volatility(openid)

    def clear_user(self, openid):
        """清除用户的短期记忆"""
        if openid in self._windows:
            del self._windows[openid]
        fp = self._path(openid)
        try:
            if os.path.exists(fp):
                os.remove(fp)
        except IOError:
            pass

    def get_all_openids(self):
        """获取所有有短期记忆的用户ID列表"""
        return list(self._windows.keys())


# ==================== 全局实例 ====================

_wm_instance = None


def get_working_memory(max_window=None):
    """获取全局短期工作记忆实例"""
    global _wm_instance
    if _wm_instance is None:
        _wm_instance = WorkingMemory(max_window or DEFAULT_WINDOW_SIZE)
    return _wm_instance


# ==================== 自测 ====================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    print('=== Working Memory Self-Test ===\n')

    wm = WorkingMemory(max_window=10)

    # 1. 创建WM，push 5次不同评分 → recent_trend 正确反映趋势
    print('1. Push 5 entries and verify trend:')
    test_openid = 'test_wm_1'
    scores = [30, 45, 55, 70, 85]  # 持续上升
    for i, s in enumerate(scores):
        wm.push(test_openid, {
            'text': f'Day {i+1}',
            'score_obs': s,
            'emotion': 'positive' if s > 50 else 'negative',
            'intervention': 'none',
            'outcome': 'none',
        })

    trend = wm.recent_trend(test_openid)
    print(f'   Trend: {trend["direction"]} (slope={trend["slope"]}), scores={trend["scores"]}')
    assert trend['direction'] == 'up', f'Expected up, got {trend["direction"]}'
    assert trend['slope'] > 1.0, f'Expected positive slope, got {trend["slope"]}'
    print('   OK - upward trend detected')

    # 2. 短期信念 = 最近加权平均
    print('\n2. Short-term belief weighted average:')
    stb = wm.short_term_belief(test_openid)
    print(f'   Weighted score: {stb["weighted_score"]}')
    print(f'   Weights: {stb["weights"]}')
    print(f'   Scores: {stb["scores"]}')
    # 加权平均值应该在简单平均值附近但偏向最新值
    # 最近5次简单平均 = (30+45+55+70+85)/5 = 57
    # 加权平均 = (30*1+45*2+55*3+70*4+85*5)/(1+2+3+4+5) = 1160/15 ≈ 77.3
    # 加权平均值 = (30*1+45*2+55*3+70*4+85*5)/15 = 990/15 = 66.0
    assert 60 < stb['weighted_score'] < 70, f'Expected weighted score around 66, got {stb["weighted_score"]}'
    print('   OK - weighted score > simple average (latest weights more)')

    # 3. 连续3次高分然后1次低分 → "short term down, long term ok" 模式
    print('\n3. Short-term down vs long-term ok pattern:')
    wm2 = WorkingMemory(max_window=10)
    test_openid2 = 'test_wm_2'
    for i in range(5):
        wm2.push(test_openid2, {
            'text': f'Good day {i+1}',
            'score_obs': 85,
            'emotion': 'positive',
            'intervention': 'none',
            'outcome': 'none',
        })
    # 加一个低分
    wm2.push(test_openid2, {
        'text': 'Bad day',
        'score_obs': 35,
        'emotion': 'negative',
        'intervention': 'none',
        'outcome': 'none',
    })

    trend2 = wm2.recent_trend(test_openid2)
    print(f'   Recent trend: {trend2["direction"]} (slope={trend2["slope"]}), scores={trend2["scores"]}')
    assert trend2['direction'] == 'down', f'Expected down, got {trend2["direction"]}'
    print(f'   Trend correctly shows down')

    stb2 = wm2.short_term_belief(test_openid2)
    print(f'   Short-term score: {stb2["weighted_score"]} (vs long-term ~85)')
    # 短期加权：最近5次 = [85,85,85,85,35] 加权 = (85*1+85*2+85*3+85*4+35*5)/15 = 935/15 ≈ 62.3
    # 短期加权：最近5次 = [85,85,85,85,35] 加权 = (85*1+85*2+85*3+85*4+35*5)/15 = 935/15 ≈ 62.3
    assert 55 < stb2['weighted_score'] < 70, f'Short-term should be around 62, got {stb2["weighted_score"]}'
    print('   OK - short-term < long-term: "short term down, long term ok"')

    # 4. 干预类型记录
    print('\n4. Recent interventions tracking:')
    wm3 = WorkingMemory(max_window=10)
    test_openid3 = 'test_wm_3'
    for i, intervention in enumerate(['push', 'chat', 'probe', 'delay_push', 'skip']):
        wm3.push(test_openid3, {
            'text': f'Day {i+1}',
            'score_obs': 60 + i * 5,
            'emotion': 'neutral',
            'intervention': intervention,
            'outcome': 'neutral' if intervention != 'push' else 'effective',
        })

    ri = wm3.recent_interventions(test_openid3, n=3)
    print(f'   Recent 3 interventions: {ri}')
    assert ri == ['skip', 'delay_push', 'probe'], f'Expected ["skip","delay_push","probe"], got {ri}'
    print('   OK - interventions correctly tracked')

    # 5. 挥发度计算
    print('\n5. Volatility calculation:')
    vol = wm2.get_volatility(test_openid2)
    print(f'   Volatility (std): {vol}')
    # 5个85和1个35，标准差应该较大
    assert vol > 15.0, f'Expected high volatility, got {vol}'
    print('   OK - volatility reflects score spread')

    # 6. 短期信念与长期信念差异测试
    print('\n6. Short-term vs long-term belief divergence:')
    # 模拟：长期POMDP信念通过观察逐步降下来很慢（λ=0.9）
    # 而短期工作记忆能快速反映最近的恶化
    wm4 = WorkingMemory(max_window=10)
    test_openid4 = 'test_wm_4'
    # 前5天好
    for i in range(5):
        wm4.push(test_openid4, {
            'text': f'Good day {i+1}',
            'score_obs': 80,
            'emotion': 'positive',
            'intervention': 'none',
            'outcome': 'none',
        })
    # 第6天崩  
    wm4.push(test_openid4, {
        'text': 'Bad day',
        'score_obs': 35,
        'emotion': 'negative',
        'intervention': 'none',
        'outcome': 'none',
    })

    stb4 = wm4.short_term_belief(test_openid4)
    trend4 = wm4.recent_trend(test_openid4)
    print(f'   6-day avg score: {sum([80,80,80,80,80,35])/6:.1f}')
    print(f'   Short-term weighted: {stb4["weighted_score"]}')
    print(f'   Trend: {trend4["direction"]}')
    # 短期加权 = (80*1+80*2+80*3+80*4+35*5)/15 = 735/15 = 49
    # 短期加权 = (80*1+80*2+80*3+80*4+35*5)/15 = 975/15 = 65.0
    assert 60 <= stb4['weighted_score'] <= 70, f'Short-term score around 65, got {stb4["weighted_score"]}'
    assert trend4['direction'] == 'down', f'Trend should be down, got {trend4["direction"]}'
    print('   OK - short-term belief correctly diverges from long-term')

    print('\nAll tests PASS! ✅')
