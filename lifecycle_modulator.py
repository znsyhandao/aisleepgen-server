#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lifecycle_modulator.py — 用户生命周期调节器 v1.0

纯后处理模块，零侵入。在POMDP做出决策后，根据用户的
"生命周期阶段"对干预策略做微调，不改动POMDP的信念/观测/状态空间。

核心逻辑：
  1. 从用户画像读取使用历史 + 聊天记录 → 推断生命周期阶段
  2. 根据阶段输出调制系数（multipliers）
  3. POMDP决策结果乘以系数 → 最终决策

生命周期阶段：
  - newbie:   第1-3天，<5次交互
  - active:   4-30天，频繁使用
  - regular:  31-90天，稳定使用
  - veteran:  91+天，或总交互>200次
  - dormant:  连续7天未使用
  - churn:    连续30天未使用（已流失）

调制策略：
  - newbie:   probe权重+20%，push权重-50%（多探索少打扰）
  - active:   原样
  - regular:  push权重-20%（老用户不需要频繁推）
  - veteran:  probe权重+10%，push权重-30%（给空间）
  - dormant:  push权重+30%（召回优先）
  - churn:    仅限in_chat（不推送，温和召回）

使用方式:
  from lifecycle_modulator import modulate_decision, get_lifecycle_phase, get_modulator_stats
  modulated = modulate_decision(openid, profile, pomdp_decision)
