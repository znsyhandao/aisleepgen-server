#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
online_rl_routes.py — AISleepGen Online RL 路由处理

为 dp_router 注入 4 条 RL 管理路由：
  - /api/rl/act     → 手动触发RL决策测试
  - /api/rl/update  → 手动更新Q值
  - /api/rl/status  → 策略统计（含双表差异检测）
  - /api/rl/reset   → 重置Q表

注意：这些路由是独立的，不依赖 dp_router 的内部结构，
在 dp_router.dispatch() 中被路由到。
"""

import json, logging, time
from datetime import datetime

_rl_log = logging.getLogger('aisleepgen.online_rl.routes')


def handle_rl_act(data):
    """手动触发RL决策测试

    POST /api/rl/act
    Body: {openid, context?}
    """
    openid = data.get('openid', 'default')
    context = data.get('context', {})

    try:
        from online_rl import get_online_rl
        rl = get_online_rl()
        action = rl.act(openid, context)
        # 获取Q表状态
        from online_rl import StateEncoder
        state_idx = StateEncoder.from_context(
            score=context.get('score'),
            trend=context.get('trend'),
            entropy=context.get('pomdp_entropy'),
            last_effect=context.get('last_effect'),
        )
        action_values = {}
        from online_rl import ACTIONS
        for a in ACTIONS:
            action_values[a] = rl.get_action_value(openid, a)

        summary = rl.get_policy_summary(openid)
        epsilon = rl._get_effective_epsilon(openid, context)

        # 获取所有行动的Q值（当前状态）
        q1_vals = {a: rl._q(openid, state_idx, i, 'Q1')
                   for i, a in enumerate(ACTIONS)}
        q2_vals = {a: rl._q(openid, state_idx, i, 'Q2')
                   for i, a in enumerate(ACTIONS)}

        return {
            'action': action,
            'state_idx': state_idx,
            'epsilon': epsilon,
            'use_table': 'Q1' if (summary.get('total_updates', 0) // 2) % 2 == 0 else 'Q2',
            'q1': q1_vals,
            'q2': q2_vals,
            'action_values_avg': action_values,
            'total_updates': summary.get('total_updates', 0),
            'timestamp': datetime.now().isoformat(),
        }
    except ImportError:
        return {'error': 'online_rl module not available'}
    except Exception as e:
        _rl_log.error('[RL Route] act failed: %s', e)
        return {'error': str(e)}


def handle_rl_update(data):
    """手动更新Q值

    POST /api/rl/update
    Body: {openid, action, reward, next_context?, force_table?}
    """
    openid = data.get('openid', 'default')
    action = data.get('action', 'skip')
    reward = data.get('reward', 0.0)
    next_context = data.get('next_context', {})

    try:
        from online_rl import get_online_rl
        rl = get_online_rl()
        td_error = rl.update(openid, action, reward, next_context)

        summary = rl.get_policy_summary(openid)
        q_after = rl.get_action_value(openid, action)

        return {
            'td_error': round(td_error, 4),
            'q_after': q_after,
            'action': action,
            'reward': reward,
            'total_updates': summary.get('total_updates', 0),
            'timestamp': datetime.now().isoformat(),
        }
    except ImportError:
        return {'error': 'online_rl module not available'}
    except Exception as e:
        _rl_log.error('[RL Route] update failed: %s', e)
        return {'error': str(e)}


def handle_rl_status(data):
    """策略统计

    POST /api/rl/status
    Body: {openid}
    """
    openid = data.get('openid', 'default')

    try:
        from online_rl import get_online_rl
        rl = get_online_rl()
        summary = rl.get_policy_summary(openid)

        from online_rl import ACTIONS
        action_values = {}
        for a in ACTIONS:
            action_values[a] = rl.get_action_value(openid, a)

        return {
            **summary,
            'action_values_avg': action_values,
            'timestamp': datetime.now().isoformat(),
        }
    except ImportError:
        return {'error': 'online_rl module not available'}
    except Exception as e:
        _rl_log.error('[RL Route] status failed: %s', e)
        return {'error': str(e)}


def handle_rl_reset(data):
    """重置Q表

    POST /api/rl/reset
    Body: {openid}
    """
    openid = data.get('openid', 'default')

    try:
        from online_rl import get_online_rl
        rl = get_online_rl()
        rl.reset_q(openid)

        return {
            'status': 'reset',
            'openid': openid[:8],
            'timestamp': datetime.now().isoformat(),
        }
    except ImportError:
        return {'error': 'online_rl module not available'}
    except Exception as e:
        _rl_log.error('[RL Route] reset failed: %s', e)
        return {'error': str(e)}


# ==================== 自动注册到dp_router ====================

def register_routes():
    """将RL路由注册到 dp_router.ROUTES 中"""
    try:
        import dp_router

        new_routes = {
            ('POST', '/api/rl/act'): dp_router._safe_handler(handle_rl_act),
            ('POST', '/api/rl/update'): dp_router._safe_handler(handle_rl_update),
            ('POST', '/api/rl/status'): dp_router._safe_handler(handle_rl_status),
            ('POST', '/api/rl/reset'): dp_router._safe_handler(handle_rl_reset),
        }

        dp_router.ROUTES.update(new_routes)
        _rl_log.info('[RL Routes] Registered 4 RL routes to dp_router')
        return True
    except Exception as e:
        _rl_log.warning('[RL Routes] Register failed: %s', e)
        return False


# 模块加载时自动注册
_auto_registered = register_routes()


# ==================== 自测 ====================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')

    print('=== Online RL Routes Self-Test ===')

    # Test 1: Register routes
    print('\n1. Route registration:')
    reg = register_routes()
    print(f'   Registered: {reg}')

    import dp_router
    route_keys = [k for k in dp_router.ROUTES.keys() if k[1].startswith('/api/rl/')]
    print(f'   RL routes: {route_keys}')
    assert len(route_keys) == 4, f'Expected 4 routes, got {len(route_keys)}'
    print('   PASS: 4 routes registered')

    # Test 2: RL act
    print('\n2. RL act route:')
    res = handle_rl_act({'openid': 'test_rl_route', 'context': {'score': 45}})
    print(f'   Act result: action={res.get("action")}, epsilon={res.get("epsilon")}')
    assert 'action' in res, f'act() should return action, got {res}'
    print('   PASS: act route works')

    # Test 3: RL update
    print('\n3. RL update route:')
    res2 = handle_rl_update({'openid': 'test_rl_route', 'action': 'ask',
                              'reward': 0.5})
    print(f'   Update result: td_error={res2.get("td_error")}, q_after={res2.get("q_after")}')
    assert 'td_error' in res2
    print('   PASS: update route works')

    # Test 4: RL status
    print('\n4. RL status route:')
    res3 = handle_rl_status({'openid': 'test_rl_route'})
    print(f'   Status: total_updates={res3.get("total_updates")}, '
          f'best_action={res3.get("best_action")}')
    assert res3.get('total_updates', 0) >= 1
    print('   PASS: status route works')

    # Test 5: RL reset
    print('\n5. RL reset route:')
    res4 = handle_rl_reset({'openid': 'test_rl_route'})
    print(f'   Reset: {res4.get("status")}')
    assert res4.get('status') == 'reset'
    print('   PASS: reset route works')

    print('\nAll tests PASS!')
