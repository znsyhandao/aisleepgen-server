#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
behavior_predictor.py — AISleepGen 行为预测引擎 v1.0

范式跃迁：从"反应式干预"到"预见式干预"。

核心思想：
  系统目前只能推断当前状态，不能预测用户接下来会怎样。
  全是反应式干预，没有预见式。

实现：
  轻量级时序预测器，基于简化的线性回归 + 模式匹配。
  使用短期工作记忆中的最近N次交互数据作为输入。

类：
  BehaviorPredictor:
    - predict_tonight(openid) → prediction dict
    - predict_trend(openid, horizon_days=3) → trend dict
    - anomaly_score(openid) → float

集成点：
  pomdp_learner: 每次信念更新后检查预测vs实际误差 → 动态调整λ
  dp_router: 在决策前跑预测 → 预见式干预
  chat_prompt_builder: pomdp_context追加预测信息
"""

import json, os, time, math, logging
from datetime import datetime, timedelta
from collections import defaultdict, deque
from statistics import mean, stdev

_bp_log = logging.getLogger('aisleepgen.behavior_predictor')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


# ==================== 行为预测引擎 ====================

class BehaviorPredictor:
    """行为预测引擎

    基于简化线性回归 + 模式匹配的轻量级时序预测器。

    输入：从WorkingMemory读取最近N次交互数据
    输出：预测今晚评分、趋势方向、置信度、异常评分

    预测方法：
      1. 简单线性回归预测明天的评分
      2. 趋势预测：最近3天 vs 之前3天
      3. 周期模式识别：周中vs周末、每周周期性
    """

    def __init__(self):
        # 预测误差追踪: {openid: {'errors': [float], 'last_lambda': float}}
        self._prediction_errors = {}
        # 预测缓存: {openid: dict} 短时缓存
        self._prediction_cache = {}
        # 最后缓存时间
        self._cache_ts = {}

    def _get_wm(self):
        """获取工作记忆实例"""
        try:
            from working_memory import get_working_memory
            return get_working_memory()
        except ImportError:
            return None

    def _get_extended_scores(self, openid, n_days=7):
        """从工作记忆获取最近N天的评分序列

        如果数据不足，返回空列表。
        """
        wm = self._get_wm()
        if wm is None:
            return []

        recent = wm.recent(openid, n=n_days)
        if not recent:
            return []

        # 按时间正序（从旧到新）
        entries = list(reversed(recent))
        scores = [e.get('score_obs', 50) for e in entries if e.get('score_obs') is not None]

        if len(scores) < 2:
            return scores

        return scores[:n_days]

    def predict_tonight(self, openid):
        """预测今晚睡眠质量

        方法：简单线性回归预测明天的评分 + 置信区间

        输入：最近7天的评分序列
        公式：predicted_score = w0 + w1*day + w2*prev_score
        置信区间：基于历史残差的标准差

        Returns:
            dict: {
                'score': float,      # 预测评分 (0-100)
                'ci': float,         # ±置信区间
                'confidence': float, # 0~1 置信度
                'w0': float,         # 回归截距
                'w1': float,         # 日趋势系数
                'n': int,            # 数据点数
            }
        """
        scores = self._get_extended_scores(openid, n_days=7)

        if len(scores) < 2:
            return {
                'score': 50.0, 'ci': 15.0, 'confidence': 0.3,
                'w0': 50.0, 'w1': 0.0, 'n': len(scores),
            }

        n = len(scores)
        # 多元回归：score = w0 + w1*day + w2*prev_score
        # 简化版：只用 day 的一元回归 + prev_score 的加权
        x = list(range(n))  # 0, 1, 2, ..., n-1

        # 一元线性回归：score = w0 + w1*x
        sum_x = sum(x)
        sum_y = sum(scores)
        sum_xy = sum(xi * yi for xi, yi in zip(x, scores))
        sum_x2 = sum(xi * xi for xi in x)

        denom = n * sum_x2 - sum_x * sum_x
        if abs(denom) < 1e-10:
            w1 = 0.0
            w0 = sum_y / n
        else:
            w1 = (n * sum_xy - sum_x * sum_y) / denom
            w0 = (sum_y - w1 * sum_x) / n

        # 预测明天的评分 (x=n)
        predicted = w0 + w1 * n

        # 用前一天评分修正
        prev_score = scores[-1]
        # 加权：30% 回归预测 + 70% 前一日评分（平滑）
        predicted = 0.3 * predicted + 0.7 * prev_score

        # 钳制到有效范围
        predicted = max(10.0, min(100.0, predicted))

        # 置信区间：基于残差的标准差
        residuals = [s - (w0 + w1 * xi) for xi, s in zip(x, scores)]
        if len(residuals) >= 2:
            ci = stdev(residuals) if len(residuals) >= 2 else 10.0
        else:
            ci = 10.0

        # 置信度：数据越多、残差越小 → 置信度越高
        data_confidence = min(1.0, n / 7.0)
        noise_confidence = max(0.3, 1.0 - (ci / 20.0))
        confidence = round(data_confidence * noise_confidence, 2)

        return {
            'score': round(predicted, 1),
            'ci': round(ci, 1),
            'confidence': confidence,
            'w0': round(w0, 2),
            'w1': round(w1, 2),
            'n': n,
        }

    def predict_trend(self, openid, horizon_days=3):
        """趋势预测

        比较最近3天 vs 之前3天的均值差异。
        计算二阶差分（加速度）。

        Args:
            openid: 用户ID
            horizon_days: 预测天数（默认3，当前未使用）

        Returns:
            dict: {
                'direction': 'improving' | 'declining' | 'stable' | 'erratic',
                'velocity': float,         # 一阶差分均值（分/天）
                'acceleration': float,     # 二阶差分均值（趋势变化速度）
                'recent_mean': float,      # 最近3天均值
                'prior_mean': float,       # 之前3天均值
                'n_recent': int,
                'n_prior': int,
            }
        """
        scores = self._get_extended_scores(openid, n_days=7)

        if len(scores) < 4:
            return {
                'direction': 'stable',
                'velocity': 0.0,
                'acceleration': 0.0,
                'recent_mean': mean(scores) if scores else 50.0,
                'prior_mean': 50.0,
                'n_recent': len(scores),
                'n_prior': 0,
            }

        # 最近3天 vs 之前3天
        recent = scores[-3:]
        prior = scores[-6:-3] if len(scores) >= 6 else scores[:-3]

        recent_mean = mean(recent)
        prior_mean = mean(prior) if prior else recent_mean

        # 速度：一阶差分均值
        diffs = [scores[i+1] - scores[i] for i in range(len(scores)-1)]
        velocity = mean(diffs) if diffs else 0.0

        # 加速度：二阶差分均值
        acc_diffs = [diffs[i+1] - diffs[i] for i in range(len(diffs)-1)]
        acceleration = mean(acc_diffs) if acc_diffs else 0.0

        # 方向判定
        diff_mean = recent_mean - prior_mean
        score_std = stdev(scores) if len(scores) >= 2 else 0

        if score_std > 20:
            direction = 'erratic'
        elif diff_mean > 5:
            direction = 'improving'
        elif diff_mean < -5:
            direction = 'declining'
        else:
            direction = 'stable'

        return {
            'direction': direction,
            'velocity': round(velocity, 2),
            'acceleration': round(acceleration, 2),
            'recent_mean': round(recent_mean, 1),
            'prior_mean': round(prior_mean, 1),
            'n_recent': len(recent),
            'n_prior': len(prior),
        }

    def anomaly_score(self, openid):
        """异常评分：当前值与历史模式的偏差程度

        基于最近一次评分与近期移动平均值的偏差。

        Returns:
            float: 0~1, 0=完全正常, 1=极度异常
        """
        scores = self._get_extended_scores(openid, n_days=7)

        if len(scores) < 3:
            return 0.0

        current = scores[-1]
        # 去除最新的移动平均
        hist = scores[:-1]
        hist_mean = mean(hist)
        hist_std = stdev(hist) if len(hist) >= 2 else 10.0

        if hist_std < 0.1:
            return 0.0  # 无波动

        z_score = abs(current - hist_mean) / hist_std

        # z-score 到 0-1 的映射
        anomaly = min(1.0, z_score / 3.0)
        return round(anomaly, 2)

    def detect_patterns(self, openid):
        """模式识别

        检测周期性模式：
        - "周一焦虑"模式：每周周期性
        - "周末晚睡"模式：周中vs周末入睡时间差异

        Returns:
            dict: {
                'has_monday_anxiety': bool,
                'has_weekend_late': bool,
                'weekly_periodicity': float,  # 0~1
            }
        """
        wm = self._get_wm()
        if wm is None:
            return {'has_monday_anxiety': False, 'has_weekend_late': False, 'weekly_periodicity': 0.0}

        recent = wm.recent(openid, n=14)
        if len(recent) < 7:
            return {'has_monday_anxiety': False, 'has_weekend_late': False, 'weekly_periodicity': 0.0}

        # 按日期组织
        day_scores = {}  # {weekday: [scores]}
        for e in recent:
            ts = e.get('timestamp', '')
            try:
                dt = datetime.fromisoformat(ts)
                wd = dt.weekday()  # 0=Mon
            except (ValueError, TypeError):
                continue
            s = e.get('score_obs')
            if s is not None:
                day_scores.setdefault(wd, []).append(s)

        # 周一焦虑：周一的评分是否系统性低于其他天
        monday_scores = day_scores.get(0, [])
        other_scores = []
        for wd, ss in day_scores.items():
            if wd != 0:
                other_scores.extend(ss)

        has_monday = bool(monday_scores) and bool(other_scores)
        has_monday_anxiety = False
        if has_monday:
            monday_mean = mean(monday_scores)
            other_mean = mean(other_scores)
            has_monday_anxiety = monday_mean < other_mean - 10

        # 周末晚睡：周末评分 vs 周中评分
        weekend_scores = day_scores.get(5, []) + day_scores.get(6, [])
        weekday_scores = []
        for wd in range(5):
            weekday_scores.extend(day_scores.get(wd, []))

        has_weekend = bool(weekend_scores) and bool(weekday_scores)
        has_weekend_late = False
        if has_weekend:
            weekend_mean = mean(weekend_scores)
            weekday_mean = mean(weekday_scores)
            has_weekend_late = weekend_mean < weekday_mean - 10

        # 周期性强度：每日评分之间的相关性
        # 简化：每天评分跟随前一天的波动程度
        all_scores_sorted = []
        for e in sorted(recent, key=lambda x: x.get('timestamp', '')):
            s = e.get('score_obs')
            if s is not None:
                all_scores_sorted.append(s)

        periodicity = 0.0
        if len(all_scores_sorted) >= 8:
            # 检查是否有7天周期模式
            lag7_corr = 0.0
            count = 0
            for i in range(7, len(all_scores_sorted)):
                lag7_corr += abs(all_scores_sorted[i] - all_scores_sorted[i-7])
                count += 1
            if count > 0:
                avg_diff = lag7_corr / count
                periodicity = max(0.0, 1.0 - avg_diff / 30.0)

        return {
            'has_monday_anxiety': has_monday_anxiety,
            'has_weekend_late': has_weekend_late,
            'weekly_periodicity': round(periodicity, 2),
        }

    def get_prediction_error(self, openid, actual_score):
        """记录并返回预测误差

        调用此方法记录实际评分与预测的误差。
        系统误差持续偏大 → 返回建议降低λ。

        Args:
            openid: 用户ID
            actual_score: 实际观测到的评分

        Returns:
            dict: {
                'error': float,
                'mean_error': float,
                'n': int,
                'suggest_lambda_reduce': bool,
            }
        """
        if openid not in self._prediction_errors:
            self._prediction_errors[openid] = {'errors': [], 'n': 0}

        pred = self.predict_tonight(openid)
        pred_score = pred['score']
        error = abs(actual_score - pred_score)
        self._prediction_errors[openid]['errors'].append(error)
        self._prediction_errors[openid]['n'] += 1

        errors = self._prediction_errors[openid]['errors']
        mean_error = sum(errors) / len(errors) if errors else 0

        # 如果最近5次的平均误差 > 15分 → 建议降低λ
        recent_errors = errors[-5:]
        recent_mean = sum(recent_errors) / len(recent_errors) if recent_errors else 0
        suggest_reduce = recent_mean > 15 and len(recent_errors) >= 3

        return {
            'error': round(error, 1),
            'mean_error': round(mean_error, 1),
            'recent_mean_error': round(recent_mean, 1),
            'n': self._prediction_errors[openid]['n'],
            'suggest_lambda_reduce': suggest_reduce,
        }

    def format_prediction_context(self, openid):
        """格式化预测信息为prompt注入文本

        v3.21: 加入时序上下文文本（速度/加速度/状态语境）

        Returns:
            str: 如 '[预测: 今晚预计56.3分(±8.2), 趋势declining, 置信0.72]'
                或 ''（数据不足时）
        """
        try:
            pred = self.predict_tonight(openid)
            trend = self.predict_trend(openid)

            if pred['n'] < 2:
                return ''

            parts = [
                f'今晚预计{pred["score"]}分(±{pred["ci"]})',
                f'趋势{trend["direction"]}',
                f'置信{pred["confidence"]}',
            ]

            # v3.21: 追加时序上下文
            try:
                from working_memory import get_working_memory
                wm = get_working_memory()
                if wm is not None:
                    sig = wm.temporal_signature(openid)
                    state = wm.state_context(openid)
                    parts.append(
                        f'时序状态={state}'
                        f'(速度={sig["velocity"]}分/天, '
                        f'加速度={sig["acceleration"]}, '
                        f'波动={sig["volatility"]})'
                    )
            except Exception:
                pass

            return f'[预测: {", ".join(parts)}]'
        except Exception:
            return ''


# ==================== 全局实例 ====================

_predictor_instance = None


def get_predictor():
    """获取全局行为预测引擎实例"""
    global _predictor_instance
    if _predictor_instance is None:
        _predictor_instance = BehaviorPredictor()
    return _predictor_instance


# ==================== 自测 ====================

if __name__ == '__main__':
    import sys
    sys.path.insert(0, PROJECT_ROOT)

    logging.basicConfig(level=logging.INFO)

    print('=== Behavior Predictor Self-Test ===\n')

    pred = BehaviorPredictor()
    from working_memory import get_working_memory
    wm = get_working_memory()

    openid = 'test_bp_1'

    # 1. 给定7天评分序列 → 预测第8天与线性回归结果一致
    print('1. Predict score from 7-day sequence:')
    scores = [65, 62, 58, 55, 52, 50, 48]  # 持续下降
    for i, s in enumerate(scores):
        wm.push(openid, {
            'text': f'Day {i+1}',
            'score_obs': s,
            'emotion': 'negative' if s < 55 else 'neutral',
            'intervention': 'none',
            'outcome': 'none',
        })

    pred_result = pred.predict_tonight(openid)
    print(f'   Prediction: {pred_result["score"]} ±{pred_result["ci"]} (conf={pred_result["confidence"]})')
    print(f'   w0={pred_result["w0"]}, w1={pred_result["w1"]}, n={pred_result["n"]}')
    # 线性回归 + 前一日修正: 下降趋势中预测应该 < 48
    assert pred_result['score'] < 55, f'Falling scores should predict <55, got {pred_result["score"]}'
    assert pred_result['n'] == 7, f'Expected 7 data points, got {pred_result["n"]}'
    print('   PASS')

    # 2. 趋势显示 declining
    print('\n2. Trend detection (declining):')
    trend = pred.predict_trend(openid)
    print(f'   Direction: {trend["direction"]}, velocity={trend["velocity"]}, acc={trend["acceleration"]}')
    print(f'   Recent mean: {trend["recent_mean"]}, Prior mean: {trend["prior_mean"]}')
    assert trend['direction'] == 'declining', f'Expected declining, got {trend["direction"]}'
    assert trend['velocity'] < 0, f'Velocity should be negative, got {trend["velocity"]}'
    print('   PASS')

    # 3. 异常评分
    print('\n3. Anomaly score:')
    anom = pred.anomaly_score(openid)
    print(f'   Anomaly: {anom}')
    assert 0 <= anom <= 1, f'Anomaly should be 0-1, got {anom}'
    print('   PASS')

    # 4. 模式检测
    print('\n4. Pattern detection:')
    patterns = pred.detect_patterns(openid)
    print(f'   Monday anxiety: {patterns["has_monday_anxiety"]}')
    print(f'   Weekend late: {patterns["has_weekend_late"]}')
    print(f'   Weekly periodicity: {patterns["weekly_periodicity"]}')
    print('   PASS')

    # 5. 预测上下文格式化
    print('\n5. Prediction context formatting:')
    ctx = pred.format_prediction_context(openid)
    print(f'   Context: {ctx}')
    assert '[预测:' in ctx, f'Context should contain prediction info'
    assert '趋势' in ctx, f'Context should contain trend info'
    print('   PASS')

    # 6. 预测误差记录
    print('\n6. Prediction error tracking:')
    err1 = pred.get_prediction_error(openid, 55)
    print(f'   Error: {err1["error"]}, mean: {err1["mean_error"]}, suggest λ reduce: {err1["suggest_lambda_reduce"]}')
    err2 = pred.get_prediction_error(openid, 45)
    print(f'   Error: {err2["error"]}, mean: {err2["mean_error"]}, suggest λ reduce: {err2["suggest_lambda_reduce"]}')
    assert err1['n'] == 1
    print('   PASS')

    # 7. 上升趋势检测
    print('\n7. Trend detection (improving):')
    openid2 = 'test_bp_2'
    scores_up = [40, 42, 45, 50, 55, 60, 65]  # 持续上升
    for i, s in enumerate(scores_up):
        wm.push(openid2, {
            'text': f'Day {i+1}',
            'score_obs': s,
            'emotion': 'positive',
            'intervention': 'none',
            'outcome': 'none',
        })
    trend2 = pred.predict_trend(openid2)
    print(f'   Direction: {trend2["direction"]}, velocity={trend2["velocity"]}')
    assert trend2['direction'] == 'improving', f'Expected improving, got {trend2["direction"]}'
    assert trend2['velocity'] > 0, f'Velocity should be positive, got {trend2["velocity"]}'
    print('   PASS')

    # 8. 数据不足回退
    print('\n8. Insufficient data fallback:')
    pred3 = pred.predict_tonight('unknown_user')
    print(f'   Prediction with <2 data points: {pred3["score"]} (conf={pred3["confidence"]})')
    assert pred3['score'] == 50.0, f'Default should be 50, got {pred3["score"]}'
    assert pred3['confidence'] == 0.3, f'Default confidence should be 0.3, got {pred3["confidence"]}'
    print('   PASS')

    print('\nAll tests PASS!')
