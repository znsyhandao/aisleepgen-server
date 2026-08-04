#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recommendation_tracker.py — AISleepGen 建议追踪器

TL;DR: 把 AI 的建议变成可追踪、可验证的效果单元。

核心循环：
  1. handle_chat 回复后 → _extract_recommendations(reply) → 存到 profile
  2. 下次用户上报数据 → _evaluate_recommendations(openid) → 比对评分变化
  3. 注入到 prompt → AI 知道"上次的建议有用/没用"
"""

import re, json, time
from datetime import datetime, timedelta
from copy import deepcopy

# 可识别的建议类型
_RECOMMENDATION_TYPES = {
    'fixed_schedule': ['固定作息', '固定时间', '定时', '规律', '同一时间', '准时'],
    'wind_down': ['睡前放松', '放下手机', '远离屏幕', '放松活动', '热水澡', '泡脚', '冥想'],
    'sleep_hygiene': ['睡眠环境', '卧室', '温度', '光线', '安静', '床垫', '枕头'],
    'bedtime_earlier': ['提前上床', '早点睡', '提前入睡', '早睡'],
    'wake_fixed': ['固定起床', '准时起床', '不赖床', '同一时间起'],
    'exercise': ['运动', '锻炼', '散步', '跑步', '有氧'],
    'diet': ['饮食', '咖啡', '咖啡因', '酒精', '睡前吃', '晚餐', '茶'],
    'stress_mgmt': ['减压', '放松', '深呼吸', '腹式呼吸', '正念', '冥想', '焦虑'],
    'daytime_activity': ['白天活动', '日间', '午睡', '晒太阳', '户外'],
    'seek_help': ['就医', '看医生', '检查', '诊断', '专科', '医院'],
}

# 建议效果类型
_EFFECT_POSITIVE = 'positive'
_EFFECT_NEGATIVE = 'negative'
_EFFECT_NEUTRAL = 'neutral'


def _extract_recommendations(text):
    """从 AI 回复中提取建议类型列表"""
    if not text:
        return []
    found = set()
    for rec_type, keywords in _RECOMMENDATION_TYPES.items():
        for kw in keywords:
            if kw in text:
                found.add(rec_type)
                break
    return list(found)


def store_recommendations(profile, reply_text, wm_score_before):
    """把 AI 回复中的建议存到 profile"""
    recs = _extract_recommendations(reply_text)
    if not recs:
        return profile
    
    store = profile.setdefault('_recommendation_history', [])
    now = datetime.now().strftime('%Y-%m-%d')
    for r in recs:
        # 同一天同类型不重复记录
        if any(e.get('date') == now and e.get('type') == r for e in store):
            continue
        store.append({
            'date': now,
            'type': r,
            'score_at_time': wm_score_before,
            'status': 'pending',  # pending / evaluated
            'effect': None,  # positive / negative / neutral
            'score_after': None,
            'evaluated_on': None,
        })
        # 只保留最近 100 条
        if len(store) > 100:
            store[:] = store[-100:]
    
    return profile


def evaluate_pending_recommendations(profile, current_score):
    """评估所有 pending 的建议——用当前评分 vs 建议时的评分
    
    简单规则：
    - 建议后评分上升 >5 分 → positive
    - 建议后评分下降 >5 分 → negative
    - 其他 → neutral
    """
    store = profile.get('_recommendation_history', [])
    changed = False
    for rec in store:
        if rec.get('status') != 'pending':
            continue
        score_before = rec.get('score_at_time') or current_score
        delta = current_score - score_before
        if delta > 5:
            rec['effect'] = _EFFECT_POSITIVE
        elif delta < -5:
            rec['effect'] = _EFFECT_NEGATIVE
        else:
            rec['effect'] = _EFFECT_NEUTRAL
        rec['score_after'] = current_score
        rec['status'] = 'evaluated'
        rec['evaluated_on'] = datetime.now().strftime('%Y-%m-%d')
        changed = True
    
    if changed:
        profile['_recommendation_history'] = store
    return profile, changed


def get_recommendation_insights(profile):
    """生成建议效果总结（注入 prompt 用）
    
    返回示例：
    "【建议效果追踪】
    - 你上次建议'固定作息'：用户尝试后评分从 57→72，效果良好
    - 你上次建议'睡前放松'：用户尝试后评分从 57→55，效果不佳
    - 整体：固定作息有效(+15)，睡前放松无效(-2)
    "
    """
    store = profile.get('_recommendation_history', [])
    if not store:
        return ''
    
    # 只分析最近 7 天的已评估建议
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    recent = [r for r in store if r.get('status') == 'evaluated' and r.get('date', '') >= week_ago]
    if not recent:
        return ''
    
    # 按类型汇总效果
    type_stats = {}
    for r in recent:
        t = r['type']
        if t not in type_stats:
            type_stats[t] = {'count': 0, 'positive': 0, 'negative': 0, 'neutral': 0, 'total_delta': 0}
        type_stats[t]['count'] += 1
        effect = r.get('effect', 'neutral')
        type_stats[t][effect] += 1
        delta = (r.get('score_after') or 0) - (r.get('score_at_time') or 0)
        type_stats[t]['total_delta'] += delta
    
    lines = ['\n【建议效果追踪】']
    sorted_types = sorted(type_stats.items(), key=lambda x: x[1]['total_delta'], reverse=True)
    for rec_type, stats in sorted_types:
        emoji = '✅' if stats['total_delta'] > 0 else ('❌' if stats['total_delta'] < 0 else '➖')
        avg_delta = stats['total_delta'] / max(stats['count'], 1)
        lines.append(f'  {emoji} {rec_type}: 建议{stats["count"]}次, 有效{stats["positive"]}次/无效{stats["negative"]}次, 平均效果{avg_delta:+.1f}分')
    
    # 整体建议
    best_type = sorted_types[0] if sorted_types else None
    worst_type = sorted_types[-1] if len(sorted_types) > 1 else None
    if best_type and best_type[1]['total_delta'] > 5:
        lines.append(f'  策略参考: {best_type[0]}效果最好，建议优先推荐')
    if worst_type and worst_type[1]['total_delta'] < -5:
        lines.append(f'  策略参考: {worst_type[0]}效果不理想，建议减少推荐或换方式')
    
    return '\n'.join(lines)


# ═══ GRPO式组间对比评估（DeepSeek R1启示） ═══
# 传统方法：单点比较("今天vs昨天")
# GRPO方法：组间比较("最好的3天vs最差的3天差异")

_EFFECT_POSITIVE = 'positive'
_EFFECT_NEGATIVE = 'negative'
_EFFECT_NEUTRAL = 'neutral'


def grpo_group_evaluation(profile, min_group_size=3):
    """GRPO式组间对比评估：不是比"今天vs昨天"，而是"最好的3天 vs 最差的3天"

    步骤：
    1. 从 profile.history 取最近 N 天的评分
    2. 按评分排序，取 Top-K 和 Bottom-K
    3. 对比两组中"干预类型分布"——找出在好日子里更常见的干预类型
    4. 标记：某个干预类型如果在好日子组中出现频率显著高 → 认定有效
            如果差日子组中反而出现频率高 → 认定无效

    这比单点比较更稳健——避开"自然波动被误认为干预效果"的问题。

    返回: {
        'has_enough_data': bool,
        'group_effects': { strategy_id: 'positive'|'negative'|'neutral'|'insufficient' },
        'comparison': {
            'top_group': { 'avg_score': 浮点数, 'n': int, 'strategies': {sid: 出现次数} },
            'bottom_group': { 'avg_score': 浮点数, 'n': int, 'strategies': {sid: 出现次数} },
        }
    }
    """
    history = profile.get('history', [])
    rec_history = profile.get('_recommendation_history', [])

    # 数据检查
    if not history or not rec_history:
        return {'has_enough_data': False, 'group_effects': {}, 'comparison': {}}

    # 筛选有评分的记录 + 关联干预
    scored_days = []
    rec_map = {}  # date → [(sid, delta_effect)]
    for r in rec_history:
        d = r.get('date', '')
        if d not in rec_map:
            rec_map[d] = []
        delta = (r.get('score_after') or 0) - (r.get('score_at_time') or 0)
        rec_map[d].append((r.get('type', ''), delta))

    for h in history:
        if not isinstance(h, dict):
            continue
        d = h.get('date', '')
        score = h.get('wm_score', 0)
        if score <= 0:
            continue
        strategies = rec_map.get(d, [])
        scored_days.append({'date': d, 'score': score, 'strategies': strategies})

    if len(scored_days) < min_group_size * 2:
        return {'has_enough_data': False, 'group_effects': {}, 'comparison': {}}

    # 按评分排序
    sorted_days = sorted(scored_days, key=lambda x: x['score'], reverse=True)
    top_k = sorted_days[:min_group_size]
    bottom_k = sorted_days[-min_group_size:]

    # 统计两组中的干预分布
    def _count_strategies(days):
        counts = {}
        total_score = 0
        for d in days:
            total_score += d['score']
            for sid, _ in d['strategies']:
                counts[sid] = counts.get(sid, 0) + 1
        return {
            'avg_score': round(total_score / len(days), 1),
            'n': len(days),
            'strategies': counts,
        }

    top_stats = _count_strategies(top_k)
    bottom_stats = _count_strategies(bottom_k)

    # 对比两组中每个策略的出现频率
    all_strategies = set(list(top_stats['strategies'].keys()) + list(bottom_stats['strategies'].keys()))
    group_effects = {}

    for sid in all_strategies:
        top_freq = top_stats['strategies'].get(sid, 0)
        bottom_freq = bottom_stats['strategies'].get(sid, 0)
        total_freq = top_freq + bottom_freq

        if total_freq < 1:
            group_effects[sid] = 'insufficient'
            continue

        # 好日子组中出现比例显著高(≥2/3) → positive
        top_ratio = top_freq / max(total_freq, 1)
        if top_ratio >= 0.67:
            group_effects[sid] = _EFFECT_POSITIVE
        elif top_ratio <= 0.33:
            # 好日子组出现比例极低(≤1/3)，说明多是差日子时被推荐 → 无效甚至有害
            group_effects[sid] = _EFFECT_NEGATIVE
        else:
            group_effects[sid] = _EFFECT_NEUTRAL

    return {
        'has_enough_data': True,
        'group_effects': group_effects,
        'comparison': {
            'top_group': top_stats,
            'bottom_group': bottom_stats,
        }
    }


# ═══ GRPO策略梯度（真RL优化版） ═══
# 不是统计比对，而是用组间优势计算策略梯度更新：
# gradient = (top_group_freq - bottom_group_freq) / total_freq * confidence
# 然后写回 profile._grpo_weights，供 intervention_scheduler 读取

_GRPO_LEARNING_RATE = 0.1

def grpo_update_policy(profile):
    """GRPO策略梯度更新

    从 grpo_group_evaluation 的结果中提取梯度，
    用组间频率差作为优势信号，更新策略权重。

    返回: {strategy_id: new_weight} 更新后的权重
    """
    result = grpo_group_evaluation(profile)
    if not result['has_enough_data']:
        return {}

    top_stats = result['comparison']['top_group']
    bottom_stats = result['comparison']['bottom_group']

    # 加载或初始化当前权重
    weights = profile.setdefault('_grpo_weights', {})

    for sid, effect in result['group_effects'].items():
        if effect == 'insufficient':
            continue
        top_freq = top_stats['strategies'].get(sid, 0)
        bottom_freq = bottom_stats['strategies'].get(sid, 0)
        total_freq = top_freq + bottom_freq

        if total_freq < 1:
            continue

        # 优势 = 好日子频率 - 差日子频率（归一化后）
        top_ratio = top_freq / max(total_freq, 1)
        bottom_ratio = bottom_freq / max(total_freq, 1)
        advantage = top_ratio - bottom_ratio  # [-1, 1]
        # 置信度：总出现次数越多越可信
        confidence = min(total_freq / 5.0, 1.0)

        # 梯度更新
        gradient = advantage * confidence * _GRPO_LEARNING_RATE
        old_weight = weights.get(sid, 0.0)
        new_weight = max(-1.0, min(1.0, old_weight + gradient))

        # 如果优势为负且当前权重为正，直接置零（策略无效）
        if advantage < -0.3 and old_weight > 0:
            new_weight = 0.0

        weights[sid] = round(new_weight, 2)

    return weights


# ===== 快速测试 =====
if __name__ == '__main__':
    test_reply = ('建议你把入睡时间固定到11点，同时睡前1小时放下手机。'
                  '如果睡不着，试试腹式呼吸5分钟。另外白天多晒晒太阳。')
    recs = _extract_recommendations(test_reply)
    print('提取建议:', recs)
    
    profile = {'_recommendation_history': []}
    profile = store_recommendations(profile, test_reply, 57)
    print('\n存储后:', len(profile['_recommendation_history']), '条')
    
    profile, _ = evaluate_pending_recommendations(profile, 72)
    print('\n评估后效果:')
    for r in profile['_recommendation_history']:
        print(f'  {r["type"]}: {r["score_at_time"]}→{r["score_after"]} = {r["effect"]}')
    
    insights = get_recommendation_insights(profile)
    print('\nPrompt注入:\n', insights)
