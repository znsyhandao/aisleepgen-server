#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
circadian_phase_model.py — AISleepGen 昼夜节律相位模型 v1.0

v3.0 延展认知 — Phase 1 核心模块。

从用户的入睡时间 + 起床时间 + 评分数据中，拟合个性化的昼夜节律相位。
不依赖大模型，纯数学拟合，~3ms。

核心输出：
  - acrophase: 节律峰值相位（~16:00 健康人）
  - amplitude: 节律振幅（越强越容易在固定时间犯困）
  - optimal_bedtime_window: 最佳就寝窗口（到达时间范围）
  - drift_rate: 相位漂移率（每天推迟/提前分钟数）
  - predicted_drowsiness(hour): 某时刻的犯困概率 0~1

使用场景：
  1. 稳态回路每3分钟扫描时：更新相位模型，写入 circadian_phase 信号
  2. 预测引擎 predict_tonight()：加入节律相位作为输入特征
  3. 陪伴模式：在犯困窗口前30分钟推送放松建议
"""

import json, os, math, time, logging
from datetime import datetime, timedelta
from collections import defaultdict

_cp_log = logging.getLogger('aisleepgen.circadian')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ==================== 核心数据结构 ====================

class CircadianProfile:
    """个人的昼夜节律模型参数

    基于 cosine 模型：score(t) = baseline + amplitude * cos(2π(t - acrophase) / 24)

    参数：
      baseline:       基础水平（~50分的个人基线）
      amplitude:      节律振幅（~15分，越大节律越强）
      acrophase:      峰值相位（小时，~16.0=下午4点健康人）
      optimal_window: 最佳就寝时间窗口 (start_hour, end_hour)
      drift_rate:     相位漂移率（分钟/天，正则夜猫子为正）
      confidence:     模型置信度 0~1（基于数据量）
      sample_count:   用于拟合的数据点数
    """
    def __init__(self):
        self.baseline = 50.0
        self.amplitude = 10.0
        self.acrophase = 16.0       # 默认下午4点
        self.optimal_window = (22.0, 23.5)  # 默认10pm-11:30pm
        self.drift_rate = 0.0       # 分钟/天
        self.confidence = 0.0
        self.sample_count = 0
        self.last_updated = None

    def to_dict(self):
        return {
            'baseline': round(self.baseline, 1),
            'amplitude': round(self.amplitude, 1),
            'acrophase': round(self.acrophase, 1),
            'optimal_window': (round(self.optimal_window[0], 1), round(self.optimal_window[1], 1)),
            'drift_rate': round(self.drift_rate, 1),
            'confidence': round(self.confidence, 2),
            'sample_count': self.sample_count,
        }

    def drowsiness_at(self, hour):
        """计算某时刻的犯困概率 (0~1)

        基于cosine模型：drowsiness = (1 - cos(2π(t-acrophase)/24)) / 2
        t=acrophase时最清醒(cos=1, drowsiness=0)
        t=acrophase+12时最困(cos=-1, drowsiness=1)
        """
        if self.confidence < 0.1:
            return 0.5  # 置信度太低，返回中性

        # 归一化时间到[0, 24)
        t = hour % 24
        phase = self.acrophase

        # cosine距离用角度差
        angle_diff = (t - phase) * 2 * math.pi / 24
        drowsiness = (1.0 - math.cos(angle_diff)) / 2.0

        # 振幅放大效应：振幅越大，困vs醒的区分越鲜明
        amplitude_factor = min(1.0, self.amplitude / 15.0)
        drowsiness = 0.5 + (drowsiness - 0.5) * (0.5 + amplitude_factor * 0.5)

        # 晚睡型的人：整体犯困曲线后移
        if self.acrophase > 17:
            delay = (self.acrophase - 17) / 7  # 归一化到~0.43
            # 傍晚到深夜增加一个犯困延迟（不显著影响清晨）
            if 18 <= t <= 24:
                drowsiness *= (1.0 - delay * 0.25)

        return max(0.0, min(1.0, drowsiness))

    def is_in_bedtime_window(self, hour):
        """检查当前时间是否在最佳就寝窗口内"""
        start, end = self.optimal_window
        if start <= end:
            return start <= hour <= end
        else:  # 跨天（比如 22:00 ~ 01:00）
            return hour >= start or hour <= end


# ==================== 模型拟合 ====================

def _hours_from_time(time_str):
    """将 HH:MM 格式转换为小时数 (float)"""
    if not time_str:
        return None
    try:
        parts = time_str.split(':')
        h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        result = h + m / 60.0
        # 凌晨时间（0~6点）统一加24小时视为"前一天深夜"
        if result < 6:
            result += 24
        return result
    except (ValueError, IndexError):
        return None


def _fit_cosine_model(bedtimes, scores=None):
    """从入睡时间数据拟合余弦节律模型

    Args:
        bedtimes: list of float (入睡时间的小时数，凌晨已+24)
        scores: list of float or None (对应的睡眠评分)

    Returns:
        CircadianProfile 或 None (数据不足)
    """
    if not bedtimes or len(bedtimes) < 2:
        return None

    n = len(bedtimes)

    profile = CircadianProfile()
    profile.sample_count = n

    # 1. 计算平均入睡时间
    # 健康人的acrophase(峰值=最清醒) 在起床后~6小时
    # 通常起床 = 入睡 + 7-8小时，所以 acrophase ≈ 入睡 + 13~14小时
    # 例：23:00入睡 → 06:00起床 → 12:00~14:00最清醒
    raw_bedtimes = [bt % 24 for bt in bedtimes]
    avg_bedtime = sum(raw_bedtimes) / n

    # 处理环面均值（23:00 和 01:00 均值为 00:00 而不是 12:00）
    sin_sum = sum(math.sin(b * 2 * math.pi / 24) for b in raw_bedtimes)
    cos_sum = sum(math.cos(b * 2 * math.pi / 24) for b in raw_bedtimes)
    mean_angle = math.atan2(sin_sum, cos_sum)
    if mean_angle < 0:
        mean_angle += 2 * math.pi
    circular_mean = mean_angle * 24 / (2 * math.pi)

    # acrophase（最清醒时刻）= 入睡时间 + 14h（假设7h睡眠+6h清醒后达峰）
    profile.acrophase = (circular_mean + 14) % 24

    # 2. 计算振幅（基于评分数据的标准差估计）
    if scores and len(scores) >= 2:
        score_std = math.sqrt(sum((s - sum(scores)/len(scores))**2 for s in scores) / len(scores))
        profile.amplitude = min(25, max(5, score_std))
        profile.baseline = sum(scores) / len(scores)
    else:
        # 无评分数据时，振幅用入睡时间方差估计
        bedtime_var = sum((b - circular_mean)**2 for b in raw_bedtimes) / n
        # 入睡越规律，振幅越大（节律越强）
        regularity = max(0, 1.0 - math.sqrt(bedtime_var) / 4)
        profile.amplitude = 5 + regularity * 15

    # 3. 最佳就寝窗口
    window_start = (circular_mean - 0.5) % 24  # 平均入睡时间前后半小时
    window_end = (circular_mean + 1.0) % 24
    if window_end < window_start:
        window_end += 24
    profile.optimal_window = (window_start, min(24, window_end))

    # 4. 漂移率（最近N天入睡时间的变化趋势）
    if n >= 3:
        # 用原始的bedtimes（凌晨已+24）来算漂移——不会出现环面回绕问题
        recent = bedtimes[-min(n, 7):]
        if len(recent) >= 3:
            # 简单线性回归
            x = list(range(len(recent)))
            y = recent
            n_r = len(x)
            sum_x = sum(x)
            sum_y = sum(y)
            sum_xy = sum(x[i] * y[i] for i in range(n_r))
            sum_xx = sum(x[i]**2 for i in range(n_r))
            denom = n_r * sum_xx - sum_x * sum_x
            if abs(denom) > 1e-10:
                slope = (n_r * sum_xy - sum_x * sum_y) / denom
                profile.drift_rate = slope * 60  # 小时→分钟/天

    # 5. 置信度
    if n >= 7:
        profile.confidence = 0.8
    elif n >= 4:
        profile.confidence = 0.5
    elif n >= 2:
        profile.confidence = 0.3

    profile.last_updated = datetime.now().isoformat()
    return profile


def fit_circadian_profile(profile):
    """从用户数据拟合昼夜节律模型

    v3.0 增强：除了问卷 bedtime 字段，还从对话时间戳中提取入睡线索。

    Args:
        profile: 用户画像 dict

    Returns:
        CircadianProfile 或 None
    """
    history = profile.get('history', [])
    if not history:
        return None

    bedtimes = []
    scores = []

    # ===== 信号源1：问卷中的 bedtime 字段 =====
    for h in history:
        if not isinstance(h, dict):
            continue
        bt = h.get('bedtime', '')
        bt_hours = _hours_from_time(bt)
        if bt_hours is not None:
            bedtimes.append(bt_hours)

        sc = h.get('wm_score', 0) or h.get('score', 0)
        if sc and isinstance(sc, (int, float)) and sc > 0:
            scores.append(sc)

    # ===== 信号源2：从情绪/聊天日志中提取活动时间 =====
    # 如果问卷数据充足（>=3条），就不需要聊天时间推断
    if len(bedtimes) < 3:
        chat_bedtimes = _extract_chat_bedtimes(profile)
        bedtimes.extend(chat_bedtimes)

    if not bedtimes:
        return None

    return _fit_cosine_model(bedtimes, scores if scores else None)


def _extract_chat_bedtimes(profile):
    """从对话+情绪日志推断入睡时间

    原理：
      - 用户深夜最后一次消息 ≈ 入睡前的最后活动
      - 连续多天在特定时间后无消息 → 推断入睡窗口
      - 不依赖问卷，纯时间戳分析

    Returns:
        list[float]: 推断的入睡时间（小时数，凌晨已+24）
    """
    # 从 emotion_log 提取每日最后一次活动时间
    emotion_log = profile.get('emotion_log', [])
    if not emotion_log:
        return []

    # 按日期分组取最后一条
    daily_times = {}
    for entry in emotion_log:
        ts = entry.get('timestamp', 0)
        if not ts:
            # 没有 timestamp 字段，尝试从 time 字符串解析
            time_str = str(entry.get('time', '') or entry.get('ts', '') or '')
            if not time_str:
                continue
            try:
                time_str = time_str.split('.')[0] if '.' in time_str else time_str
                dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                continue
        else:
            try:
                dt = datetime.fromtimestamp(float(ts))
            except (ValueError, TypeError, OSError):
                continue

        day_key = dt.strftime('%Y-%m-%d')
        hour = dt.hour + dt.minute / 60.0
        if day_key not in daily_times or hour > daily_times[day_key]:
            daily_times[day_key] = hour

    # 每天最后一次对话时间如果在22:00之后，视为入睡时间候选
    inferred_bedtimes = []
    for day_key, hour in daily_times.items():
        if hour >= 21:  # 21:00 之后最后一次聊天
            bedtime = hour + 0.5  # 假设聊天结束后半小时入睡
            if bedtime >= 24:
                bedtime += 0  # 已经过了+24
            if bedtime < 6:
                bedtime += 24  # 凌晨统一加24
            inferred_bedtimes.append(bedtime)
        elif hour <= 6:  # 凌晨还在聊
            # 这种情况说明用户很晚睡，加24处理
            inferred_bedtimes.append(hour + 24 + 0.5)

    _cp_log.info('[Circadian] Inferred %d bedtimes from chat logs', len(inferred_bedtimes))
    return inferred_bedtimes


# ==================== 公开 API ====================

def get_drowsiness_forecast(openid):
    """获取某用户的犯困预测（供稳态回路使用）

    Returns:
        dict: {
            'available': bool,
            'current_drowsiness': float,  # 当前时刻 0~1
            'peak_alert_hour': float,     # 最清醒的时刻
            'optimal_bedtime_window': (float, float),
            'drift_rate': float,
            'model_confidence': float,
        }
        或 {'available': False}
    """
    from profile_storage import _load_user_profile
    prof = _load_user_profile(openid)

    cprof = fit_circadian_profile(prof)
    if not cprof:
        return {'available': False}

    now = datetime.now()
    current_hour = now.hour + now.minute / 60.0

    return {
        'available': True,
        'current_drowsiness': cprof.drowsiness_at(current_hour),
        'peak_alert_hour': cprof.acrophase,
        'optimal_bedtime_window': cprof.optimal_window,
        'drift_rate': cprof.drift_rate,
        'model_confidence': cprof.confidence,
        'parameters': cprof.to_dict(),
    }


def get_drowsiness_at(openid, hour):
    """查询用户在指定时刻的犯困概率

    Args:
        openid: 用户ID
        hour: 小时数 (0~24)

    Returns:
        float: 0~1 或 -1 (数据不足)
    """
    from profile_storage import _load_user_profile
    prof = _load_user_profile(openid)
    cprof = fit_circadian_profile(prof)
    if not cprof or cprof.confidence < 0.1:
        return -1
    return cprof.drowsiness_at(hour)


def get_circadian_signal(openid):
    """获取供稳态回路写入的节律信号

    Returns:
        dict: 供 report_body_event 使用的 data
    """
    forecast = get_drowsiness_forecast(openid)
    if not forecast.get('available'):
        return None

    now_drowsy = forecast['current_drowsiness']
    drift = forecast['drift_rate']
    confidence = forecast['model_confidence']

    signals = {
        'phase_available': True,
        'model_confidence': confidence,
    }

    # 犯困程度
    if now_drowsy > 0.7:
        signals['drowsiness'] = 'high'
    elif now_drowsy > 0.4:
        signals['drowsiness'] = 'moderate'
    else:
        signals['drowsiness'] = 'low'

    # 漂移风险评估
    if drift > 15:
        signals['circadian_drift'] = 'severe'
    elif drift > 5:
        signals['circadian_drift'] = 'moderate'
    else:
        signals['circadian_drift'] = 'stable'

    # 窗口距离评估
    now_h = datetime.now().hour + datetime.now().minute / 60.0
    window = forecast['optimal_bedtime_window']
    if window[0] <= now_h <= window[1]:
        signals['in_bedtime_window'] = True
    else:
        # 距离窗口还有多久
        if now_h < window[0]:
            hours_to_window = window[0] - now_h
        elif now_h > window[1]:
            hours_to_window = 24 - now_h + window[0]
        else:
            hours_to_window = 0
        signals['in_bedtime_window'] = False
        signals['hours_to_window'] = round(hours_to_window, 1)

    return signals


# ==================== 自测 ====================
def _self_test():
    """验证基本功能"""
    test_profile = {
        'history': [
            {'date': '2026-04-28', 'bedtime': '23:30', 'wm_score': 65},
            {'date': '2026-04-29', 'bedtime': '23:45', 'wm_score': 58},
            {'date': '2026-04-30', 'bedtime': '00:15', 'wm_score': 45},
            {'date': '2026-05-01', 'bedtime': '23:15', 'wm_score': 62},
            {'date': '2026-05-02', 'bedtime': '00:30', 'wm_score': 42},
            {'date': '2026-05-03', 'bedtime': '23:50', 'wm_score': 55},
            {'date': '2026-05-04', 'bedtime': '01:00', 'wm_score': 38},
        ]
    }

    cprof = fit_circadian_profile(test_profile)
    assert cprof is not None
    print(f'[Test] Acrophase: {cprof.acrophase:.1f}h')
    print(f'[Test] Amplitude: {cprof.amplitude:.1f}')
    print(f'[Test] Baseline: {cprof.baseline:.1f}')
    print(f'[Test] Optimal window: {cprof.optimal_window}')
    print(f'[Test] Drift rate: {cprof.drift_rate:+.1f} min/day')
    print(f'[Test] Confidence: {cprof.confidence}')

    # 犯困概率
    print()
    for h in range(0, 24, 3):
        d = cprof.drowsiness_at(h)
        label = '😴' if d > 0.65 else ('🙂' if d > 0.4 else '🧠')
        print(f'  {h:02d}:00 -> drowsiness={d:.2f}')

    # 深夜vs白天差异
    night_drowsy = cprof.drowsiness_at(23)  # 11pm
    morning_drowsy = cprof.drowsiness_at(8)  # 8am
    print(f'[Test] 23:00 drowsiness: {night_drowsy:.2f}')
    print(f'[Test] 08:00 drowsiness: {morning_drowsy:.2f}')
    assert night_drowsy > morning_drowsy, 'night should be drowsier than morning'

    # 漂移检测
    print(f'\n[Test] Drift: {cprof.drift_rate:+.1f} min/day')
    if cprof.drift_rate > 10:
        print('  → ⚠️ Circadian drift detected (sleep time getting later)')

    # get_circadian_signal
    sig = get_circadian_signal('default')
    # This will use the real profile (may be empty)
    print(f'\n[Test] Circadian signal available: {sig is not None}')

    print('\nAll tests PASS!')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _self_test()
