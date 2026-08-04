#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
predictive_coding.py — AISleepGen 预测编码引擎 v1.0

范式跃迁：从"规则驱动的干预系统" → "自我修正的预测系统"

核心思想（自由能原理 / 预测编码）：
  大脑不是被动处理输入，而是主动生成预测，并通过预测误差来更新模型。
  用户的每个行为（聊天/填问卷/接受建议/忽略推送）都是"实际输入"。
  系统在每次输入后，计算所有层的预测误差，反向传播更新各层模型。

三层预测架构：
  高层: 睡眠评分预测 (score_layer) — "今晚能睡几分"
  中层: 昼夜节律预测 (circadian_layer) — "会在几点入睡"
  低层: 干预响应预测 (response_layer) — "用户会对什么做出反应"

  ┌──────────────────────────────────────┐
  │  高层: score_layer                   │  prediction_error_up
  │  预测: 今晚评分                      │  ◄────────────
  ├──────────────────────────────────────┤
  │  中层: circadian_layer               │  prediction_error_up
  │  预测: 入睡时间 + 节律相位           │  ◄────────────
  ├──────────────────────────────────────┤
  │  低层: response_layer                │  prediction_error_up
  │  预测: 用户对推送/建议/陪伴的反应     │  ◄────────────
  └──────────────────────────────────────┘
         │         │          │
         ▼         ▼          ▼
      实际输入   实际输入    实际输入
      (评分)    (入睡时间)  (反馈)

每次新数据 → 计算各层预测误差 → 向上传播 → 更新预测

这不是"加一个新功能"，而是重构整个系统的决策逻辑：
  - 旧: "评分低→推送" (因果)
  - 新: "评分预测误差大 → 需要更多信息来降低不确定性" (预测编码)
