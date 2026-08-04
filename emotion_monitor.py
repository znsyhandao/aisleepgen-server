#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emotion_monitor.py — AISleepGen 情绪感知与追踪模块

职责:
  1. 从用户聊天消息中提取情绪标签（轻量关键词+规则，不依赖模型）
  2. 记录情绪变化到 profile (emotion_log)
  3. 检测负面情绪积累趋势
  4. 触发推送源数据生成（供 scheduler + wechat_push 使用）

依赖:
  - 只读 profile dict，通过外部传入
  - 不依赖 deepseek/world model
"""

import time
import json
import logging
from datetime import datetime, timedelta
from collections import Counter

# 具身上下文集成
try:
    from body_context import report_body_event as _report_body_ev
    _HAS_BODY_CTX = True
except ImportError:
    _HAS_BODY_CTX = False

_log = logging.getLogger('aisleepgen.emotion')

# ===== 情绪关键词词典 =====
# 分级：-2(严重负面) -1(轻微负面) 0(中性) +1(轻微正面) +2(正面)

EMOTION_KEYWORDS = {
    # 严重负面 (-2)
    'severe_negative': {
        'keywords': [
            '崩溃', '绝望', '活不下去', '想死', '受不了', '撑不住',
            '抑郁发作', 'panic', 'panic attack', '无法呼吸',
            '暴怒', '控制不住', '摔东西', '砸',
        ],
        'label': '崩溃',
        'score': -2,
    },
    # 焦虑/压力 (-1.5)
    'anxiety': {
        'keywords': [
            '焦虑', '紧张', '压力大', '喘不过气', '心慌', '心跳加速',
            '失眠', '睡不着', '整夜没睡', '凌晨醒来', '早醒',
            '担心', '害怕', '恐惧', '不安', '烦', '烦躁',
            '考试', '面试', 'deadline', 'DDL', '加班', '工作压力',
            '房贷', '车贷', '经济', '裁员', '失业',
            'anxious', 'stress', 'worried', 'nervous',
        ],
        'label': '焦虑',
        'score': -1.5,
    },
    # 疲惫/低能量 (-1)
    'fatigue': {
        'keywords': [
            '累', '累死', '累死了', '疲惫', '没精神', '困', '疲倦', '乏力', '不想动',
            '嗜睡', '睡不醒', '没力气', '虚', '疲劳', '太累了', '好累',
            'tired', 'exhausted', 'fatigue', 'sleepy',
        ],
        'label': '疲惫',
        'score': -1,
    },
    # 悲伤/低落 (-1)
    'sadness': {
        'keywords': [
            '难过', '伤心', '哭', '流泪', '失落', '孤独', '寂寞',
            '没意思', '没意义', '无聊', '空虚', '沮丧',
            'sad', 'lonely', 'depressed', 'down',
        ],
        'label': '低落',
        'score': -1,
    },
    # 平静/中性 (0)
    'calm': {
        'keywords': [
            '还行', '一般', '正常', '平静', '放松', '休息', '刚醒',
            'fine', 'ok', 'okay', 'normal', 'calm',
        ],
        'label': '平静',
        'score': 0,
    },
    # 开心/满足 (+1)
    'happy': {
        'keywords': [
            '开心', '高兴', '愉快', '舒服', '不错', '很好', '满意',
            '幸福', '感恩', '美好', '放松了', '睡得好',
            'happy', 'good', 'great', 'wonderful', 'enjoy',
        ],
        'label': '开心',
        'score': 1,
    },
    # 兴奋/精力充沛 (+1.5)
    'energetic': {
        'keywords': [
            '精力充沛', '充满活力', '兴奋', '期待', '充满希望',
            '睡够了', '精神好', 'energy', 'energetic',
        ],
        'label': '充满活力',
        'score': 1.5,
    },
}


def detect_emotion(message):
    """从消息中检测情绪

    Args:
        message: 用户消息字符串

    Returns:
        dict: {
            'emotion': str,       # 情绪标签名
            'score': float,       # 情绪分数 (-2 ~ +2)
            'confidence': float,  # 置信度 0~1
            'matched': [str],     # 匹配到的关键词
        }
        无匹配时返回 {'emotion': 'unknown', 'score': 0, 'confidence': 0, 'matched': []}
    """
    if not message or not isinstance(message, str):
        return {'emotion': 'unknown', 'score': 0, 'confidence': 0, 'matched': []}

    msg_lower = message.lower()
    matches = []  # [(label, score, keyword)]

    for category, config in EMOTION_KEYWORDS.items():
        for kw in config['keywords']:
            if kw in msg_lower:
                matches.append((config['label'], config['score'], kw))

    if not matches:
        return {'emotion': 'unknown', 'score': 0, 'confidence': 0, 'matched': []}

    # 去重合并：按类别聚合分数
    label_scores = {}
    for label, score, kw in matches:
        if label not in label_scores:
            label_scores[label] = {'score': score, 'count': 0, 'keywords': []}
        label_scores[label]['count'] += 1
        label_scores[label]['keywords'].append(kw)

    # 选择计数最多且分数更低（更负面优先）的类别
    best_label = None
    best_priority = (-999, 0)  # (negative_score_priority, count)

    for label, data in label_scores.items():
        avg_score = data['score']
        count = data['count']
        # 越负面优先级越高（分数越低）
        priority = (avg_score, count)
        if best_label is None or priority < best_priority:
            best_priority = priority
            best_label = label

    # 特殊规则：如果同时匹配焦虑(-1.5)和疲惫(-1)，且疲惫词更多 → 选疲惫
    if '焦虑' in label_scores and '疲惫' in label_scores:
        if label_scores['疲惫']['count'] > label_scores['焦虑']['count']:
            best_label = '疲惫'
            best_priority = (-1, label_scores['疲惫']['count'])

    best = label_scores[best_label]
    # 置信度基于匹配词数量/质量
    avg_score = best['score']
    conf_factor = min(1.0, len(best['keywords']) / 3)

    return {
        'emotion': best_label,
        'score': avg_score,
        'confidence': round(conf_factor, 2),
        'matched': list(set(best['keywords']))[:5],
    }


def record_emotion(profile, message):
    """记录用户情绪到 profile

    在 profile 的 emotion_log 列表追加一条记录

    Args:
        profile: 用户画像 dict（会被修改）
        message: 用户消息

    Returns:
        dict: 情绪检测结果，或 None（消息太短）
    """
    if not message or len(message) < 2:
        return None

    result = detect_emotion(message)
    if result['emotion'] == 'unknown':
        return result

    log_entry = {
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'timestamp': time.time(),
        'message_snippet': message[:100],
        'emotion': result['emotion'],
        'score': result['score'],
        'confidence': result['confidence'],
    }

    emotion_log = profile.setdefault('emotion_log', [])
    emotion_log.append(log_entry)

    # 通知具身上下文
    if _HAS_BODY_CTX:
        try:
            _report_body_ev(
                profile.get('openid', 'default'),
                'emotion_detected',
                {'emotion': result['emotion'], 'score': result['score']}
            )
        except Exception:
            pass

    # 最多保留最近 200 条
    if len(emotion_log) > 200:
        profile['emotion_log'] = emotion_log[-200:]

    # 更新情绪摘要
    _update_emotion_summary(profile)

    return result


def _update_emotion_summary(profile):
    """更新情绪摘要（最近7天 + 最近24小时）"""
    now = time.time()
    day_ago = now - 86400
    week_ago = now - 86400 * 7

    log = profile.get('emotion_log', [])

    recent_day = [e for e in log if e.get('timestamp', 0) > day_ago]
    recent_week = [e for e in log if e.get('timestamp', 0) > week_ago]

    def _agg(entries):
        if not entries:
            return None
        scores = [e.get('score', 0) for e in entries]
        emotions = [e.get('emotion', 'unknown') for e in entries]
        avg_score = sum(scores) / len(scores)
        most_common = Counter(emotions).most_common(3)
        neg_count = sum(1 for s in scores if s < 0)
        return {
            'avg_score': round(avg_score, 2),
            'top_emotions': [{'emotion': e, 'count': c} for e, c in most_common],
            'negative_ratio': round(neg_count / len(entries), 2) if entries else 0,
            'total_entries': len(entries),
        }

    summary = profile.setdefault('emotion_summary', {})
    summary['last_24h'] = _agg(recent_day)
    summary['last_7d'] = _agg(recent_week)
    summary['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def get_emotion_trigger(profile):
    """检测是否需要触发情绪推送

    检查最近记录的负面情绪是否达到推送阈值

    Returns:
        dict or None: {
            'trigger_type': str,       # 'accumulated_negativity' | 'sudden_drop' | 'consistent_anxiety'
            'severity': str,           # 'mild' | 'moderate' | 'severe'
            'detail': str,             # 推送用描述文本
        }
    """
    log = profile.get('emotion_log', [])
    summary = profile.get('emotion_summary', {})

    last_24h = summary.get('last_24h')
    last_7d = summary.get('last_7d')

    if not last_24h or last_24h['total_entries'] == 0:
        return None

    triggers = []

    # 1. 24小时内负面情绪比例过高
    if last_24h.get('negative_ratio', 0) >= 0.6 and last_24h['total_entries'] >= 2:
        avg = last_24h['avg_score']
        if avg <= -1.5:
            severity = 'severe'
        elif avg <= -1.0:
            severity = 'moderate'
        else:
            severity = 'mild'

        top_emotions = last_24h.get('top_emotions', [])
        emotion_names = ', '.join([e['emotion'] for e in top_emotions[:2]])

        triggers.append({
            'trigger_type': 'accumulated_negativity',
            'severity': severity,
            'detail': f'最近{last_24h["total_entries"]}次对话中频繁出现负面情绪（{emotion_names}），占比{last_24h["negative_ratio"]*100:.0f}%。',
        })

    # 2. 突发情绪下降（最近一条 vs 之前的平均）
    recent_entries = [e for e in log[-10:] if e.get('score', 0) != 0]
    if len(recent_entries) >= 3:
        last_score = recent_entries[-1]['score']
        prev_avg = sum(e['score'] for e in recent_entries[:-1]) / len(recent_entries[:-1])
        drop = prev_avg - last_score
        if drop >= 2:  # 突然从正面掉到严重负面
            triggers.append({
                'trigger_type': 'sudden_drop',
                'severity': 'severe' if drop >= 2.5 else 'moderate',
                'detail': f'情绪突然下降（{prev_avg:.1f}→{last_score:.1f}），当前情绪：{recent_entries[-1].get("emotion", "未知")}。',
            })

    # 3. 持续的焦虑模式（最近7天焦虑占比高）
    if last_7d and last_7d['total_entries'] >= 5:
        top_emotions = last_7d.get('top_emotions', [])
        anxiety_count = sum(c for e, c in top_emotions if e == '焦虑')
        total = last_7d['total_entries']
        if anxiety_count / total >= 0.4 and total >= 5:
            triggers.append({
                'trigger_type': 'consistent_anxiety',
                'severity': 'moderate',
                'detail': f'过去7天{total}次对话中焦虑出现{anxiety_count}次（占比{anxiety_count/total*100:.0f}%），属于高频焦虑模式。',
            })

    if not triggers:
        return None

    # 返回最严重的触发
    severity_order = {'severe': 3, 'moderate': 2, 'mild': 1}
    triggers.sort(key=lambda t: severity_order.get(t['severity'], 0), reverse=True)
    return triggers[0]


def generate_emotion_push_content(trigger, profile):
    """根据情绪触发生成推送内容

    Args:
        trigger: get_emotion_trigger() 返回的触发信息
        profile: 用户画像

    Returns:
        (title, content, push_type) or None
    """
    from wechat_push import _get_username
    username = _get_username(profile) or '朋友'

    if not trigger:
        return None

    trigger_type = trigger['trigger_type']
    severity = trigger['severity']
    detail = trigger['detail']

    if trigger_type == 'accumulated_negativity':
        if severity == 'severe':
            title = f'💙 {username}，想跟你聊聊'
            content = f'注意到你最近情绪不太好，如果愿意的话，随时可以找我聊聊。{detail[:60]}'
        else:
            title = f'💭 {username}，放松一下？'
            content = f'{detail[:80]}今晚试试做3分钟深呼吸，或者听一段白噪音，让大脑休息一下。'

    elif trigger_type == 'sudden_drop':
        title = f'🤗 {username}，发生什么了？'
        content = f'感觉你心情突然变差了。{detail[:60]}需要的话，这里有一些减压练习可以帮你放松。'

    elif trigger_type == 'consistent_anxiety':
        title = f'🌿 {username}，焦虑有办法缓解'
        content = f'{detail[:80]}长期焦虑会影响睡眠质量，建议睡前做10分钟正念冥想，让过度思考的大脑安静下来。'

    else:
        return None

    return title, content, 'emotion_care'


# ===== 自测 =====
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    test_messages = [
        '今晚又失眠了，好焦虑明天还有会',
        '今天好开心，睡了个好觉',
        '累死了，加班到半夜',
        '最近压力很大，房贷车贷压得喘不过气',
        '还行吧，一般般',
        '活不下去了，真的撑不住了',
    ]

    print('=== Emotion Detection Tests ===')
    for msg in test_messages:
        r = detect_emotion(msg)
        print(f'  [{r["emotion"]:6s} score={r["score"]:+.1f} conf={r["confidence"]:.2f}] {msg}')

    print()
    print('=== Emotion Log Test ===')
    profile = {}
    for msg in test_messages:
        record_emotion(profile, msg)
    print(f'  Log entries: {len(profile.get("emotion_log", []))}')
    print(f'  Summary 24h: {profile.get("emotion_summary", {}).get("last_24h")}')
    print(f'  Trigger: {get_emotion_trigger(profile)}')

    print()
    print('OK')
