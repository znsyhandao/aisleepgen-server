#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prediction_engine.py — AISleepGen 睡眠预测引擎

基于用户历史数据，预测今晚/明晚的睡眠质量（总评分）。

本质：轻量线性趋势模型，不需要大模型，不需要训练。
"""

import json
import os
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def predict_tonight(profile, openid=None):
    """预测今晚的睡眠总评分

    v3.0: 增强——注入昼夜节律相位约束。

    Args:
        profile: 用户画像 dict
        openid: 用户ID (可选，用于读取节律数据)

    输出：{
        'predicted_score': 57.0,        # 预测评分
        'confidence': 'high'|'medium'|'low',  # 置信度
        'direction': 'worse'|'stable'|'better',  # 相比个人基线
        'key_concern': 'latency'|'awake'|'duration'|'circadian'|'unknown',  # 主要风险维度
        'samples': 12,                  # 用于预测的数据点数
        'circadian_lift': 0,            # v3.0: 节律相位调整量
        'circadian_risk': False,        # v3.0: 是否因节律风险下调
    }
    如果数据不足，返回 None
    """
    result = _base_predict(profile)
    if result is None:
        return None

    # v3.0: 昼夜节律相位增强
    circadian_lift = 0
    circadian_risk = False
    try:
        if openid:
            from circadian_phase_model import get_drowsiness_forecast
            forecast = get_drowsiness_forecast(openid)
            if forecast.get('available'):
                params = forecast.get('parameters', {})
                drift_rate = params.get('drift_rate', 0)
                acrophase = params.get('acrophase', 16)

                if drift_rate > 15:
                    circadian_lift -= 4
                    circadian_risk = True
                    result['key_concern'] = 'circadian'
                elif drift_rate > 5:
                    circadian_lift -= 2
                    circadian_risk = True

                amp = params.get('amplitude', 10)
                if amp < 8:
                    if result['confidence'] == 'high':
                        result['confidence'] = 'medium'
                    elif result['confidence'] == 'medium':
                        result['confidence'] = 'low'

                circadian_lift = max(-10, min(5, circadian_lift))
    except ImportError:
        pass
    except Exception as e:
        import logging
        logging.getLogger('aisleepgen.prediction').warning(
            '[Prediction] Circadian failed: %s', str(e)[:100])

    result['predicted_score'] = max(10, min(100,
        result['predicted_score'] + circadian_lift))
    result['circadian_lift'] = circadian_lift
    result['circadian_risk'] = circadian_risk

    if circadian_lift < -2 and result['direction'] == 'stable':
        result['direction'] = 'worse'

    return result


def _base_predict(profile):
    """原 predict_tonight 逻辑（改名以便节律增强入口）"""
    history = profile.get('history', [])
    if not history:
        # 虽然没 history，但如果有偏差数据，给一个带偏差的默认预测
        if profile.get('_prediction_bias', {}).get('count', 0) > 0:
            default_pred = {'predicted_score': 50, 'confidence': 'low', 'direction': 'stable',
                          'baseline': 50, 'key_concern': 'unknown', 'samples': 0}
            return apply_prediction_bias(profile, default_pred)
        return None

    # 提取有评分的记录，按日期排序
    records = []
    for h in history:
        if not isinstance(h, dict):
            continue
        score = h.get('wm_score', 0)
        date_str = h.get('date', '')
        if score > 0 and date_str:
            records.append({'date': date_str, 'score': score})

    if len(records) < 3:
        # 数据太少，用最新评分 + 方向估计
        if len(records) == 0:
            return None
        latest_score = records[-1]['score']
        if latest_score < 60:
            direction = 'worse'  # 低于 60 分需要关注
            predicted = latest_score - 5
        elif latest_score > 80:
            direction = 'better'
            predicted = latest_score + 3
        else:
            direction = 'stable'
            predicted = latest_score
        return {
            'predicted_score': round(predicted, 1),
            'confidence': 'low',
            'direction': direction,
            'baseline': round(latest_score, 1),
            'key_concern': 'unknown',
            'samples': len(records),
        }

    # 按日期排序
    records.sort(key=lambda x: x['date'])
    n = len(records)

    # 计算个人基线（所有评分的中位数/均值）
    scores = [r['score'] for r in records]
    baseline = sum(scores) / n

    # 最近 5 条的趋势
    recent = records[-5:] if n >= 5 else records
    recent_scores = [r['score'] for r in recent]

    recent_avg = sum(recent_scores) / len(recent_scores)

    # 简单回归：用最近分数 vs 早前分数看方向
    if len(recent_scores) >= 3:
        # 最近 3 条
        last_3 = recent_scores[-3:]
        trend = (last_3[-1] - last_3[0]) / max(len(last_3) - 1, 1)
        # 如果明确下降且绝对值>5分，预测更差
        if trend < -2:
            direction = 'worse'
            predicted = recent_avg + trend * 1.5  # 趋势外推
        elif trend > 2:
            direction = 'better'
            predicted = recent_avg + trend * 1.5
        else:
            direction = 'stable'
            predicted = recent_avg
    else:
        direction = 'stable'
        predicted = recent_avg

    # 置信度
    if n >= 10:
        confidence = 'high'
    elif n >= 5:
        confidence = 'medium'
    else:
        confidence = 'low'

    # 压制到合理范围
    predicted = max(10, min(100, predicted))

    # 判断主要风险维度
    key_concern = 'unknown'
    # 检查是否有最新的结构化字段数据
    latest = profile.get('latest', {}) or {}
    if latest.get('sleep_latency', 0) > 60:
        key_concern = 'latency'
    elif latest.get('awake_times', 0) >= 2:
        key_concern = 'awake'
    elif latest.get('total_duration', 480) < 360:
        key_concern = 'duration'

    # 构建结果
    result = {
        'predicted_score': round(predicted, 1),
        'confidence': confidence,
        'direction': direction,
        'baseline': round(baseline, 1),
        'key_concern': key_concern,
        'samples': n,
    }

    # 存一份到 profile 供 analyze 阶段的偏差记录使用
    if isinstance(profile, dict):
        profile['_last_prediction'] = result

    return apply_prediction_bias(profile, result)


def apply_prediction_bias(profile, prediction):
    """对预测应用用户个性化偏差矫正

    每个用户有自己的预测偏差（系统预测 vs 实际评分）
    偏差每累积 3 条后收敛，最多 ±15 分
    """
    bias_record = profile.get('_prediction_bias', {})
    bias = bias_record.get('bias', 0.0)  # 已有偏差
    count = bias_record.get('count', 0)

    if count > 0 and isinstance(prediction, dict) and prediction.get('predicted_score'):
        adjustment = bias / max(count, 1)
        # 偏差收敛：偏差越大，调整幅度越小（反比）
        decay = max(0.3, 1.0 - (count / 20))  # 20条后收敛到0.3倍
        delta = round(adjustment * decay, 1)
        prediction['predicted_score'] = max(10, min(100,
            prediction['predicted_score'] + delta))
        prediction['bias_adjusted'] = True
        prediction['bias_delta'] = delta
    else:
        prediction['bias_adjusted'] = False
        prediction['bias_delta'] = 0

    return prediction


def record_prediction_discrepancy(profile, actual_score, prediction):
    """记录预测偏差（实际 vs 预测），用于自适应调优

    在 handle_sleep_analyze 中每次分析后调用
    偏差 = 实际评分 - 预测评分（正=预测保守，负=预测乐观）
    """
    predicted = prediction.get('predicted_score', 0) if prediction else 0
    if not predicted or not actual_score:
        return profile

    discrepancy = actual_score - predicted
    # 只记录超过 ±5 分的明显偏差
    if abs(discrepancy) < 5:
        return profile

    record = profile.setdefault('_prediction_bias', {})
    discrepancies = record.setdefault('discrepancies', [])
    discrepancies.append({
        'actual': actual_score,
        'predicted': predicted,
        'discrepancy': discrepancy,
        'timestamp': __import__('time').time(),
    })

    # 保留最近 20 条
    if len(discrepancies) > 20:
        discrepancies = discrepancies[-20:]

    # 计算加权平均偏差（最近偏差权重大）
    if discrepancies:
        total_weight = 0
        weighted_sum = 0
        for i, d in enumerate(discrepancies):
            w = 1 + i * 0.1  # 时间权重：越近权重越大
            weighted_sum += d['discrepancy'] * w
            total_weight += w
        new_bias = weighted_sum / total_weight
        # 封顶 ±15
        record['bias'] = max(-15, min(15, new_bias))
        record['count'] = len(discrepancies)

    return profile


def get_prediction_bias_summary(profile):
    """获取预测偏差摘要（用于调试）"""
    record = profile.get('_prediction_bias', {})
    if not record.get('count'):
        return '无偏差数据'
    return f'偏差={record.get("bias", 0):.1f}分 (样本={record.get("count", 0)})'


# ===== 快速测试 =====
if __name__ == '__main__':
    # 模拟一个用户的历史
    profile = {
        'latest': {'sleep_latency': 45, 'awake_times': 2, 'total_duration': 380},
        'history': [
            {'date': (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'),
             'wm_score': max(30, min(100, 65 + (i % 3) * 5 - i * 2))}
            for i in range(10)
        ]
    }
    r = predict_tonight(profile)
    print('Prediction:', r)

# ===== Trend Data API =====

def get_trend_data(profile):
    """Get 14-day trend data with prediction (frontend-ready)"""
    history = profile.get('history', [])
    records = []
    for h in history:
        if not isinstance(h, dict):
            continue
        score = h.get('wm_score', 0)
        date_str = h.get('date', '')
        if score > 0 and date_str:
            records.append({'date': date_str, 'score': score})

    from datetime import datetime as dt, timedelta
    cutoff = (dt.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    records = [r for r in records if r['date'] >= cutoff]
    records.sort(key=lambda x: x['date'])

    labels = [r['date'][5:] for r in records]
    actual = [r['score'] for r in records]

    prediction = predict_tonight(profile)

    predicted_points = []
    if prediction and records:
        last_date = records[-1]['date']
        pred_score = prediction.get('predicted_score', 0)
        predicted_points.append({'date': last_date, 'actual': actual[-1] if actual else 0, 'predicted': None})
        d1 = (dt.strptime(last_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')[5:]
        d2 = (dt.strptime(last_date, '%Y-%m-%d') + timedelta(days=2)).strftime('%Y-%m-%d')[5:]
        predicted_points.append({'date': d1, 'actual': None, 'predicted': pred_score})
        predicted_points.append({'date': d2, 'actual': None, 'predicted': pred_score})

    trend_text = 'stable'
    direction = prediction.get('direction', 'stable') if prediction else 'stable'
    if direction == 'better':
        trend_text = 'improving'
    elif direction == 'worse':
        trend_text = 'declining'

    return {
        'labels': labels,
        'actual': actual,
        'predicted_points': predicted_points,
        'trend': trend_text,
        'prediction': prediction,
        'has_data': len(records) >= 1,
    }
