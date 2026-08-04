#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exploration_engine.py — AISleepGen 探索-利用权衡引擎

第一性原理（Sutton & Barto, 2018）：
纯利用系统陷入局部最优——从不推荐用户没试过的方案。
ε-贪婪策略：以概率 ε 探索未验证方案，以概率 1-ε 利用最佳已知方案。

探索的意义：
1. 发现用户对某个未试方案的真正反应
2. 避免"一直推荐固定的东西 → 用户免疫 → 效果衰减"的恶性循环
3. 新鲜感本身可以提高执行率（行为经济学：新方案 = 新希望效应）

规则：
- ε = 0.15（15%概率探索，85%利用）
- 探索时从"从未被推荐的方案"中随机选一个
- 探索候选集 = 所有未被推荐过 + 被推荐过但未评价且超过30天
- 数据不足(<3次历史推荐)时 ε 提升到0.3（多探索）
- 探索后必须跟踪效果，无效方案从候选集移除

数据不足时自动降级到纯利用模式（ε=0）。
"""
import random
import math
from datetime import datetime, timedelta


def _get_never_tried(profile):
    """获取用户从未被推荐过的方案"""
    tried = set()
    for entry in profile.get('_recommendation_history', []):
        tid = entry.get('type', '')
        if tid:
            tried.add(tid)
    # 从现有方案中过滤
    from intervention_scheduler import _INTERVENTIONS
    never = [sid for sid in _INTERVENTIONS if sid not in tried and not _INTERVENTIONS[sid].get('require_pain', False)]
    return never


def _get_expired_suggestions(profile, max_days=30):
    """获取被推荐过但从未评价（用户没理）且超过max_d天的方案"""
    from intervention_scheduler import _INTERVENTIONS
    tried_but_dead = []
    history = profile.get('_recommendation_history', [])
    now = datetime.now()
    for entry in history:
        if entry.get('status') == 'evaluated':
            continue
        tid = entry.get('type', '')
        if not tid or tid not in _INTERVENTIONS:
            continue
        date_str = entry.get('date', '')
        if not date_str:
            continue
        try:
            d = datetime.strptime(date_str, '%Y-%m-%d')
            if (now - d).days >= max_days:
                tried_but_dead.append(tid)
        except:
            pass
    return list(set(tried_but_dead))


def _estimate_known_strategy_count(profile):
    """统计用户历史中被推荐过的不同方案数"""
    history = profile.get('_recommendation_history', [])
    return len(set(e.get('type', '') for e in history if e.get('type', '')))


def should_explore(profile, target_dim='unknown'):
    """判断本次是否应该探索

    返回: (bool, str) — (是否探索, 探索原因)
    """
    from intervention_scheduler import _INTERVENTIONS

    # 数据不足时降级到纯利用
    history = profile.get('_recommendation_history', [])
    if len(history) < 3:
        return False, '数据不足，不探索'

    # ═══ NGU内在好奇心：如果当前状态异常，主动探索 ═══
    try:
        from state_topology import check_anomalous
        anomaly = check_anomalous(profile)
        if anomaly.get('is_anomalous'):
            return True, f'NGU好奇心：{anomaly["anomaly_type"]}'
    except Exception:
        pass

    # 计算 epsilon
    known_count = _estimate_known_strategy_count(profile)
    total_count = len([s for s in _INTERVENTIONS.values() if not s.get('require_pain', False)])

    # 知道的比例越高 → 探索需求越低（知道的多了，捡漏概率小）
    known_ratio = known_count / max(total_count, 1)
    
    # 自适应 epsilon
    if known_ratio < 0.3:
        epsilon = 0.30  # 知道的少，多探索
    elif known_ratio < 0.6:
        epsilon = 0.20
    else:
        epsilon = 0.12  # 知道的差不多了，少探索
    
    # 如果没有可探索的候选集
    never = _get_never_tried(profile)
    expired = _get_expired_suggestions(profile)
    candidates = never + expired
    if not candidates:
        return False, '无未探索方案'

    # ε-贪婪决策
    if random.random() < epsilon:
        return True, f'ε-贪婪探索(ε={epsilon}, 已知{known_count}/{total_count})'

    return False, '利用模式'


def select_exploration_strategy(profile, target_dim='unknown'):
    """从探索候选集中选择一个方案

    选择策略：
    1. 优先选从未被推荐过的
    2. 其次选被推荐过但用户没理的
    3. 匹配目标维度的优先
    
    返回: (strategy_id, strategy_name) 或 None
    """
    from intervention_scheduler import _INTERVENTIONS
    
    never = _get_never_tried(profile)
    expired = _get_expired_suggestions(profile)
    
    # 优先从未推荐集中选（真正的探索）
    candidates = []
    
    # 匹配目标维度的优先
    for sid in never:
        s = _INTERVENTIONS.get(sid)
        if s and (target_dim in s['target_dims'] or 'unknown' in s['target_dims']):
            candidates.append((0, sid))  # 优先级0
    for sid in never:
        if sid not in [c[1] for c in candidates]:
            s = _INTERVENTIONS.get(sid)
            if s and not s.get('require_pain', False):
                candidates.append((1, sid))
    
    # 如果探索候选集中没有符合目标的，再从过期集补充
    if not candidates:
        for sid in expired:
            s = _INTERVENTIONS.get(sid)
            if s and (target_dim in s['target_dims'] or 'unknown' in s['target_dims']):
                candidates.append((1, sid))
    
    if not candidates:
        return None
    
    # 随机选一个（探索的本质）
    candidates.sort(key=lambda x: x[0])
    best_priority = candidates[0][0]
    top = [c for c in candidates if c[0] == best_priority]
    sid = random.choice(top)[1]
    s = _INTERVENTIONS.get(sid, {})
    return sid, s.get('name', sid)


def reset_exploration_state(profile, new_day=True):
    """重置探索状态（每天调用一次）
    
    new_day=True 时，把当天的探索计数重置
    """
    state = profile.setdefault('_exploration_state', {})
    if new_day:
        state['today_explored'] = False
        state['today_date'] = datetime.now().strftime('%Y-%m-%d')
    return state


def get_exploration_summary(profile):
    """返回探索概览（用于日志和审计）"""
    from intervention_scheduler import _INTERVENTIONS
    never = _get_never_tried(profile)
    expired = _get_expired_suggestions(profile)
    known = _estimate_known_strategy_count(profile)
    total = len([s for s in _INTERVENTIONS.values() if not s.get('require_pain', False)])
    return {
        'known_strategies': known,
        'total_available': total,
        'never_tried': len(never),
        'expired_recommendations': len(expired),
        'exploration_progress': f'{known}/{total}',
    }


# ===== 快速测试 =====
if __name__ == '__main__':
    test_profile = {
        '_recommendation_history': [
            {'type': 'wind_down_routine', 'date': '2026-07-01', 'status': 'evaluated'},
            {'type': 'fixed_schedule', 'date': '2026-07-02', 'status': 'evaluated'},
            {'type': 'stress_write_down', 'date': '2026-07-03', 'status': 'pending'},
        ]
    }
    explore, reason = should_explore(test_profile)
    print(f'是否探索: {explore}')
    print(f'原因: {reason}')
    
    sel = select_exploration_strategy(test_profile)
    if sel:
        print(f'探索方案: {sel[1]} ({sel[0]})')
    
    summary = get_exploration_summary(test_profile)
    print(f'探索概览: {summary}')
