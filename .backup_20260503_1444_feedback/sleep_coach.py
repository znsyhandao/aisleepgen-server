#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sleep_coach.py — 睡眠改善计划引擎

核心：把AI分析结果转化为可执行的改善计划，形成建议→执行→反馈→优化闭环。
不依赖世界模型，纯增量模块。

策略:
  1. 每天生成1条改善建议（根据评分+趋势+情绪）
  2. 建议含可执行动作（非"好好睡觉"这种空洞话）
  3. 跟踪建议执行情况（今天提的建议→明天看效果）
  4. 自适应：有效策略强化，无效策略淘汰
"""

import json
import os
import time
import random
import logging
from datetime import datetime, timedelta

_log = logging.getLogger('aisleepgen.coach')
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ===== 建议类型库 =====
SUGGESTIONS = {
    'routine': {
        'name': '固定作息',
        'action': '今晚{target_time}前放下手机，关灯准备入睡',
        'condition': 'moderate',  # moderate: 评分40-70时用
        'category': 'habit',
        'weight': 1.0,
        'effect_tracking': True,
    },
    'wind_down': {
        'name': '睡前放松',
        'action': '睡前30分钟做5分钟深呼吸或身体扫描',
        'condition': 'stress',  # stress: 检测到焦虑情绪时用
        'category': 'relaxation',
        'weight': 1.0,
        'effect_tracking': True,
    },
    'no_screen': {
        'name': '减少蓝光',
        'action': '今晚睡前1小时不看手机屏幕，切换到阅读模式',
        'condition': 'latency',  # latency: 入睡困难时用
        'category': 'habit',
        'weight': 1.0,
        'effect_tracking': True,
    },
    'walk': {
        'name': '白天活动',
        'action': '明天白天做20分钟户外步行，帮助今晚入睡',
        'condition': 'low_quality',  # low_quality: 睡眠质量差时用
        'category': 'exercise',
        'weight': 1.0,
        'effect_tracking': True,
    },
    'earlier': {
        'name': '提前上床',
        'action': '今晚比平时早{early_minutes}分钟上床，试验一下效果',
        'condition': 'deprivation',  # deprivation: 睡眠不足时用
        'category': 'habit',
        'weight': 1.0,
        'effect_tracking': True,
    },
    'journal': {
        'name': '焦虑日记',
        'action': '睡前把脑子里想的事情写下来，释放大脑负担',
        'condition': 'anxiety',
        'category': 'mental',
        'weight': 1.0,
        'effect_tracking': True,
    },
    'hydrate': {
        'name': '调整饮水',
        'action': '今晚6点后不喝水或少喝水，减少起夜',
        'condition': 'interrupted',  # interrupted: 频繁醒来时用
        'category': 'habit',
        'weight': 1.0,
        'effect_tracking': True,
    },
    'temp': {
        'name': '调节室温',
        'action': '今晚把卧室温度调到18-22°C，这是最佳睡眠温度',
        'condition': 'general',
        'category': 'environment',
        'weight': 0.8,
        'effect_tracking': True,
    },
    'stretch': {
        'name': '睡前拉伸',
        'action': '做5分钟简单拉伸（肩颈放松），帮助身体进入休息状态',
        'condition': 'general',
        'category': 'exercise',
        'weight': 0.8,
        'effect_tracking': True,
    },
    'breath': {
        'name': '4-7-8呼吸',
        'action': '用4-7-8呼吸法入睡（吸气4秒→屏息7秒→呼气8秒），重复5轮',
        'condition': 'anxiety_latency',
        'category': 'relaxation',
        'weight': 1.0,
        'effect_tracking': True,
    },
}

CONDITION_MAP = {
    'moderate': ('score', 40, 70),
    'stress': ('emotion', '焦虑'),
    'latency': ('latency', 30, 999),
    'deprivation': ('duration', 0, 360),
    'low_quality': ('quality', 'poor', 'fair'),
    'anxiety': ('emotion', '焦虑'),
    'interrupted': ('awakenings', 2, 999),
}


def _get_user_history(profile, days=7):
    """获取用户近N天的睡眠记录"""
    history = profile.get('history', [])
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    return [h for h in history if isinstance(h, dict) and h.get('date', '') >= cutoff]


def _get_avg_score(history):
    """近几天平均评分"""
    scores = [h.get('wm_score', 0) for h in history if h.get('wm_score', 0) > 0]
    return sum(scores) / len(scores) if scores else 0


def _get_trend(profile):
    """判断评分趋势"""
    history = _get_user_history(profile, days=5)
    if len(history) < 2:
        return 'stable'
    scores = [h.get('wm_score', 0) for h in history if h.get('wm_score', 0) > 0]
    if len(scores) < 2:
        return 'stable'
    # 比较最近3天 vs 之前
    recent = scores[-3:] if len(scores) >= 3 else scores
    older = scores[:-3] if len(scores) > 3 else scores[:1]
    avg_recent = sum(recent) / len(recent)
    avg_older = sum(older) / len(older) if older else avg_recent
    diff = avg_recent - avg_older
    if diff > 8:
        return 'improving'
    elif diff < -8:
        return 'declining'
    return 'stable'


def _get_preferred_category(profile):
    """获取用户偏好的建议类型"""
    coach = profile.get('sleep_coach', {})
    if not coach:
        return None
    # 找到效果最好的
    effects = coach.get('effectiveness', {})
    if not effects:
        return None
    sorted_eff = sorted(effects.items(), key=lambda x: x[1], reverse=True)
    if sorted_eff and sorted_eff[0][1] > 70:
        return sorted_eff[0][0]
    return None


def _evaluate_suggestion_result(suggestion_key, yesterday_score, today_score, profile):
    """评估一条建议的效果

    Returns:
        int: 0-100 的效果评分
    """
    if yesterday_score <= 0 or today_score <= 0:
        return 50  # 无数据时默认中性
    change = today_score - yesterday_score
    # 评分上升 → 效果好
    if change > 10:
        return 85
    elif change > 5:
        return 70
    elif change > 0:
        return 60
    elif change > -5:
        return 45
    else:
        return 25


def _select_suggestion(profile, history, avg_score, trend, emotion_state):
    """选择最合适的改善建议"""
    coach = profile.get('sleep_coach', {})
    effectiveness = coach.get('effectiveness', {})
    last_suggestion = coach.get('last_suggestion')
    given_today = coach.get('given_today', False)

    # 今天已经给过建议了
    if given_today:
        return None, None

    # 排除最近3天给过的建议（不重复）
    recent_keys = set()
    for record in coach.get('history', [])[-3:]:
        if isinstance(record, dict):
            recent_keys.add(record.get('suggestion'))

    # 根据条件筛选候选
    candidates = []
    for key, sug in SUGGESTIONS.items():
        if key in recent_keys:
            continue
        if key == last_suggestion:
            continue
        cond = sug['condition']

        if cond == 'general':
            candidates.append((key, sug, 60 + effectiveness.get(key, 50) * 0.2))
        elif cond == 'moderate' and 40 <= avg_score <= 70:
            candidates.append((key, sug, 70 + effectiveness.get(key, 50) * 0.2))
        elif cond == 'stress' and emotion_state in ('焦虑', '紧张'):
            candidates.append((key, sug, 85 + effectiveness.get(key, 50) * 0.2))
        elif cond == 'latency' and any(h.get('total_duration', 0) > 1800 for h in history[-3:]):
            candidates.append((key, sug, 80 + effectiveness.get(key, 50) * 0.2))
        elif cond == 'deprivation' and avg_score < 40:
            candidates.append((key, sug, 90 + effectiveness.get(key, 50) * 0.2))
        elif cond == 'low_quality' and avg_score < 50:
            candidates.append((key, sug, 80 + effectiveness.get(key, 50) * 0.2))
        elif cond == 'anxiety' and emotion_state == '焦虑':
            candidates.append((key, sug, 90 + effectiveness.get(key, 50) * 0.2))
        elif cond == 'interrupted' and any(h.get('wm_score', 0) < 40 for h in history[-2:]):
            candidates.append((key, sug, 75 + effectiveness.get(key, 50) * 0.2))
        elif cond == 'anxiety_latency' and (emotion_state == '焦虑' or avg_score < 45):
            candidates.append((key, sug, 85 + effectiveness.get(key, 50) * 0.2))

    if not candidates:
        # 保底：选通用建议
        for key, sug in SUGGESTIONS.items():
            if sug['condition'] == 'general' and key not in recent_keys:
                candidates.append((key, sug, 50))

    if not candidates:
        return None, None

    # 按得分排序，取最高分（加一点随机扰动避免僵化）
    candidates.sort(key=lambda x: x[2] + random.uniform(-5, 5), reverse=True)
    best = candidates[0]
    return best[0], best[1]


def _format_suggestion_text(key, sug, profile):
    """格式化建议文本（填充动态参数）"""
    text = sug['action']
    # 填充动态参数
    if '{target_time}' in text:
        now = datetime.now()
        bed_time = now.replace(hour=22, minute=30)
        if now.hour >= 20:
            bed_time = now.replace(hour=23, minute=0)
        text = text.replace('{target_time}', bed_time.strftime('%H:%M'))
    if '{early_minutes}' in text:
        avg_duration = profile.get('latest', {}).get('duration', 420)
        early = max(15, min(60, int(avg_duration / 60 * 0.1)))
        text = text.replace('{early_minutes}', str(early))
    return text


def _get_reminder_time(sug):
    """根据建议类型决定推送提醒时间"""
    category = sug.get('category', '')
    if category in ('relaxation', 'mental'):
        # 放松类 → 睡前30分钟推（21:00-21:30）
        return {'hour': 21, 'minute': 0}
    elif category == 'habit':
        # 习惯类 → 傍晚推（20:00-20:30）
        return {'hour': 20, 'minute': 0}
    elif category == 'exercise':
        # 运动类 → 下午推（17:00-18:00）
        return {'hour': 17, 'minute': 0}
    elif category == 'environment':
        # 环境类 → 傍晚推（19:00-19:30）
        return {'hour': 19, 'minute': 0}
    return {'hour': 20, 'minute': 0}


# ===== 对外接口 =====

def get_daily_suggestion(profile, emotion_state='neutral'):
    """获取今日改善建议

    每次 chat 或 analyze 后调用，检查是否需要给建议。

    Args:
        profile: 用户画像
        emotion_state: 当前情绪状态

    Returns:
        dict or None: {suggestion_key, title, action, reminder_time, effect_tracking}
    """
    coach = profile.get('sleep_coach', {})
    given_date = coach.get('given_date', '')
    today = datetime.now().strftime('%Y-%m-%d')

    # 同一天同一个建议只给一次
    if given_date == today:
        return None

    history = _get_user_history(profile)
    avg_score = _get_avg_score(history)
    trend = _get_trend(profile)

    key, sug = _select_suggestion(profile, history, avg_score, trend, emotion_state)
    if not key or not sug:
        return None

    action_text = _format_suggestion_text(key, sug, profile)
    reminder = _get_reminder_time(sug)

    return {
        'suggestion_key': key,
        'title': sug['name'],
        'action': action_text,
        'reminder_time': reminder,
        'category': sug['category'],
        'effect_tracking': sug.get('effect_tracking', True),
        'generated_at': today,
    }


def apply_suggestion(profile, suggestion):
    """把建议写入用户画像"""
    if not suggestion:
        return profile

    coach = profile.setdefault('sleep_coach', {})
    today = datetime.now().strftime('%Y-%m-%d')

    coach['last_suggestion'] = suggestion['suggestion_key']
    coach['last_title'] = suggestion['title']
    coach['last_action'] = suggestion['action']
    coach['given_date'] = today
    coach['given_today'] = True
    coach['reminder_hour'] = suggestion['reminder_time']['hour']
    coach['reminder_minute'] = suggestion['reminder_time']['minute']

    # 记录历史
    coach.setdefault('history', [])
    coach['history'].append({
        'date': today,
        'suggestion': suggestion['suggestion_key'],
        'title': suggestion['title'],
        'action': suggestion['action'],
        'timestamp': datetime.now().isoformat(),
        'completed': False,
    })
    # 保留最近50条
    if len(coach['history']) > 50:
        coach['history'] = coach['history'][-50:]

    return profile


def evaluate_yesterday_suggestion(profile, today_score):
    """评估昨天建议的效果（今天出评分后调用）"""
    coach = profile.get('sleep_coach', {})
    if not coach:
        return profile, None

    history = coach.get('history', [])
    if not history:
        return profile, None

    yesterday = history[-1]
    if yesterday.get('evaluated', False):
        return profile, None

    yesterday_score = yesterday.get('score_before', 0)
    yesterday_key = yesterday.get('suggestion')
    if not yesterday_key:
        return profile, None

    # 评估效果
    effect_score = _evaluate_suggestion_result(
        yesterday_key, yesterday_score, today_score, profile
    )

    # 记录效果到 effectiveness
    effectiveness = coach.setdefault('effectiveness', {})
    old = effectiveness.get(yesterday_key, 50)
    # 加权移动平均
    new_eff = old * 0.6 + effect_score * 0.4
    effectiveness[yesterday_key] = round(new_eff, 1)

    # 标记已评估
    yesterday['evaluated'] = True
    yesterday['effect_score'] = effect_score
    yesterday['score_before'] = yesterday_score
    yesterday['score_after'] = today_score

    # 重置 daily flag，允许明天生成新建议
    coach['given_today'] = False

    return profile, {
        'suggestion': yesterday_key,
        'effect_score': effect_score,
        'score_change': today_score - yesterday_score,
        'category': SUGGESTIONS.get(yesterday_key, {}).get('category', ''),
    }


def get_coach_summary(profile):
    """获取教练状态摘要"""
    coach = profile.get('sleep_coach', {})
    history = coach.get('history', [])
    effectiveness = coach.get('effectiveness', {})

    # 找出最有效的策略
    best_strategies = sorted(
        effectiveness.items(), key=lambda x: x[1], reverse=True
    )[:3]

    # 本周完成率
    this_week = [
        h for h in history
        if h.get('date', '') >= (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    ]
    completed = sum(1 for h in this_week if h.get('completed', False))
    completion_rate = round(completed / len(this_week) * 100, 1) if this_week else 0

    return {
        'today_suggestion': coach.get('last_title', ''),
        'today_action': coach.get('last_action', ''),
        'best_strategies': best_strategies,
        'total_suggestions': len(history),
        'this_week_suggestions': len(this_week),
        'this_week_completed': completed,
        'completion_rate': completion_rate,
        'given_today': coach.get('given_today', False),
    }


def mark_suggestion_completed(profile, date=None):
    """标记某天的建议已完成"""
    coach = profile.get('sleep_coach', {})
    history = coach.get('history', [])
    target_date = date or datetime.now().strftime('%Y-%m-%d')
    for h in history:
        if h.get('date') == target_date:
            h['completed'] = True
            h['completed_at'] = datetime.now().isoformat()
            break
    return profile


# ===== 决策引擎集成：在 push_decision 中调度提醒 =====

def get_scheduled_reminders(openid, profile):
    """获取需要推送的教练提醒

    由 scheduler_daemon 每次扫描时调用。

    Returns:
        list: 需要推送的提醒列表 [{title, body, push_at}]
    """
    coach = profile.get('sleep_coach', {})
    if not coach.get('given_today', False):
        return []

    now = datetime.now()
    reminders = []

    # 检查定时提醒
    reminder_hour = coach.get('reminder_hour', 20)
    reminder_minute = coach.get('reminder_minute', 0)
    if now.hour == reminder_hour and now.minute == reminder_minute:
        last_action = coach.get('last_action', '')
        last_title = coach.get('last_title', '')
        if last_action:
            reminders.append({
                'title': f'🌙 今晚计划：{last_title}',
                'body': last_action,
                'type': 'coach_reminder',
                'priority': 'normal',
            })

    # 如果今天还没评估昨天的建议 + 有当天评分 → 评估
    # （评估由 analyze 或 chat 触发，调度器不做）

    return reminders


# ===== 自测 =====
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    # 模拟用户画像
    mock_profile = {
        'history': [
            {'date': '2026-05-01', 'wm_score': 55},
            {'date': '2026-05-02', 'wm_score': 48},
        ],
        'sleep_coach': {
            'effectiveness': {'routine': 70, 'wind_down': 65},
            'history': [],
            'given_today': False,
        },
    }

    # Test 1: 获取建议
    sug = get_daily_suggestion(mock_profile, '焦虑')
    print('Test 1 - Daily suggestion:', sug.get('title') if sug else 'None')
    print('  action:', sug.get('action', '') if sug else 'N/A')

    # Test 2: 应用建议
    if sug:
        mock_profile = apply_suggestion(mock_profile, sug)
        print('\nTest 2 - Applied suggestion')
        print('  given_today:', mock_profile['sleep_coach']['given_today'])
        print('  history count:', len(mock_profile['sleep_coach']['history']))

    # Test 3: 评估效果
    mock_profile, result = evaluate_yesterday_suggestion(mock_profile, 65)
    print('\nTest 3 - Evaluation:', result)
    if result:
        print('  effect_score:', result['effect_score'])
        print('  score_change:', result['score_change'])

    # Test 4: 摘要
    summary = get_coach_summary(mock_profile)
    print('\nTest 4 - Coach summary:')
    print('  today:', summary['today_suggestion'])
    print('  completion_rate:', summary['completion_rate'])
    print('  best_strategies:', summary['best_strategies'])

    # Test 5: 定时提醒
    reminders = get_scheduled_reminders('test', mock_profile)
    print('\nTest 5 - Reminders:', len(reminders))

    print('\nOK')
