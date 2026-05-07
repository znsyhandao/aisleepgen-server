#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
trend_layer.py — AISleepGen 结构化睡眠趋势分析

从 history 中提取多维睡眠趋势，以结构化 dict 返回。
不再输出自由文本——由 context_builder 翻译。
"""
import json, logging
from datetime import datetime, timedelta
from collections import defaultdict

_tl_log = logging.getLogger('aisleepgen.trend_layer')


def _extract_trends(openid='default'):
    """提取多维睡眠趋势（结构化的），返回 dict

    输出结构：
    {
        'score_trend': {'direction':'up|down|stable', 'delta':n, 'latest':n, 'earliest':n},
        'duration_trend': {'direction':'up|down|stable', 'avg':n, 'recent_3d_avg':n, 'min':n, 'max':n},
        'bedtime_trend': {'direction':'earlier|later|stable', 'avg_time':'HH:MM', 'variance_minutes':n},
        'sleep_efficiency': {'avg':n, 'trend':'improving|declining|stable'},
        'awake_trend': {'avg_times':n, 'direction':'more|less|stable'},
        'stress_trend': {'avg_level':n, 'direction':'rising|falling|stable'},
        'total_records': n,
        'sleep_deprivation_risk': False,  # 连续3天<6小时
        'circadian_disruption_risk': False,  # 起床时间波动>2小时
    }

    返回空 dict 表示数据不足。
    """
    from profile_storage import _load_user_profile
    profile = _load_user_profile(openid)
    history = profile.get('history', [])
    if not history:
        return {}

    # 按日期排序
    sorted_h = sorted(history, key=lambda x: x.get('date', ''))
    total = len(sorted_h)

    # 1. 分数趋势
    score_records = [(e['date'], e.get('wm_score', 0))
                     for e in sorted_h if e.get('wm_score', 0) > 0]
    score_trend = {}
    if len(score_records) >= 2:
        earliest = score_records[0][1]
        latest = score_records[-1][1]
        delta = latest - earliest
        direction = 'up' if delta > 8 else ('down' if delta < -8 else 'stable')
        score_trend = {
            'direction': direction, 'delta': round(delta, 1),
            'latest': latest, 'earliest': earliest,
        }

    # 2. 睡眠时长趋势
    duration = [e.get('total_duration', 0) for e in sorted_h if e.get('total_duration', 0) > 0]
    duration_trend = {}
    if len(duration) >= 2:
        avg = sum(duration) / len(duration)
        recent_3d = duration[-3:] if len(duration) >= 3 else duration
        avg_recent = sum(recent_3d) / len(recent_3d)
        delta = avg_recent - avg
        duration_trend = {
            'avg': round(avg, 1), 'recent_3d_avg': round(avg_recent, 1),
            'min': min(duration), 'max': max(duration),
            'direction': 'up' if delta > 30 else ('down' if delta < -30 else 'stable'),
        }

    # 3. 生物钟（入睡时间）趋势
    bedtime = []
    for e in sorted_h:
        bt = e.get('bedtime', '') or e.get('got_to_bed', '')
        if bt:
            try:
                parts = bt.split(':')
                mins = int(parts[0]) * 60 + int(parts[1])
                bedtime.append(mins)
            except Exception as e:
                _tl_log.debug('Parse bedtime part failed: %s, value=%s', e, bt)
    bedtime_trend = {}
    if bedtime:
        avg_bed = sum(bedtime) / len(bedtime)
        var = max(bedtime) - min(bedtime)
        # 转回时间
        avg_h = int(avg_bed // 60)
        avg_m = int(avg_bed % 60)
        avg_time = f'{avg_h:02d}:{avg_m:02d}'
        bedtime_trend = {
            'avg_time': avg_time, 'variance_minutes': var,
            'direction': 'earlier' if var < 60 else ('later' if var > 120 else 'stable'),
        }

    # 4. 睡眠效率
    eff = [e.get('sleep_efficiency', 0) for e in sorted_h if e.get('sleep_efficiency', 0) > 0]
    eff_trend = {}
    if len(eff) >= 2:
        avg_eff = sum(eff) / len(eff)
        recent = eff[-3:] if len(eff) >= 3 else eff
        avg_recent = sum(recent) / len(recent)
        eff_trend = {
            'avg': round(avg_eff, 1),
            'trend': 'improving' if avg_recent > avg_eff + 0.03 else (
                'declining' if avg_recent < avg_eff - 0.03 else 'stable'),
        }

    # 5. 夜醒趋势
    awake = [e.get('awake_times', 0) for e in sorted_h if e.get('awake_times', 0) >= 0]
    awake_trend = {}
    if awake:
        avg_awake = sum(awake) / len(awake)
        recent = awake[-3:] if len(awake) >= 3 else awake
        avg_recent = sum(recent) / len(recent)
        awake_trend = {
            'avg_times': round(avg_awake, 1),
            'direction': 'more' if avg_recent > avg_awake + 0.5 else (
                'less' if avg_recent < avg_awake - 0.5 else 'stable'),
        }

    # 6. 压力趋势
    stress = [e.get('stress_level', 0) for e in sorted_h if e.get('stress_level', 0) > 0]
    stress_trend = {}
    if stress:
        avg_stress = sum(stress) / len(stress)
        recent = stress[-3:] if len(stress) >= 3 else stress
        avg_recent = sum(recent) / len(recent)
        stress_trend = {
            'avg_level': round(avg_stress, 1),
            'direction': 'rising' if avg_recent > avg_stress + 1 else (
                'falling' if avg_recent < avg_stress - 1 else 'stable'),
        }

    # 7. 风险检测
    deprivation_risk = len([d for d in duration if d < 360]) >= 3  # 连续3天<6小时
    # 起床时间波动
    wake_times = []
    for e in sorted_h:
        wt = e.get('wake_up', '') or e.get('wake_time', '')
        if wt:
            try:
                parts = wt.split(':')
                mins = int(parts[0]) * 60 + int(parts[1])
                wake_times.append(mins)
            except Exception as e:
                _tl_log.debug('Parse wake time failed: %s, value=%s', e, wt)
    circadian_risk = False
    if len(wake_times) >= 3:
        if max(wake_times) - min(wake_times) > 120:  # 起床波动>2小时
            circadian_risk = True

    return {
        'score_trend': score_trend,
        'duration_trend': duration_trend,
        'bedtime_trend': bedtime_trend,
        'sleep_efficiency': eff_trend,
        'awake_trend': awake_trend,
        'stress_trend': stress_trend,
        'total_records': total,
        'sleep_deprivation_risk': deprivation_risk,
        'circadian_disruption_risk': circadian_risk,
    }


def _build_history_context(openid='default'):
    """构建历史上下文，返回 (context_str, trends_dict)
    context_str 仍为自由文本（供 prompt_builder 兼容）。
    trends_dict 为结构化趋势（供 context_builder 使用）。
    """
    trends = _extract_trends(openid)
    lines = []

    # 评分趋势
    if trends.get('score_trend'):
        st = trends['score_trend']
        dir_label = '上升' if st['direction'] == 'up' else ('下降' if st['direction'] == 'down' else '稳定')
        lines.append(f"评分趋势: {dir_label} {abs(st['delta']):.0f}分 (从{st['earliest']:.0f}到{st['latest']:.0f})")

    # 睡眠时长
    if trends.get('duration_trend'):
        dt = trends['duration_trend']
        dir_label = '增加' if dt['direction'] == 'up' else ('减少' if dt['direction'] == 'down' else '稳定')
        lines.append(f"睡眠时长: 均{dt['avg']:.0f}分钟, 近3日均{dt['recent_3d_avg']:.0f}分钟, 趋势{dir_label}")
        if dt['avg'] < 360:
            lines.append(f"⚠ 警告: 平均睡眠不足6小时({dt['avg']:.0f}分钟)")

    # 生物钟
    if trends.get('bedtime_trend'):
        bt = trends['bedtime_trend']
        lines.append(f"入睡时间: 均值{bt['avg_time']}, 波动{bt['variance_minutes']}分钟")
        if trends.get('circadian_disruption_risk'):
            lines.append(f"⚠ 昼夜节律紊乱风险: 起床时间波动超过2小时")

    # 夜醒
    if trends.get('awake_trend'):
        at = trends['awake_trend']
        if at['direction'] == 'more':
            lines.append(f"⚠ 夜醒增多: 均{at['avg_times']}次/晚")

    if trends.get('sleep_deprivation_risk'):
        lines.append(f"⚠ 连续3天睡眠不足6小时, 建议调整作息")

    ctx = '\n'.join(lines)
    if ctx:
        ctx = f"\n===== 睡眠趋势分析 =====\n{ctx}\n========================\n"

    return ctx, trends
