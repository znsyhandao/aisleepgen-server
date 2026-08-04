# -*- coding: utf-8 -*-
"""
体验引擎 v1 - AI对话中自动嗅探用户情绪，推送疗愈动作

功能:
  1. 在AI回复中自动附加"动作卡片"(冥想/呼吸/认知训练等)
  2. 情绪嗅探: 根据用户关键词判断当前情绪状态
  3. 动作推荐: 匹配最合适的疗愈方式
  4. 一键启动: 前端收到action字段即可展示按钮

集成点: deepseek_proxy.py -> _handle_chat 在 response_obj 中注入 action_suggestions

突变动力学安全:
  1. 只读分析用户消息
  2. 只往 response_obj 加字段，不修改任何数据
  3. 推荐失败不影响主回复
"""

import os, json, random, re
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))

# 疗愈动作库
HEALING_ACTIONS = {
    '478_breathing': {
        'name': '4-7-8 呼吸法',
        'category': 'breathing',
        'symbol': '[B]',
        'description': '吸气4秒 屏住7秒 呼气8秒，快速放松神经系统',
        'params': {'inhale': 4, 'hold': 7, 'exhale': 8, 'rounds': 4},
        'api': '/api/start-breathing',
        'match_keywords': ['焦虑', '紧张', '心慌', '睡不着', '压力大', '烦躁'],
        'difficulty': 'easy',
    },
    'box_breathing': {
        'name': '盒子呼吸法',
        'category': 'breathing',
        'symbol': '[B]',
        'description': '吸气4秒 屏住4秒 呼气4秒 屏住4秒，军队专用减压法',
        'params': {'inhale': 4, 'hold': 4, 'exhale': 4, 'rounds': 5},
        'api': '/api/start-breathing',
        'match_keywords': ['专注', '集中', '焦虑', '紧张', '心烦'],
        'difficulty': 'easy',
    },
    'body_scan': {
        'name': '身体扫描冥想',
        'category': 'meditation',
        'symbol': '[M]',
        'description': '从头到脚逐一放松，适合睡前焦虑',
        'params': {'duration': 10, 'guide': 'body_scan'},
        'api': '/api/start-meditation',
        'match_keywords': ['失眠', '焦虑', '身体僵硬', '放松', '睡不着', '压力'],
        'difficulty': 'medium',
    },
    'mindful_breathing': {
        'name': '正念呼吸',
        'category': 'meditation',
        'symbol': '[M]',
        'description': '专注于一呼一吸，让杂念自然消散',
        'params': {'duration': 5, 'guide': 'mindful'},
        'api': '/api/start-meditation',
        'match_keywords': ['杂念', '想太多', '睡不着', '焦虑', '清醒'],
        'difficulty': 'easy',
    },
    'progressive_relaxation': {
        'name': '渐进式肌肉放松',
        'category': 'relaxation',
        'symbol': '[R]',
        'description': '逐部位紧绷到放松，释放全身紧张',
        'params': {'duration': 15, 'guide': 'progressive'},
        'api': '/api/start-relaxation',
        'match_keywords': ['身体累', '肌肉', '酸痛', '紧张', '僵硬', '放松'],
        'difficulty': 'medium',
    },
    'white_noise': {
        'name': '白噪音助眠',
        'category': 'audio',
        'symbol': '[S]',
        'description': '轻柔白噪音遮盖环境噪音，更快入睡',
        'params': {'type': 'white_noise', 'duration': 60},
        'api': '/api/play-audio',
        'match_keywords': ['噪音', '吵', '睡不着', '环境', '安静'],
        'difficulty': 'easy',
    },
    'rain_sounds': {
        'name': '雨声入眠',
        'category': 'audio',
        'symbol': '[S]',
        'description': '舒缓雨声，营造安心睡眠环境',
        'params': {'type': 'rain', 'duration': 60},
        'api': '/api/play-audio',
        'match_keywords': ['放松', '安静', '自然', '入睡', '安稳'],
        'difficulty': 'easy',
    },
    'sleep_stories': {
        'name': '睡眠故事',
        'category': 'story',
        'symbol': '[T]',
        'description': '轻柔的睡前故事，引导注意力转移',
        'params': {'duration': 20, 'style': 'calm'},
        'api': '/api/play-story',
        'match_keywords': ['睡不着', '无聊', '孤单', '焦虑', '想太多'],
        'difficulty': 'easy',
    },
    'cognitive_reframe': {
        'name': '认知重构练习',
        'category': 'cognitive',
        'symbol': '[C]',
        'description': '识别并重构负面思维模式，缓解睡前焦虑',
        'params': {'duration': 8, 'guide': 'cognitive_reframe'},
        'api': '/api/start-cognitive',
        'match_keywords': ['自责', '后悔', '担心', '明天', '工作', '考试', '害怕'],
        'difficulty': 'hard',
    },
    'mood_tracking': {
        'name': '情绪记录',
        'category': 'tracking',
        'symbol': '[T]',
        'description': '简单记录当前情绪，长期追踪睡眠与情绪关联',
        'params': {},
        'api': '/api/mood-log',
        'match_keywords': ['情绪', '心情', '烦', '不开心', '低落', '难过'],
        'difficulty': 'easy',
    },
}

