#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
world_models_v2.py — 世界模型v2 时空演化预测 (v7.5+)
原理: DeepMind MuZero/Dreamer — 用潜变量预测用户的长期睡眠演化轨迹
落地: 从历史学习"睡眠演化模型"，预测未来7天的睡眠趋势

用法:
  from world_models_v2 import predict_evolution, world_models_summary
  forecast = predict_evolution(history, horizon=7)
"""

import math


def _autocorr(values):
    """自相关系数: 昨日→今日评分相关性"""
    n = len(values)
    if n < 4:
        return 0.3
    last = values[-1]
    prev = values[-2]
    # 最近两天变化方向
    if last > prev + 3:
        return 0.6  # 上升趋势惯性
    elif last < prev - 3:
        return -0.3  # 下降趋势可能反弹
    else:
        # 滑动窗口相关性
        x = values[-8:-1] if n >= 9 else values[:-1]
        y = values[-7:] if n >= 8 else values[1:]
        if len(x) < 3:
            return 0.3
        mx = sum(x) / len(x)
        my = sum(y) / len(y)
        num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
        dx = math.sqrt(max(1e-10, sum((xi - mx)**2 for xi in x)))
        dy = math.sqrt(max(1e-10, sum((yi - my)**2 for yi in y)))
        corr = num / (dx * dy)
        return max(-0.5, min(0.8, corr))


def _rbf_kernel(t1, t2, length_scale=3.0):
    """RBF核: 时间距离越近→相关性越高"""
    d = abs(t1 - t2)
    return math.exp(-0.5 * (d / length_scale) ** 2)


def predict_evolution(history, horizon=7, features=None):
    """预测未来睡眠演化轨迹

    用时序自相关+马尔可夫链模拟未来演化。
    不依赖numpy/ML库，纯数学实现。

    Args:
        history: list[dict] — 历史睡眠记录，每个含score
        horizon: int — 预测天数 (默认7)
        features: list[str] — 要预测的维度 (默认['score'])

    Returns:
        dict: {forecast, uncertainty, trend, story, note}
    """
    if not history:
        return {'forecast': [], 'note': '无历史数据'}

    if features is None:
        features = ['score']

    # 提取评分序列
    scores = []
    for h in history:
        if isinstance(h, dict) and 'score' in h:
            s = h.get('score')
            if isinstance(s, (int, float)):
                scores.append(float(s))

    if len(scores) < 2:
        return {'forecast': [], 'note': '数据不足2条'}

    # 计算自相关
    corr = _autocorr(scores)
    recent_mean = sum(scores[-5:]) / min(5, len(scores[-5:]))
    overall_mean = sum(scores) / len(scores)
    last_val = scores[-1]
    std = math.sqrt(max(1e-10, sum((s - overall_mean)**2 for s in scores) / len(scores)))

    # ===== 多步预测 =====
    forecast = []
    current = last_val
    for step in range(1, horizon + 1):
        # 马尔可夫: 返回均值 + 相关性衰减
        alpha = _rbf_kernel(0, step, length_scale=5.0)  # 远程依赖衰减
        beta = _rbf_kernel(0, step, length_scale=2.0) * 0.3  # 随机项

        # 预测 = 自相关趋势 + 均值回归 + 噪声
        trend_effect = corr * (current - recent_mean) * alpha
        mean_reversion = (overall_mean - current) * 0.15 * alpha
        noise = (std * 0.5) * beta * (1 if step % 2 == 0 else -1)

        next_val = current + trend_effect + mean_reversion + noise
        next_val = max(0, min(100, next_val))

        # 不确定性随步长递增
        uncertainty = 5 + step * 3  # 第7天误差±26分

        forecast.append({
            'day': step,
            'predicted_score': round(next_val, 1),
            'uncertainty': round(uncertainty, 1),
            'lower_bound': round(max(0, next_val - uncertainty), 1),
            'upper_bound': round(min(100, next_val + uncertainty), 1),
        })
        current = next_val

    # ===== 趋势判断 =====
    start = forecast[0]['predicted_score']
    end = forecast[-1]['predicted_score']
    diff = end - start

    if diff > 8:
        trend = '改善↑'
        story = '预测评分在持续改善中，建议保持当前干预方案'
    elif diff > 3:
        trend = '温和改善↗'
        story = '预测评分有轻微上升趋势，建议继续维持良好习惯'
    elif diff > -3:
        trend = '稳定→'
        story = '预测评分相对稳定，波动在正常范围内'
    elif diff > -8:
        trend = '温和下降↘'
        story = '预测评分有轻微下降趋势，建议增加放松干预'
    else:
        trend = '明显下降↓'
        story = '预测评分下降趋势明显，建议调整睡眠策略'

    # 长期最终稳定值
    stable_point = (
        overall_mean * 0.6 +
        recent_mean * 0.3 +
        last_val * 0.1
    )

    return {
        'forecast': forecast,
        'horizon': horizon,
        'n_samples': len(scores),
        'autocorr': round(corr, 2),
        'trend': trend,
        'story': story,
        'stable_long_term': round(stable_point, 1),
        'final_prediction': forecast[-1],
        'note': 'ok',
    }


def world_models_summary(result):
    """摘要"""
    if 'forecast' not in result or not result['forecast']:
        return '世界模型: %s' % result.get('note', 'N/A')
    return '世界模型: %s, %d天预测, %s' % (
        result['trend'],
        result['horizon'],
        result['story'][:30],
    )


# ===== 自测 =====
if __name__ == '__main__':
    print('=== World Models v2 Test ===\n')

    # 缓慢上升趋势
    history_rise = [{'score': 50 + i * 1.5} for i in range(14)]
    r1 = predict_evolution(history_rise, horizon=7)
    print('Rising:', world_models_summary(r1))
    assert '改善' in r1['trend']
    assert len(r1['forecast']) == 7

    # 下降趋势
    history_fall = [{'score': 70 - i * 2} for i in range(10)]
    r2 = predict_evolution(history_fall, horizon=5)
    print('Falling:', world_models_summary(r2))
    assert '下降' in r2['trend']

    # 数据不足
    r3 = predict_evolution([{'score': 60}], horizon=3)
    assert r3['note'] == '数据不足2条'

    # 无数据
    r4 = predict_evolution([])
    assert '无历史数据' in r4['note']

    # 稳定序列
    history_stable = [{'score': 65 + (i % 3 - 1) * 2} for i in range(14)]
    r5 = predict_evolution(history_stable, horizon=7)
    print('Stable:', world_models_summary(r5))
    assert '稳定' in r5['trend']

    # 边界检查: 评分不超出0-100
    for d in r5['forecast']:
        assert 0 <= d['predicted_score'] <= 100

    print('\nAll tests passed!')