"""

import json, os, logging, math
from datetime import datetime, timedelta

_lc_log = logging.getLogger('aisleepgen.lifecycle')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ==================== 生命周期阶段 ====================

PHASE_NEWBIE = 'newbie'
PHASE_ACTIVE = 'active'
PHASE_REGULAR = 'regular'
PHASE_VETERAN = 'veteran'
PHASE_DORMANT = 'dormant'
PHASE_CHURN = 'churn'
PHASE_UNKNOWN = 'unknown'

PHASE_LABELS = {
    PHASE_NEWBIE: '新用户',
    PHASE_ACTIVE: '活跃用户',
    PHASE_REGULAR: '稳定用户',
    PHASE_VETERAN: '资深用户',
    PHASE_DORMANT: '休眠用户',
    PHASE_CHURN: '流失用户',
    PHASE_UNKNOWN: '未知',
}

# 调制系数: {phase: {action: multiplier}}
#   action取值: 'probe', 'push', 'delay_push', 'in_chat', 'skip'
#   1.0 = 不变, >1.0 = 提升倾向, <1.0 = 降低倾向
_MODULATION = {
    PHASE_NEWBIE: {
        'probe': 1.2,
        'push': 0.5,
        'delay_push': 0.7,
        'in_chat': 1.0,
        'skip': 0.9,
    },
    PHASE_ACTIVE: {
        'probe': 1.0,
        'push': 1.0,
        'delay_push': 1.0,
        'in_chat': 1.0,
        'skip': 1.0,
    },
    PHASE_REGULAR: {
        'probe': 1.0,
        'push': 0.8,
        'delay_push': 0.9,
        'in_chat': 1.0,
        'skip': 1.1,
    },
    PHASE_VETERAN: {
        'probe': 1.1,
        'push': 0.7,
        'delay_push': 0.8,
        'in_chat': 1.0,
        'skip': 1.15,
    },
    PHASE_DORMANT: {
        'probe': 0.8,
        'push': 1.3,
        'delay_push': 1.2,
        'in_chat': 0.8,
        'skip': 0.6,
    },
    PHASE_CHURN: {
        'probe': 0.5,
        'push': 0.1,
        'delay_push': 0.1,
        'in_chat': 1.5,
        'skip': 0.3,
    },
    PHASE_UNKNOWN: {
        'probe': 1.0,
        'push': 1.0,
        'delay_push': 1.0,
        'in_chat': 1.0,
        'skip': 1.0,
    },
}


def _extract_usage_data(profile):
    """从用户画像提取使用数据

    兼容多种profile格式，返回标准化dict。
    """
    if not profile:
        return {'total_interactions': 0, 'days_used': 0, 'first_date': None, 'last_date': None,
                'streak': 0, 'day_count': 0}

    # 尝试从多个路径读取使用天数
    day_count = profile.get('day_count', 0)
    if not day_count:
        day_count = profile.get('consecutive_days', 0)

    # 尝试读取first_date
    first_date = profile.get('first_date', None)
    if not first_date:
        first_date = profile.get('registered_at', None)
        if not first_date:
            first_date = profile.get('created_at', None)
            if first_date and isinstance(first_date, str):
                first_date = first_date[:10]

    # 从history推断交互次数
    history = profile.get('history', [])
    if isinstance(history, list):
        total_interactions = len(history)
    else:
        total_interactions = history.get('total', 0) if isinstance(history, dict) else 0

    # 从sleep_coach提取更多数据
    coach = profile.get('sleep_coach', {})
    chat_history = coach.get('chat_history', []) if isinstance(coach, dict) else []
    if isinstance(chat_history, list):
        total_interactions += len(chat_history)

    # 计算使用天数
    days_used = 0
    if isinstance(history, list):
        dates = set()
        for h in history:
            d = h.get('date', '') if isinstance(h, dict) else ''
            if d:
                dates.add(str(d))
        days_used = len(dates)

    return {
        'total_interactions': total_interactions,
        'days_used': days_used,
        'first_date': first_date,
        'last_date': profile.get('last_active', None) or profile.get('last_login', None),
        'day_count': day_count,
    }


def infer_phase(openid, profile=None):
    """推断用户生命周期阶段

    Args:
        openid: 用户标识
        profile: 用户画像（可选，没有则用POMDP数据估算）

    Returns:
        str: 阶段标识
    """
    usage = _extract_usage_data(profile)
    ti = usage['total_interactions']
    du = usage['days_used']

    # 填充POMDP数据
    try:
        from pomdp_learner import get_engine
        engine = get_engine()
        user = engine.users.get(openid)
        if user:
            learner = user.get('learner')
            if learner:
                ti = max(ti, learner._total_obs)
    except (ImportError, Exception):
        pass

    # 日期判断
    now = datetime.now()
    first_date = usage.get('first_date')

    days_since_first = None
    if first_date and isinstance(first_date, str):
        try:
            fd = datetime.strptime(first_date[:10], '%Y-%m-%d')
            days_since_first = (now - fd).days
        except ValueError:
            pass

    days_since_last = None
    last_active = profile.get('last_active') if profile else None
    if not last_active:
        last_active = usage.get('last_date')
    if last_active and isinstance(last_active, str):
        try:
            ld = datetime.strptime(last_active[:19] if 'T' in last_active else last_active[:10], '%Y-%m-%d' if 'T' not in last_active else '%Y-%m-%dT%H:%M:%S')
            days_since_last = (now - ld).days
        except ValueError:
            try:
                ld = datetime.strptime(last_active[:10], '%Y-%m-%d')
                days_since_last = (now - ld).days
            except ValueError:
                pass

    # 阶段判定
    # 优先级: 流失 > 休眠 > 新用户 > 天数分级

    # 流失: 30天未使用 & 有过交互
    if days_since_last is not None and days_since_last >= 30 and ti > 0:
        return PHASE_CHURN

    # 休眠: 7天未使用 & 有过交互
    if days_since_last is not None and days_since_last >= 7 and ti > 0:
        return PHASE_DORMANT

    # 新用户: 少交互
    if ti < 5 or (days_since_first is not None and days_since_first <= 3):
        return PHASE_NEWBIE

    # 天数分级 (从first_date算)
    if days_since_first is not None:
        if days_since_first >= 91:
            return PHASE_VETERAN
        elif days_since_first >= 31:
            return PHASE_REGULAR
        elif days_since_first >= 4:
            return PHASE_ACTIVE

    # 用交互次数估算
    if ti > 200:
        return PHASE_VETERAN
    elif ti > 30:
        return PHASE_REGULAR
    elif ti > 5:
        return PHASE_ACTIVE

    return PHASE_NEWBIE


def modulate_decision(openid, profile, pomdp_decision):
    """在POMDP决策后做生命周期调制

    Args:
        openid: 用户标识
        profile: 用户画像 (dict)
        pomdp_decision: POMDP决策输出 (dict with 'action', 'confidence', etc.)

    Returns:
        dict: 调制后的决策 (与原格式兼容)
    """
    phase = infer_phase(openid, profile)
    mod = _MODULATION.get(phase, _MODULATION[PHASE_UNKNOWN])

    action = pomdp_decision.get('action', 'skip')
    original_confidence = pomdp_decision.get('confidence', 0.5)

    # 应用调制系数
    multiplier = mod.get(action, 1.0)
    modulated_confidence = original_confidence * multiplier

    # 钳制至 [0, 1]
    modulated_confidence = max(0.0, min(1.0, modulated_confidence))

    # 构建返回值（保留原始值供追踪）
    modulated = dict(pomdp_decision)
    modulated['confidence'] = modulated_confidence
    modulated['lifecycle_phase'] = phase
    modulated['lifecycle_label'] = PHASE_LABELS.get(phase, '未知')
    modulated['lifecycle_multiplier'] = multiplier
    modulated['lifecycle_original_confidence'] = original_confidence

    return modulated


def get_lifecycle_phase(openid, profile=None):
    """公开接口：直接获取生命周期阶段"""
    return infer_phase(openid, profile)


def get_modulator_stats():
    """获取调制器状态摘要"""
    return {
        'phases': {k: v for k, v in PHASE_LABELS.items()},
        'modulation_map': _MODULATION,
    }


# ==================== 自测 ====================

def _test():
    print('=== Lifecycle Modulator Self-Test ===\n')

    # 1. 新用户
    p1 = {'history': [{'date': '2026-05-03'}], 'sleep_coach': {}}
    assert infer_phase('_test', p1) == PHASE_NEWBIE
    print(f'1. Newbie: {infer_phase("_test", p1)}')

    # 2. 活跃用户（14天，10次交互）
    p2 = {'history': [{'date': f'2026-04-2{i}'} for i in range(1, 10)],
          'first_date': '2026-04-20', 'day_count': 14, 'sleep_coach': {'chat_history': [{'msg': 'x'}]}}
    phase = infer_phase('_test2', p2)
    print(f'2. Active: {phase}')
    assert phase == PHASE_ACTIVE, f'Expected active, got {phase}'

    # 3. 稳定用户（45天）
    p3 = {'history': [{'date': '2026-03-15'} for _ in range(50)],
          'first_date': '2026-03-20', 'day_count': 45, 'sleep_coach': {}}
    phase = infer_phase('_test3', p3)
    print(f'3. Regular: {phase}')
    assert phase == PHASE_REGULAR, f'Expected regular, got {phase}'

    # 4. 资深用户（150天）
    p4 = {'history': [{'date': '2025-12-01'} for _ in range(60)],
          'first_date': '2025-12-01', 'day_count': 150, 'sleep_coach': {}}
    phase = infer_phase('_test4', p4)
    print(f'4. Veteran: {phase}')
    assert phase == PHASE_VETERAN, f'Expected veteran, got {phase}'

    # 5. 休眠用户
    p5 = {'history': [{'date': '2026-04-25'}],
          'first_date': '2026-03-01',
          'last_active': '2026-04-25',
          'sleep_coach': {}}
    phase = infer_phase('_test5', p5)
    print(f'5. Dormant: {phase}')
    assert phase == PHASE_DORMANT, f'Expected dormant, got {phase}'

    # 6. 调制效果：新用户push降低
    decision = {'action': 'push', 'confidence': 0.8, 'reason': 'test'}
    modulated = modulate_decision('_test6', p1, decision)
    print(f'6. Newbie push: {modulated["confidence"]:.2f} (original: {modulated["lifecycle_original_confidence"]})')
    assert modulated['confidence'] < 0.8, 'Newbie push should be reduced'

    # 7. 休眠用户推送增强
    decision = {'action': 'push', 'confidence': 0.5, 'reason': 'test'}
    modulated = modulate_decision('_test7', p5, decision)
    print(f'7. Dormant push: {modulated["confidence"]:.2f} (original: 0.5)')
    assert modulated['confidence'] > 0.5, 'Dormant push should be boosted'

    # 8. 流失用户push被压制
    p8 = dict(p5)
    p8['last_active'] = '2026-03-01'
    decision = {'action': 'push', 'confidence': 0.7, 'reason': 'test'}
    modulated = modulate_decision('_test8', p8, decision)
    print(f'8. Churn push: {modulated["confidence"]:.2f} (original: 0.7)')
    assert modulated['confidence'] < 0.2, 'Churn push should be near-zero'

    # 9. 流失用户in_chat增强
    decision = {'action': 'in_chat', 'confidence': 0.5, 'reason': 'test'}
    modulated = modulate_decision('_test8', p8, decision)
    print(f'9. Churn in_chat: {modulated["confidence"]:.2f} (original: 0.5)')
    assert modulated['confidence'] > 0.5, 'Churn in_chat should be boosted'

    print(f'\nAll 9 tests PASS')


if __name__ == '__main__':
    _test()