# 情绪模式
EMOTION_PATTERNS = {
    'anxious': {
        'keywords': ['焦虑', '紧张', '心慌', '担心', '害怕', '不安', '恐慌', '惊恐'],
        'priority': 'high',
        'recommended': ['478_breathing', 'body_scan', 'mindful_breathing'],
    },
    'stressed': {
        'keywords': ['压力', '烦躁', '疲惫', '累', '忙', '崩溃', '撑不住'],
        'priority': 'high',
        'recommended': ['progressive_relaxation', '478_breathing', 'rain_sounds'],
    },
    'insomnia': {
        'keywords': ['失眠', '睡不着', '早醒', '多梦', '浅睡', '醒来', '难以入睡'],
        'priority': 'high',
        'recommended': ['mindful_breathing', 'sleep_stories', 'body_scan', 'white_noise'],
    },
    'overthinking': {
        'keywords': ['想太多', '杂念', '胡思乱想', '停不下来', '清醒', '脑子'],
        'priority': 'medium',
        'recommended': ['mindful_breathing', 'cognitive_reframe', 'body_scan'],
    },
    'sad': {
        'keywords': ['难过', '低落', '抑郁', '孤单', '哭', '不开心', '没意思'],
        'priority': 'medium',
        'recommended': ['mood_tracking', 'sleep_stories', 'rain_sounds'],
    },
}


def sniff_emotion(user_message):
    """嗅探用户情绪 -> 返回匹配的情绪标签"""
    if not user_message:
        return []
    text_lower = user_message.lower()
    matches = []
    for emotion, pattern in EMOTION_PATTERNS.items():
        score = 0
        matched_kw = []
        for kw in pattern['keywords']:
            if kw in user_message or kw in text_lower:
                score += 1
                matched_kw.append(kw)
        if score > 0:
            confidence = min(score / 3, 1.0)
            matches.append({
                'emotion': emotion,
                'confidence': round(confidence, 2),
                'matched_keywords': matched_kw,
                'recommended_actions': pattern['recommended'],
                'priority': pattern['priority'],
            })
    matches.sort(key=lambda x: -x['confidence'])
    return matches


def recommend_action(user_message, user_profile=None):
    """主入口: 用户消息 -> 情绪嗅探 -> 动作推荐"""
    emotions = sniff_emotion(user_message)
    if not emotions:
        return {'has_recommendation': False}
    best = emotions[0]
    recommended = best['recommended_actions']
    if not recommended:
        return {'has_recommendation': False}
    action_key = recommended[0]
    action = HEALING_ACTIONS.get(action_key)
    if not action:
        return {'has_recommendation': False}
    return {
        'has_recommendation': True,
        'emotion': best['emotion'],
        'confidence': best['confidence'],
        'action': {
            'key': action_key,
            'name': action['name'],
            'symbol': action['symbol'],
            'category': action['category'],
            'description': action['description'],
            'difficulty': action['difficulty'],
            'params': action['params'],
            'api': action['api'],
        },
        'all_emotions': [{'emotion': e['emotion'], 'confidence': e['confidence']} for e in emotions],
    }


if __name__ == '__main__':
    print('体验引擎 -- 疗愈动作库')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print()
    for cat in ['breathing', 'meditation', 'relaxation', 'audio', 'story', 'cognitive', 'tracking']:
        items = {k: v for k, v in HEALING_ACTIONS.items() if v['category'] == cat}
        if items:
            cat_name = {'breathing':'呼吸法','meditation':'冥想','relaxation':'放松','audio':'声音','story':'故事','cognitive':'认知训练','tracking':'记录'}.get(cat, cat)
            print(f'  [{cat_name}]')
            for key, act in items.items():
                print(f'    {act["symbol"]} {act["name"]:20s} ({act["difficulty"]}) {act["description"][:30]}')
    print()
    print('情绪嗅探测试:')
    for msg in ['压力大睡不着觉', '总想太多停不下来', '心情不太好低落', '今晚又失眠了']:
        rec = recommend_action(msg)
        if rec['has_recommendation']:
            sym = rec['action']['symbol']
            name = rec['action']['name']
            emotion = rec['emotion']
            conf = rec['confidence']
            print(f'  U: {msg}')
            print(f'    -> emotion={emotion} conf={conf:.0%} recommend={sym} {name}')
        else:
            print(f'  U: {msg}')
            print(f'    -> (no match)')
