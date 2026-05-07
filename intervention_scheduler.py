#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
intervention_scheduler.py — AISleepGen 干预调度器

职责：基于预测结果 + RL 闭环数据，选择最优干预策略。
"""

import json
import os
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 干预策略清单（每个策略有触发条件和目标）
_INTERVENTIONS = {
    'wind_down_routine': {
        'name': '睡前放松惯例',
        'desc': '睡前30分钟放下手机，做5分钟腹式呼吸或轻度拉伸',
        'target_dims': ['latency', 'anxiety'],
        'priority': 1,
        'require_pain': False,
    },
    'fixed_schedule': {
        'name': '固定作息',
        'desc': '固定23:00入睡和7:00起床，周末也保持一致',
        'target_dims': ['awake', 'duration', 'unknown'],
        'priority': 2,
        'require_pain': False,
    },
    'stress_write_down': {
        'name': '压力释放清单',
        'desc': '睡前把今天担心的所有事写下来，告诉自己"明天再处理"',
        'target_dims': ['anxiety', 'latency'],
        'priority': 3,
        'require_pain': False,
    },
    'wake_stimulus_control': {
        'name': '刺激控制法',
        'desc': '如果在床上躺了20分钟还睡不着，起床到客厅坐会儿，等困了再躺下',
        'target_dims': ['latency', 'awake'],
        'priority': 4,
        'require_pain': False,
    },
    'pain_relief': {
        'name': '疼痛舒缓准备',
        'desc': '睡前温水泡脚15分钟，使用热敷缓解疼痛部位',
        'target_dims': ['pain'],
        'priority': 1,
        'require_pain': True,
    },
    'circle_time': {
        'name': '作息重置',
        'desc': '今晚比平时早30分钟关灯，明天固定时间起床不赖床',
        'target_dims': ['duration', 'awake'],
        'priority': 5,
        'require_pain': False,
    },
}


def _get_verified_strategies(profile, target_dim):
    """从 RL 闭环数据中找已证明对 target_dim 有效的策略"""
    rec_history = profile.get('_recommendation_history', [])
    if not rec_history:
        return []

    verified = []
    for rec in rec_history:
        if rec.get('effect') == 'positive' and rec.get('status') == 'evaluated':
            verified.append(rec['type'])

    return list(set(verified))


def _select_strategy(prediction, wm_result, profile):
    """选择最佳干预策略

    返回: dict 或 None
        {
            'strategy_id': 'wind_down_routine',
            'name': '睡前放松惯例',
            'desc': '...',
            'reason': '入睡困难(预测评分57分) + 腹式呼吸效果已验证',
            'effective_before': True,  # RL 闭环验证过此策略有效
        }
    """
    if prediction is None:
        return None

    predicted = prediction.get('predicted_score', 70)
    direction = prediction.get('direction', 'stable')
    key_concern = prediction.get('key_concern', 'unknown')

    # 只在预测恶化或评分低时触发
    if predicted > 75 and direction != 'worse':
        return None

    # 获取已验证有效的策略
    verified = _get_verified_strategies(profile, key_concern)

    # 选候选策略（按目标维度匹配 + 优先级排序）
    candidates = []
    for sid, s in _INTERVENTIONS.items():
        if s['require_pain'] and not (wm_result and '疼痛' in str(wm_result)):
            continue
        if key_concern in s['target_dims'] or 'unknown' in s['target_dims']:
            priority = s['priority']
            # 如果 RL 闭环验证过有效，优先级提到最前
            if verified and s['name'] in verified:
                priority = 0
            candidates.append((priority, sid, s))

    if not candidates:
        # 兜底：选个通用的
        candidates = [(99, 'fixed_schedule', _INTERVENTIONS['fixed_schedule'])]

    candidates.sort(key=lambda x: x[0])
    _, best_id, best = candidates[0]

    # 构建原因
    reasons = []
    if direction == 'worse':
        reasons.append('评分持续下降')
    elif predicted < 60:
        reasons.append('预测评分偏低(%.0f分)' % predicted)
    else:
        reasons.append('预测评分%.0f分' % predicted)

    if key_concern != 'unknown':
        dim_names = {'latency': '入睡困难', 'awake': '夜醒过多', 'duration': '睡眠不足'}
        reasons.append(dim_names.get(key_concern, key_concern))

    is_verified = best['name'] in verified

    return {
        'strategy_id': best_id,
        'name': best['name'],
        'desc': best['desc'],
        'reason': ' + '.join(reasons),
        'effective_before': is_verified,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }


def schedule_intervention(profile, wm_result):
    """调度入口：分析 + 预测 + 决策 + 写入 profile

    参数:
        profile: 用户 profile dict
        wm_result: 世界模型分析结果（带评分）

    返回:
        scheduled: 是否调度了新干预
        intervention: 干预详情或 None
    """
    from prediction_engine import predict_tonight
    prediction = predict_tonight(profile)

    current_score = wm_result.get('total_score', 0) if wm_result else 0

    # 即使预测结果为空，如果当前评分偏低也直接干预
    if prediction is None:
        if current_score > 0 and current_score < 65:
            # 直接基于当前评分介入
            selected = _select_fallback_strategy(profile, wm_result)
            if selected:
                return _write_to_profile(profile, selected)
        return False, None

    # 如果用户当前评分已经不错且趋势稳定，不做干预
    if current_score > 75 and prediction.get('direction') == 'stable':
        return False, None

    selected = _select_strategy(prediction, wm_result, profile)
    if selected is None:
        return False, None

    return _write_to_profile(profile, selected)


def _select_fallback_strategy(profile, wm_result):
    """当预测数据不足时，基于当前评分的快速策略选择"""
    current_score = wm_result.get('total_score', 0) if wm_result else 0
    if current_score <= 0:
        return None

    reason = '当前评分偏低(%.0f分)' % current_score

    # 有疼痛？
    if '疼痛' in str(wm_result) or 'pain' in str(wm_result).lower():
        return {
            'strategy_id': 'pain_relief',
            'name': _INTERVENTIONS['pain_relief']['name'],
            'desc': _INTERVENTIONS['pain_relief']['desc'],
            'reason': reason,
            'effective_before': False,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }

    # 检查 RL 闭环已验证的策略
    verified = _get_verified_strategies(profile, 'unknown')
    if verified:
        for v in verified:
            for sid, s in _INTERVENTIONS.items():
                if s['name'] == v:
                    return {
                        'strategy_id': sid,
                        'name': s['name'],
                        'desc': s['desc'],
                        'reason': reason + ' + 已验证有效',
                        'effective_before': True,
                        'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    }

    # 默认：固定作息
    s = _INTERVENTIONS['fixed_schedule']
    return {
        'strategy_id': 'fixed_schedule',
        'name': s['name'],
        'desc': s['desc'],
        'reason': reason,
        'effective_before': False,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }


def _write_to_profile(profile, selected):
    """写入干预到 profile"""
    existing = profile.setdefault('_pending_interventions', [])
    for e in existing:
        if e.get('strategy_id') == selected['strategy_id'] and not e.get('completed'):
            return False, None
    selected['status'] = 'pending'
    selected['completed'] = False
    existing.append(selected)
    if len(existing) > 5:
        profile['_pending_interventions'] = existing[-5:]
    return True, selected


def get_pending_interventions(profile):
    """获取当前待完成的干预列表"""
    pending = [i for i in profile.get('_pending_interventions', []) if not i.get('completed')]
    return pending


def mark_intervention_completed(profile, strategy_id):
    """标记干预已完成"""
    for i in profile.get('_pending_interventions', []):
        if i.get('strategy_id') == strategy_id:
            i['completed'] = True
            i['completed_on'] = datetime.now().strftime('%Y-%m-%d')
            return True
    return False


# ===== 快速测试 =====
if __name__ == '__main__':
    profile = {
        'latest': {'sleep_latency': 60, 'awake_times': 2, 'total_duration': 360},
        'history': [{'date': f'2026-0{(d%12)+1:02d}-0{(d%28)+1:02d}', 'wm_score': max(30, 50 - d * 3)} for d in range(5)],
        '_recommendation_history': [
            {'type': 'wind_down_routine', 'effect': 'positive', 'status': 'evaluated', 'score_at_time': 45, 'score_after': 68},
        ],
    }
    wm_result = {'total_score': 55, 'quality': '较差'}
    scheduled, intervention = schedule_intervention(profile, wm_result)
    if scheduled:
        print('Scheduled:', intervention['name'])
        print('  Reason:', intervention['reason'])
        print('  Verified by RL:', intervention['effective_before'])
    else:
        print('No intervention needed')