"""


def _load_meta_param(param, default=None, openid=None):
    """从元学习params读参数（支持用户级覆盖）"""
    import json, os
    try:
        base = os.path.dirname(__file__)
        # 先读用户级
        if openid:
            safe = openid.replace('/', '_').replace('\\', '_')
            upath = os.path.join(base, 'data', 'params', safe + '.json')
            if os.path.exists(upath):
                with open(upath, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                if param in d:
                    return d[param]
        # 后读全局
        p = os.path.join(base, 'data', 'params.json')
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                d = json.load(f)
            return d.get(param, default)
    except Exception as _e:
        _log = logging.getLogger('predictive_coding')
        _log.warning('get_param failed: %s', _e)
    return default

import json, os, time, logging, math
from datetime import datetime, timedelta
from collections import defaultdict

_pc_log = logging.getLogger('aisleepgen.predictive_coding')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ==================== 预测层定义 ====================

class PredictionLayer:
    """通用预测层

    每一层维护：
      - prediction: 当前的预测值
      - uncertainty: 预测不确定性 (0=确定, 大=不确定)
      - error_history: 最近N次预测误差
      - update_count: 更新次数（影响收敛速度）
    """
    def __init__(self, name, default_prediction=0.5, default_uncertainty=0.5):
        self.name = name
        self.prediction = default_prediction
        self.uncertainty = default_uncertainty
        self.error_history = []
        self.update_count = 0
        self.prediction_log = []  # [(timestamp, predicted, actual, error)]

    def predict(self):
        """返回当前预测值 + 不确定性"""
        return {
            'value': self.prediction,
            'uncertainty': self.uncertainty,
            'confidence': max(0.0, 1.0 - self.uncertainty),
            'updates': self.update_count,
        }

    def compute_error(self, actual):
        """计算预测误差 (actual - prediction)

        正误差 = 预测偏保守
        负误差 = 预测偏乐观
        """
        if isinstance(actual, (int, float)):
            return actual - self.prediction
        return 0

    def update(self, actual, learning_rate=None):
        if learning_rate is None:
            learning_rate = _load_meta_param("learning_rate", 0.3)
        """用实际值更新预测

        预测编码核心：prediction += learning_rate * prediction_error
        不确定性每次更新后衰减（但如果有大误差，不确定性回升）

        Args:
            actual: 实际观测值
            learning_rate: 学习率（越大越快地适应新数据）

        Returns:
            float: 本次的预测误差
        """
        error = self.compute_error(actual)
        self.error_history.append(error)
        if len(self.error_history) > 20:
            self.error_history = self.error_history[-20:]

        # 更新预测
        self.prediction += learning_rate * error
        self.update_count += 1

        # 更新不确定性
        # 误差越大不确定性越高，但更新次数多会降低不确定性
        recent_errors = self.error_history[-5:]
        if recent_errors:
            mean_abs_error = sum(abs(e) for e in recent_errors) / len(recent_errors)
            # 不确定性 = 平均绝对误差 * 衰减因子
            decay = max(0.1, 1.0 - (self.update_count / 50))
            self.uncertainty = min(0.9, mean_abs_error * decay / 100)
        else:
            self.uncertainty = min(0.9, self.uncertainty * 0.9)

        # 记录
        self.prediction_log.append({
            'ts': time.time(),
            'predicted': self.prediction - learning_rate * error,  # 更新前的预测
            'actual': actual,
            'error': error,
        })
        if len(self.prediction_log) > 100:
            self.prediction_log = self.prediction_log[-100:]

        return error


class HierarchicalPredictor:
    """分层预测编码器

    维护三个层次的预测，支持误差反向传播。

    Usage:
        hp = HierarchicalPredictor()
        hp.load_from_profile(profile)

        # 填完问卷后更新
        hp.update_from_survey(bedtime='23:30', score=62)

        # 获取综合预测
        pred = hp.predict_tonight()
        # -> {'score': 57, 'bedtime': '23:15', 'intervention_response': 0.3, ...}
    """

    def __init__(self):
        # 三层预测
        self.score_layer = PredictionLayer('score', default_prediction=50, default_uncertainty=0.8)
        self.circadian_layer = PredictionLayer('circadian', default_prediction=23.5, default_uncertainty=0.7)
        self.response_layer = PredictionLayer('response', default_prediction=0.5, default_uncertainty=0.6)

        # 层间交叉影响矩阵
        # cross_weights[from_layer][to_layer] = 影响系数
        self.cross_weights = {
            'circadian_to_score': 0.2,   # 节律预测偏差 → 评分预测修正
            'response_to_score': 0.1,    # 干预响应偏差 → 评分预测修正
        }

        self.total_updates = 0

    def predict_tonight(self, openid=None):
        """综合三层预测，输出今晚预测。

        Returns:
            dict: {
                'score': float,           # 预测评分
                'bedtime': float,         # 预测入睡时间（小数小时）
                'bedtime_str': str,       # 预测入睡时间（HH:MM）
                'intervention_effect': float,  # 预测干预效果
                'uncertainty': float,     # 综合不确定性
                'should_interact': bool,  # 不确定性高 → 需要互动
                'confidence': str,        # 'high' | 'medium' | 'low'
            }
        """
        score_pred = self.score_layer.predict()
        circ_pred = self.circadian_layer.predict()
        resp_pred = self.response_layer.predict()

        # 交叉传播：下层误差影响上层
        adjusted_score = score_pred['value']

        # 如果节律预测不确定性高 → 评分预测也降低置信度
        score_uncertainty = score_pred['uncertainty']
        circ_uncertainty = circ_pred['uncertainty']
        combined_uncertainty = (score_uncertainty * 0.6 + circ_uncertainty * 0.3 +
                                resp_pred['uncertainty'] * 0.1)

        # 入睡时间格式
        bt_hour = circ_pred['value']
        bt_hour_display = bt_hour % 24  # 凌晨加24的处理
        bt_h = int(bt_hour_display)
        bt_m = int((bt_hour_display - bt_h) * 60)
        bt_str = f'{bt_h:02d}:{bt_m:02d}'
        if bt_hour >= 24:
            bt_str = f'{bt_h-24 if bt_h < 24 else bt_h:02d}:{bt_m:02d} (翌日)'

        # 决策：不确定性高 → 需要互动（主动获取信息）
        should_interact = combined_uncertainty > 0.4

        confidence = 'high' if combined_uncertainty < 0.2 else (
            'medium' if combined_uncertainty < 0.5 else 'low'
        )

        return {
            'score': round(adjusted_score, 1),
            'bedtime': round(bt_hour, 2),
            'bedtime_str': bt_str,
            'intervention_effect': round(resp_pred['value'], 2),
            'uncertainty': round(combined_uncertainty, 2),
            'should_interact': should_interact,
            'confidence': confidence,
            'layers': {
                'score': score_pred,
                'circadian': circ_pred,
                'response': resp_pred,
            }
        }

    def update_from_survey(self, profile, bedtime='', score=0):
        """用户填完睡眠问卷 → 更新所有层

        Args:
            profile: 用户画像（用于读写持久化数据）
            bedtime: 用户填的入睡时间 (HH:MM)
            score: 用户填的/系统算的睡眠评分

        Returns:
            dict: 各层的预测误差
        """
        errors = {}

        # 1. 更新评分层
        if score > 0:
            score_error = self.score_layer.update(score)
            errors['score_error'] = round(score_error, 1)
        else:
            errors['score_error'] = 0

        # 2. 更新节律层（入睡时间）
        if bedtime:
            from circadian_phase_model import _hours_from_time
            bt_hours = _hours_from_time(bedtime)
            if bt_hours is not None:
                circ_error = self.circadian_layer.update(bt_hours)
                errors['circadian_error'] = round(circ_error, 1)

                # 交叉传播：节律误差 → 评分预测修正
                if score > 0:
                    cross = self.cross_weights['circadian_to_score']
                    # 如果节律预测有大误差（>1小时），稍微修正评分预测
                    if abs(circ_error) > 1:
                        self.score_layer.prediction += circ_error * cross * 0.5
        else:
            errors['circadian_error'] = 0

        self.total_updates += 1
        errors['total_updates'] = self.total_updates

        self._save_to_profile(profile)
        return errors

    def update_from_intervention_feedback(self, profile, feedback_type, positive=True):
        """用户对干预（推送/建议/陪伴）给出反馈 → 更新响应层

        Args:
            profile: 用户画像
            feedback_type: 'push' | 'suggestion' | 'companion'
            positive: 是否正面反馈

        Returns:
            float: 预测误差
        """
        # 响应值：正面=1.0, 负面=0.0
        actual = 1.0 if positive else 0.0
        error = self.response_layer.update(actual)

        # 交叉传播：响应误差 → 评分层
        cross = self.cross_weights['response_to_score']
        self.score_layer.prediction += error * cross

        self._save_to_profile(profile)
        return error

    def should_intervene(self, openid):
        """预测编码驱动的干预决策

        取代旧的"score < 50 → push"逻辑。
        如果预测不确定性高 → 需要互动获取信息。
        如果预测确定且评分低 → 才推送。

        Returns:
            dict: {
                'intervene': bool,
                'reason': str,
                'uncertainty': float,
                'mode': 'chat' | 'push' | 'skip',
            }
        """
        pred = self.predict_tonight(openid)

        # 决策树（替代旧的 push_decision 规则）
        if pred['uncertainty'] > 0.6:
            # 极度不确定 → 需要主动获取信息，但用轻量方式（聊天>推送）
            return {
                'intervene': True,
                'reason': f'high_uncertainty({pred["uncertainty"]:.2f})',
                'uncertainty': pred['uncertainty'],
                'mode': 'chat',  # 对话方式比推送更柔和
                'prediction': pred,
            }
        elif pred['uncertainty'] > 0.4:
            # 中等不确定 + 评分低 → 推送
            if pred['score'] < 55:
                return {
                    'intervene': True,
                    'reason': f'moderate_uncertainty({pred["uncertainty"]:.2f})_low_score({pred["score"]})',
                    'uncertainty': pred['uncertainty'],
                    'mode': 'push',
                    'prediction': pred,
                }
            else:
                return {
                    'intervene': False,
                    'reason': f'medium_uncertainty_but_score_ok({pred["score"]})',
                    'uncertainty': pred['uncertainty'],
                    'mode': 'skip',
                    'prediction': pred,
                }
        else:
            # 低不确定性 → 系统有把握
            if pred['score'] < 50:
                # 真的不好 → 推
                return {
                    'intervene': True,
                    'reason': f'confident_low_score({pred["score"]})',
                    'uncertainty': pred['uncertainty'],
                    'mode': 'push',
                    'prediction': pred,
                }
            else:
                return {
                    'intervene': False,
                    'reason': f'confident_ok',
                    'uncertainty': pred['uncertainty'],
                    'mode': 'skip',
                    'prediction': pred,
                }

    def _save_to_profile(self, profile):
        """持久化预测编码器状态到用户画像"""
        if not isinstance(profile, dict):
            return
        profile['_predictive_coding'] = {
            'score': {
                'prediction': self.score_layer.prediction,
                'uncertainty': self.score_layer.uncertainty,
                'update_count': self.score_layer.update_count,
            },
            'circadian': {
                'prediction': self.circadian_layer.prediction,
                'uncertainty': self.circadian_layer.uncertainty,
                'update_count': self.circadian_layer.update_count,
            },
            'response': {
                'prediction': self.response_layer.prediction,
                'uncertainty': self.response_layer.uncertainty,
                'update_count': self.response_layer.update_count,
            },
            'cross_weights': self.cross_weights,
            'total_updates': self.total_updates,
        }

    def load_from_profile(self, profile):
        """从用户画像恢复预测编码器状态"""
        if not isinstance(profile, dict):
            return
        saved = profile.get('_predictive_coding')
        if not saved:
            return

        try:
            s = saved.get('score', {})
            self.score_layer.prediction = s.get('prediction', 50)
            self.score_layer.uncertainty = s.get('uncertainty', 0.8)
            self.score_layer.update_count = s.get('update_count', 0)

            c = saved.get('circadian', {})
            self.circadian_layer.prediction = c.get('prediction', 23.5)
            self.circadian_layer.uncertainty = c.get('uncertainty', 0.7)
            self.circadian_layer.update_count = c.get('update_count', 0)

            r = saved.get('response', {})
            self.response_layer.prediction = r.get('prediction', 0.5)
            self.response_layer.uncertainty = r.get('uncertainty', 0.6)
            self.response_layer.update_count = r.get('update_count', 0)

            cw = saved.get('cross_weights', {})
            if cw:
                self.cross_weights.update(cw)

            self.total_updates = saved.get('total_updates', 0)
        except Exception as e:
            _pc_log.warning('[PC] Failed to load state: %s', e)

    def get_uncertainty_report(self):
        """输出各层不确定性报告（用于诊断和展示）"""
        return {
            'overall_uncertainty': self.predict_tonight()['uncertainty'],
            'layers': {
                'score': self.score_layer.predict(),
                'circadian': self.circadian_layer.predict(),
                'response': self.response_layer.predict(),
            },
            'total_updates': self.total_updates,
            'cross_weights': self.cross_weights,
        }


# ==================== 公开 API ====================

def get_predictor_for_user(openid):
    """获取用户的分层预测编码器

    Args:
        openid: 用户ID

    Returns:
        HierarchicalPredictor
    """
    hp = HierarchicalPredictor()
    try:
        from profile_storage import _load_user_profile
        profile = _load_user_profile(openid)
        hp.load_from_profile(profile)
    except Exception as e:
        _pc_log.warning('[PC] Load failed for %s: %s', str(openid)[:8], e)
    return hp


def update_predictor_from_survey(openid, bedtime, score):
    """用户填问卷后更新预测编码器

    Returns:
        dict: 更新前后的对比
    """
    hp = get_predictor_for_user(openid)
    before = hp.predict_tonight(openid)

    # 加载profile做持久化
    from profile_storage import _load_user_profile, _atomic_write_profile
    profile = _load_user_profile(openid)
    hp.load_from_profile(profile)

    errors = hp.update_from_survey(profile, bedtime=bedtime, score=score)

    # 持久化
    _atomic_write_profile(openid, lambda p: hp._save_to_profile(p) or p)

    after = hp.predict_tonight(openid)
    return {
        'before': before,
        'after': after,
        'errors': errors,
    }


# ==================== 自测 ====================
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    hp = HierarchicalPredictor()

    # 模拟用户首次填问卷
    print('=== Before any data ===')
    pred = hp.predict_tonight()
    print(f'  Score: {pred["score"]} (uncertainty={pred["uncertainty"]:.2f})')
    print(f'  Bedtime: {pred["bedtime_str"]}')
    print(f'  Should interact: {pred["should_interact"]}')
    assert pred['uncertainty'] > 0.5  # 初始应该高不确定性

    # 模拟填了5天问卷
    print('\n=== After 5 survey entries ===')
    test_data = [
        ('23:30', 62),
        ('23:15', 65),
        ('23:45', 58),
        ('00:00', 52),
        ('23:50', 55),
    ]
    profile = {'_predictive_coding': {}}
    for bedtime, score in test_data:
        errors = hp.update_from_survey(profile, bedtime=bedtime, score=score)
        print(f'  {bedtime} score={score} -> circ_error={errors.get("circadian_error")} score_error={errors.get("score_error")}')

    pred2 = hp.predict_tonight()
    print(f'\n  After: Score={pred2["score"]} confidence={pred2["confidence"]}')
    print(f'  Bedtime: {pred2["bedtime_str"]}')
    print(f'  Uncertainty: {pred2["uncertainty"]:.2f}')
    print(f'  Should interact: {pred2["should_interact"]}')
    assert pred2['uncertainty'] < 0.5  # 5次后应该降低不确定性

    # 测试 predict_tonight output matches
    assert 'score' in pred2
    assert 'uncertainty' in pred2
    assert 'should_interact' in pred2

    # 测试干预决策
    print('\n=== Intervention decision ===')
    decision = hp.should_intervene('test_user')
    print(f'  Intervene: {decision["intervene"]} reason={decision["reason"]} mode={decision["mode"]}')

    # 加载/保存循环
    print('\n=== Persistence cycle ===')
    profile2 = {'_predictive_coding': {}}
    hp._save_to_profile(profile2)
    assert '_predictive_coding' in profile2

    hp2 = HierarchicalPredictor()
    hp2.load_from_profile(profile2)
    pred3 = hp2.predict_tonight()
    assert abs(pred3['score'] - pred2['score']) < 0.5  # 应该接近
    print(f'  Reloaded: Score={pred3["score"]} (diff={abs(pred3["score"]-pred2["score"]):.2f})')

    # 模拟介入反馈
    print('\n=== Intervention feedback ===')
    hp2.update_from_intervention_feedback(profile2, 'push', positive=True)
    hp2.update_from_intervention_feedback(profile2, 'push', positive=True)
    hp2.update_from_intervention_feedback(profile2, 'push', positive=False)
    resp = hp2.response_layer.predict()
    print(f'  Response prediction: {resp["value"]:.2f} (uncertainty={resp["uncertainty"]:.2f})')

    print('\nAll tests PASS!')
