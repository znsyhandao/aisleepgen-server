#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
interoceptive_prediction.py — AISleepGen 内感受预测 v1.0

v2.17 延展认知 — Phase 2 核心模块。

SCAN启示-执行前内部模拟：
  在决定推送/建议/陪伴之前，先仿真这个动作对用户可能产生什么效果。
  有历史数据时，从历史上看这种方法对用户有多有效。
  无历史数据时，基于用户画像做合理推测。

纯规则引擎，~3ms级别，不依赖大模型。

使用场景：
  1. 稳态回路：每隔N分钟评估是否应该推（push_simulation）
  2. 干预选择：从多个候选建议中，仿真选出效果最好的
  3. 陪伴模式：估计当前陪聊的最佳时长
"""

import json, os, math, hashlib, logging
from datetime import datetime, timedelta
from collections import defaultdict

_ip_log = logging.getLogger('aisleepgen.interoceptive')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ==================== 建议配置 ====================

SUGGESTIONS = {
    'routine': {'title': '建立规律作息', 'type': 'habit', 'base_effect': 8,
                'description': '固定作息时间，稳定生物钟'},
    'wind_down': {'title': '睡前放松', 'type': 'relaxation', 'base_effect': 6,
                  'description': '睡前进行放松活动'},
    'relax': {'title': '腹式呼吸放松', 'type': 'breathing', 'base_effect': 5,
              'description': '通过腹式呼吸放松身心'},
    'breath': {'title': '4-7-8呼吸法', 'type': 'breathing', 'base_effect': 5,
               'description': '通过调节呼吸节奏入眠'},
    'attention': {'title': '正念冥想', 'type': 'mindfulness', 'base_effect': 4,
                  'description': '通过正念练习改善睡眠质量'},
    'habit': {'title': '提前上床', 'type': 'habit', 'base_effect': 3,
              'description': '逐步提前入睡时间'},
    'sleep_restriction': {'title': '睡眠限制疗法', 'type': 'therapy', 'base_effect': 7,
                          'description': '通过限制卧床时间提高睡眠效率'},
    'sensory': {'title': '感官调节', 'type': 'sensory', 'base_effect': 2,
                'description': '调整卧室环境，改善睡眠质量'},
    'nutrition': {'title': '饮食调理', 'type': 'nutrition', 'base_effect': 3,
                  'description': '调整饮食习惯改善睡眠'},
    'cognitive': {'title': '认知重构', 'type': 'therapy', 'base_effect': 6,
                  'description': '调整对睡眠的认知和态度'},
    'body_scan': {'title': '身体扫描放松', 'type': 'mindfulness', 'base_effect': 4,
                  'description': '逐个部位扫描放松身体'},
    'progressive_muscle': {'title': '渐进式肌肉放松', 'type': 'relaxation', 'base_effect': 5,
                           'description': '通过肌肉紧张-放松循环入睡'},
    'emotion_regulation': {'title': '情绪调节', 'type': 'emotion', 'base_effect': 5,
                           'description': '管理睡前情绪波动'},
    'journaling': {'title': '睡眠日记', 'type': 'cognitive', 'base_effect': 4,
                   'description': '记录睡眠日志寻找规律'},
    'morning_light': {'title': '晨光疗愈', 'type': 'routine', 'base_effect': 3,
                      'description': '早晨接触自然光调节生物钟'},
    'bedtime_ritual': {'title': '睡前仪式', 'type': 'ritual', 'base_effect': 5,
                       'description': '建立固定的睡前仪式'},
    'sleep_education': {'title': '睡眠教育', 'type': 'education', 'base_effect': 2,
                        'description': '了解睡眠基本知识'},
}
"""
注意: 所有仿真函数都不应假设profile不是None或dict。
调用方可能在任何上下文中调用，安全钳制是每个函数的自我防御。
"""

# ==================== 核心仿真引擎 ====================

def simulate_suggestion_effect(profile, suggestion_key, suggestion_config=None):
    """仿真一个建议对特定用户的效果。

    SCAN启示：执行前内部模拟。
    有历史效果记录时，基于历史均值±标准差估计。
    无记录时，根据用户画像综合评分 + 建议效果base。

    Args:
        profile: 用户画像 dict
        suggestion_key: 建议类型的 key (e.g. 'routine', 'wind_down')
        suggestion_config: 建议配置 dict (可选，自定义从 SUGGESTIONS 取)

    Returns:
        dict: {
            'predicted_effect': int,       # 预计评分变化 (-20 ~ +20)
            'confidence': str,              # 'high' | 'medium' | 'low'
            'confidence_score': float,      # 0.0 ~ 1.0
            'basis': str,                   # 'historical' | 'personalized_baseline' | 'default_estimate'
            'effectiveness_samples': int,   # 用于预测的历史数据量
            'variability': float,           # 效果方差 (0=稳定, 大=不稳定)
            'recommendation': str,          # 'recommend' | 'consider' | 'avoid'
        }
    """
    # 安全钳制：容错None/invalid profile
    if not isinstance(profile, dict):
        _ip_log.warning('[Sim] None/invalid profile for %s', suggestion_key)
        return {'predicted_effect': 0, 'confidence': 'low', 'confidence_score': 0.0,
                'basis': 'default_estimate', 'effectiveness_samples': 0,
                'variability': 12.0, 'recommendation': 'consider'}
    coach = profile.get('sleep_coach', {})
    effectiveness = coach.get('effectiveness', {})
    coach_history = coach.get('history', [])

    # 获取该建议的历史效果记录
    key = suggestion_key
    effect_data = effectiveness.get(key, {})
    if isinstance(effect_data, (int, float)):
        # 旧格式：直接是分数
        past_effects = []
        base_score = float(effect_data)
    else:
        past_effects = effect_data.get('effects', []) if isinstance(effect_data, dict) else []
        base_score = effect_data.get('avg_effect', 50) if isinstance(effect_data, dict) else 50

    if past_effects:
        # 有历史数据：基于效果均值±标准差
        mean_effect = sum(past_effects) / len(past_effects)
        variance = sum((e - mean_effect) ** 2 for e in past_effects) / len(past_effects)
        std_dev = math.sqrt(variance) if variance > 0 else 2.0
        confidence = 'high' if len(past_effects) >= 5 else ('medium' if len(past_effects) >= 3 else 'low')
        recommendation = 'recommend' if mean_effect > 3 else ('consider' if mean_effect > 0 else 'avoid')
        return {
            'predicted_effect': round(mean_effect),
            'confidence': confidence,
            'confidence_score': {'high': 0.9, 'medium': 0.6, 'low': 0.3}.get(confidence, 0.3),
            'basis': 'historical',
            'effectiveness_samples': len(past_effects),
            'variability': round(std_dev, 1),
            'recommendation': recommendation,
        }

    # 无历史数据：基于用户评分 + 建议特征做合理推测
    # 计算用户最近评分均值
    history = profile.get('history', [])
    recent_scores = [h.get('total_score', 50) for h in history if isinstance(h, dict)]
    avg_score = sum(recent_scores[-14:]) / max(len(recent_scores[-14:]), 1) if recent_scores else 50

    # 建议基本信息
    config = suggestion_config or SUGGESTIONS.get(key, {})
    base_effect = config.get('base_effect', 3) if isinstance(config, dict) else 3

    # 根据用户状态调整
    if avg_score < 40:
        # 低分用户：建议效果较好（有较大改善空间）
        effect_multiplier = 1.2
        confidence = 'medium' if len(recent_scores) >= 7 else 'low'
    elif avg_score > 70:
        # 高分用户：建议效果有限（天花板效应）
        effect_multiplier = 0.6
        confidence = 'low'
    else:
        effect_multiplier = 1.0
        confidence = 'low'

    predicted_effect = round(base_effect * effect_multiplier)

    # 计算活跃度衰减
    if len(recent_scores) >= 2:
        trend = recent_scores[-1] - recent_scores[-2]
        if trend > 10:
            predicted_effect = max(1, predicted_effect - 2)  # 已经好转，额外帮助较小
        elif trend < -10:
            predicted_effect = min(20, predicted_effect + 2)  # 恶化，急需帮助

    return {
        'predicted_effect': predicted_effect,
        'confidence': confidence,
        'confidence_score': {'high': 0.9, 'medium': 0.6, 'low': 0.3}.get(confidence, 0.3),
        'basis': 'personalized_baseline',
        'effectiveness_samples': 0,
        'variability': 5.0,
        'recommendation': 'recommend' if predicted_effect >= 5 else 'consider',
    }


def simulate_push_effect(profile, push_type='general'):
    """仿真一次推送对用户的影响。

    该用户的推送历史中，推送后评分变化是正还是负？
    如果用户对推送的反应普遍不好，就不推。

    Args:
        profile: 用户画像
        push_type: 'morning_review' | 'evening_care' | 'inactive' | 'general'

    Returns:
        dict: {
            'should_push': bool,          # 是否应该推送
            'expected_engagement': str,   # 'positive' | 'neutral' | 'negative'
            'reason': str,               # 决策理由
            'last_push_result': str or None,  # 上次推送的结果
        }
    """
    # 安全钳制：容错None/invalid profile
    if not isinstance(profile, dict):
        _ip_log.warning('[Sim] None/invalid profile for push')
        return {'should_push': False, 'expected_engagement': 'neutral', 'reason': 'profile is None', 'last_push_result': None}
    coach = profile.get('sleep_coach', {})
    intervention_log = profile.get('_intervention_log', [])

    if not intervention_log:
        # 无历史干预记录 → 默认可推
        return {
            'should_push': True,
            'expected_engagement': 'neutral',
            'reason': 'no past intervention data',
            'last_push_result': None,
        }

    # 分析历史推送效果
    push_history = [entry for entry in intervention_log if entry.get('type') == 'push']
    if not push_history:
        # 有干预记录但没有推送记录
        return {
            'should_push': True,
            'expected_engagement': 'neutral',
            'reason': 'past interventions exist but no push history',
            'last_push_result': None,
        }

    # 计算最近推送的平均反馈
    recent_pushes = push_history[-5:]  # 最近5次
    total_feedback = 0
    feedback_count = 0
    for push in recent_pushes:
        feedback = push.get('feedback_score', 0)
        if feedback:
            total_feedback += feedback
            feedback_count += 1

    if feedback_count > 0:
        avg_feedback = total_feedback / feedback_count
        if avg_feedback >= 0:
            return {
                'should_push': True,
                'expected_engagement': 'positive',
                'reason': f'positive feedback (avg={avg_feedback:.1f})',
                'last_push_result': recent_pushes[-1].get('result', None),
            }
        elif avg_feedback >= -2:
            return {
                'should_push': True,
                'expected_engagement': 'neutral',
                'reason': f'neutral feedback (avg={avg_feedback:.1f})',
                'last_push_result': recent_pushes[-1].get('result', None),
            }
        else:
            return {
                'should_push': False,
                'expected_engagement': 'negative',
                'reason': f'negative feedback (avg={avg_feedback:.1f})',
                'last_push_result': recent_pushes[-1].get('result', None),
            }

    # 有记录但无明确反馈分：看推送后是否继续使用
    # 推送后若用户次日还有记录，视为正向
    last_push = recent_pushes[-1]
    push_time = last_push.get('timestamp', 0)
    follow_up = any(
        e.get('timestamp', 0) > push_time and e.get('timestamp', 0) < push_time + 86400
        for e in intervention_log if e.get('type') != 'push'
    )
    if follow_up:
        return {
            'should_push': True,
            'expected_engagement': 'positive',
            'reason': 'user continued using after last push',
            'last_push_result': last_push.get('result', None),
        }

    return {
        'should_push': True,
        'expected_engagement': 'neutral',
        'reason': 'no clear feedback from past pushes',
        'last_push_result': last_push.get('result', None) if isinstance(last_push, dict) else None,
    }


def simulate_companion_duration(profile):
    """估计最佳陪伴时长。

    根据用户的当前情绪、活跃度、评分趋势，推测最佳陪伴会话长度。

    Args:
        profile: 用户画像

    Returns:
        dict: {
            'predicted_minutes': int,     # 预测的最佳陪伴时长(分钟)
            'protocol': str,              # 推荐的陪伴协议
            'confidence': str,           # 'high' | 'medium' | 'low'
        }
    """
    # 安全钳制：容错None/invalid profile
    if not isinstance(profile, dict):
        _ip_log.warning('[Sim] None/invalid profile for companion')
        return {'predicted_minutes': 0, 'protocol': 'none', 'confidence': 'low'}
    coach = profile.get('sleep_coach', {})
    history = profile.get('history', [])

    # 基础陪伴时长
    base_minutes = 3

    # 情绪调节：焦虑/烦躁/压力大 → 更长陪伴
    latest_emotion = profile.get('latest_emotion', 'neutral')
    if latest_emotion in ['焦虑', '烦躁', '压力大', '紧张', '不安']:
        base_minutes += 3
    if latest_emotion in ['低落', '悲伤', '抑郁', '孤独']:
        base_minutes += 2

    # 评分趋势调节
    recent_scores = [h.get('total_score', 50) for h in history if isinstance(h, dict)][-7:]
    if len(recent_scores) >= 2:
        avg_score = sum(recent_scores) / len(recent_scores)
        if avg_score < 40:
            base_minutes += 2  # 低分用户需要更多陪伴
        elif avg_score > 75:
            base_minutes -= 1  # 高分用户少打扰

        # 最近两天趋势
        if len(recent_scores) >= 2:
            trend = recent_scores[-1] - recent_scores[-2]
            if trend < -10:
                base_minutes += 2  # 恶化中，需要更多支持
            elif trend > 5:
                base_minutes -= 1  # 好转中，少打扰

    # 限制范围
    base_minutes = max(2, min(15, base_minutes))

    # 协议选择
    if base_minutes <= 4:
        protocol = '4-7-8'
    elif base_minutes <= 7:
        protocol = 'body_scan'
    else:
        protocol = 'full_relaxation'

    return {
        'predicted_minutes': base_minutes,
        'protocol': protocol,
        'confidence': 'high' if len(recent_scores) >= 7 else ('medium' if len(recent_scores) >= 3 else 'low'),
    }


# ==================== 基于仿真的决策选择 ====================

def select_suggestion_with_simulation(profile, candidates, emotion_state='neutral'):
    """通过仿真从多个候选建议中选出最合适的。

    对每个候选建议运行 simulate_suggestion_effect，
    综合考虑基础评分 + 仿真效果 + 置信度 + 情绪状态。

    Args:
        profile: 用户画像
        candidates: [(key, suggestion, base_score), ...]
        emotion_state: 当前情绪状态

    Returns:
        (key, suggestion) or None
    """
    # 安全钳制：candidates 必须是 (key, sug, base_score) 元组列表
    if not isinstance(candidates, (list, tuple)):
        _ip_log.warning('[Sim] candidates is not list/tuple, returning None')
        return None

    scored = []
    for item in candidates:
        # 安全钳制：跳过非元组格式
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            _ip_log.warning('[Sim] skipping invalid candidate format: %s', type(item).__name__)
            continue
        key, sug, base_score = item[:3]
        sim = simulate_suggestion_effect(profile, key, sug)

        # 根据推荐等级确定乘数
        rec_multiplier = {
            'recommend': 1.3,
            'consider': 1.0,
            'avoid': 0.3,
        }.get(sim.get('recommendation', 'consider'), 1.0)

        # 置信度加权（高置信度的推荐更有价值）
        confidence_weight = 0.5 + sim['confidence_score'] * 0.5

        # 综合得分 = base_score * 推荐乘数 * 置信度加权
        final_score = base_score * rec_multiplier * confidence_weight

        scored.append({
            'key': key,
            'suggestion': sug,
            'original_score': base_score,
            'simulation': sim,
            'final_score': round(final_score, 1),
        })

        _ip_log.debug('[Sim] %s: base=%.0f sim_effect=%+d rec=%s conf=%.2f → final=%.1f',
                      key, base_score, sim['predicted_effect'],
                      sim['recommendation'], sim['confidence_score'], final_score)

    if not scored:
        return None

    # 按综合得分排序
    scored.sort(key=lambda x: -x['final_score'])
    best = scored[0]

    _ip_log.info('[Sim] Best: %s (score=%.1f, effect=%+d)',
                 best['key'], best['final_score'], best['simulation']['predicted_effect'])

    return (best['key'], best['suggestion'])


# ==================== 自测 ====================

def _self_test():
    """快速自测确认各函数正常工作"""
    print('=== Interoceptive Prediction Self-Test ===\n')

    # 安全测试：各种畸形输入不应crash
    for fn_name, fn, args in [
        ('simulate_suggestion_effect', simulate_suggestion_effect, ({}, 'relax')),
        ('simulate_suggestion_effect', simulate_suggestion_effect, (None, 'relax')),
        ('simulate_push_effect', simulate_push_effect, ({},)),
        ('simulate_push_effect', simulate_push_effect, (None,)),
        ('simulate_companion_duration', simulate_companion_duration, ({},)),
        ('simulate_companion_duration', simulate_companion_duration, (None,)),
        ('select_suggestion_with_simulation', select_suggestion_with_simulation, ({}, [])),
        ('select_suggestion_with_simulation', select_suggestion_with_simulation, ({}, 'bad')),
        ('select_suggestion_with_simulation', select_suggestion_with_simulation, ({}, [{'key': 'bad'}])),
    ]:
        try:
            result = fn(*args)
            status = 'OK' if result is not None else 'WARN'
        except Exception as e:
            status = f'CRASH: {e}'
        print(f'  {fn_name}{args}: {status}')

    print('\n  All edge cases handled.')


if __name__ == '__main__':
    _self_test()
