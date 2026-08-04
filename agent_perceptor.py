# agent_perceptor.py v1.0 — Agent自主感知引擎
#
# 核心: 把scheduler_daemon从"定时任务"升级为"自主Agent循环"
#
# 循环: Perceive → Reason → Act → Learn
#   Perceive: 扫描数据源变化
#   Reason:   优先级排序+上下文理解+选择行动
#   Act:      调用siege/diary/push/alert
#   Learn:    记录效果+更新Q值
#
# 集成点:
#   - scheduler_daemon (替换其主循环)
#   - dp_router (调用已有路由)
#   - episodic_memory (记录决策)
#   - semantic_memory (学习模式)

import json, os, time, logging
from datetime import datetime, timedelta
from collections import defaultdict

_log = logging.getLogger('aisleepgen.agent')

PROJECT_ROOT = r'D:\AISleepGen_Optimized'
MEM_PATH = os.path.join(PROJECT_ROOT, 'data', 'agent_memory.json')


def _load_agent_memory():
    """加载Agent自身记忆"""
    try:
        if os.path.exists(MEM_PATH):
            with open(MEM_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {'cycles': 0, 'last_perceive': {}, 'learned': [], 'version': '1.0'}


def _save_agent_memory(mem):
    try:
        os.makedirs(os.path.dirname(MEM_PATH), exist_ok=True)
        with open(MEM_PATH, 'w', encoding='utf-8') as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_active_users(min_records=3):
    """获取活跃用户"""
    try:
        from profile_storage import _load_all_profiles
        profiles = _load_all_profiles()
        active = []
        for openid, profile in profiles.items():
            history = profile.get('history', [])
            if len(history) >= min_records:
                recent = [h for h in history if isinstance(h, dict) and
                          h.get('timestamp', '')[:10] >= (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')]
                if recent:
                    active.append((openid, profile))
        return active
    except Exception:
        return []


# ============ Phase 1: Perceive (感知) ============

def perceive(openid: str) -> dict:
    """感知当前情境"""
    signals = {
        'time': datetime.now(),
        'hour': datetime.now().hour,
        'has_new_diary': False,
        'has_new_ring': False,
        'has_new_audio': False,
        'user_score': None,
        'user_silent_days': 0,
        'need_consolidation': False,
        'need_weekly': False,
        'push_window': None,
    }

    hour = signals['hour']
    if 7 <= hour < 9:
        signals['push_window'] = 'morning'
    elif 20 <= hour < 22:
        signals['push_window'] = 'evening'

    # 检查是否需要睡前整理
    if 22 <= hour or hour < 3:
        try:
            from episodic_memory import EpisodicMemory
            em = EpisodicMemory(openid)
            today = datetime.now().strftime('%Y-%m-%d')
            existing = em.get_by_date(today)
            if not existing:
                signals['need_consolidation'] = True
        except Exception:
            pass

    # 检查是否需要周整合 (周日深夜)
    if hour >= 23 or hour < 2:
        if datetime.now().weekday() == 6:  # 周日
            signals['need_weekly'] = True

    # 检查用户沉默天数
    try:
        from working_memory import get_working_memory
        wm = get_working_memory()
        if wm:
            recent = wm.recent(openid, n=1)
            if recent:
                last = recent[0].get('timestamp', '')
                if last:
                    last_dt = datetime.fromisoformat(last)
                    signals['user_silent_days'] = (datetime.now() - last_dt).days
    except Exception:
        pass

    return signals


# ============ Phase 2: Reason (推理) ============

def reason(openid: str, profile: dict, signals: dict) -> list:
    """推理并生成行动清单（按优先级排序）"""
    actions = []
    hour = signals['hour']

    # 优先级1: 异常检测 → 立即告警
    try:
        from behavior_predictor import BehaviorPredictor
        bp = BehaviorPredictor()
        anomaly = bp.anomaly_score(openid)
        if anomaly > 0.8:
            actions.append({
                'priority': 1,
                'type': 'alert',
                'name': 'anomaly_detected',
                'reason': f'异常指数{anomaly:.0%}',
                'handler': '_do_anomaly_alert',
            })
    except Exception:
        pass

    # 优先级2: 睡前整理
    if signals.get('need_consolidation'):
        actions.append({
            'priority': 2,
            'type': 'consolidate',
            'name': 'sleep_consolidation',
            'reason': '睡前记忆整理',
            'handler': '_do_consolidation',
        })

    # 优先级3: 周整合
    if signals.get('need_weekly'):
        actions.append({
            'priority': 3,
            'type': 'weekly',
            'name': 'weekly_integration',
            'reason': '周记忆整合',
            'handler': '_do_weekly',
        })

    # 优先级4: 推送窗口
    if signals.get('push_window'):
        # 检查是否已推送过
        actions.append({
            'priority': 4,
            'type': 'push',
            'name': f'{signals["push_window"]}_push',
            'reason': f'{signals["push_window"]}推送窗口',
            'handler': '_do_push',
        })

    # 优先级5: 用户沉默 >3天 → 关怀消息
    if signals.get('user_silent_days', 0) >= 3:
        actions.append({
            'priority': 5,
            'type': 'care',
            'name': 'silence_care',
            'reason': f'沉默{signals["user_silent_days"]}天',
            'handler': '_do_care',
        })

    actions.sort(key=lambda a: a['priority'])
    return actions


# ============ Phase 3: Act (执行) ============

def execute(action: dict, openid: str, profile: dict) -> dict:
    """执行一个行动"""
    handler_name = action['handler']
    result = {'action': action['name'], 'status': 'error', 'detail': ''}

    try:
        if handler_name == '_do_anomaly_alert':
            from push_enhancer import generate_alert_content
            alert = generate_alert_content(openid, profile, 'anomaly_detected', action.get('extra'))
            if alert:
                result['status'] = 'alert_generated'
                result['title'] = alert[0]
                result['content'] = alert[1]

        elif handler_name == '_do_consolidation':
            from memory_integrator import sleep_consolidate
            r = sleep_consolidate(openid)
            result['status'] = r.get('status', 'done')
            result['detail'] = f'consolidated: {r.get("date", "?")}'

        elif handler_name == '_do_weekly':
            from memory_integrator import weekly_integrate
            r = weekly_integrate(openid)
            result['status'] = r.get('status', 'done')
            result['detail'] = f'patterns={r.get("patterns")}, triggers={r.get("triggers")}'

        elif handler_name == '_do_push':
            win = action['name'].replace('_push', '')
            try:
                from scheduler_daemon import _process_user
                processed, info = _process_user(openid, profile)
                result['status'] = 'done' if processed else 'skipped'
                result['detail'] = info
            except Exception:
                from push_enhancer import push_morning, push_evening
                if win == 'morning':
                    success = push_morning(openid, profile)
                else:
                    success = push_evening(openid, profile)
                result['status'] = 'sent' if success else 'failed'

        elif handler_name == '_do_care':
            from push_enhancer import generate_alert_content
            alert = generate_alert_content(openid, profile, 'score_drop', {'days': action.get('reason', '')})
            if alert:
                result['status'] = 'care_generated'
                result['title'] = alert[0]
                result['content'] = alert[1]
            else:
                result['status'] = 'no_content'

    except Exception as e:
        result['status'] = 'error'
        result['detail'] = str(e)
        _log.warning('[Agent] Execute error for %s: %s', openid[:8], e)

    return result


# ============ Phase 4: Learn (学习) ============

def learn(openid: str, action_result: dict):
    """从行动结果学习"""
    mem = _load_agent_memory()
    entry = {
        'openid': openid,
        'action': action_result.get('action'),
        'status': action_result.get('status'),
        'timestamp': datetime.now().isoformat(),
    }
    mem['learned'].append(entry)
    mem['learned'] = mem['learned'][-100:]  # 只保留最近100条
    _save_agent_memory(mem)

    # 决策审计 trace（异步无阻塞）
    try:
        from decision_auditor import trace as da_trace
        da_trace(
            openid=openid,
            decision_id=f'{openid}_{int(time.time())}',
            decision_type=entry['action'] or 'unknown',
            context={'status': action_result.get('status', ''),
                     'detail': str(action_result.get('detail', ''))[:200]},
            predicted_impact=0.0,
            confidence=0.5,
        )
    except Exception:
        pass


# ============ Main Loop ============

def agent_cycle():
    """一次Agent循环: Perceive → Reason → Act → Learn"""
    mem = _load_agent_memory()
    mem['cycles'] += 1
    mem['last_run'] = datetime.now().isoformat()

    users = get_active_users()
    if not users:
        _log.info('[Agent] No active users, skip cycle %d', mem['cycles'])
        return {'status': 'no_users', 'cycle': mem['cycles']}

    results = []
    for openid, profile in users:
        try:
            # Perceive
            signals = perceive(openid)

            # Reason
            actions = reason(openid, profile, signals)

            # Act
            for action in actions:
                result = execute(action, openid, profile)
                result['action'] = action['name']
                result['priority'] = action['priority']
                results.append(result)

                # Learn
                learn(openid, result)

                _log.info('[Agent] %s -> %s (%s)', action['name'], result['status'], openid[:8])

        except Exception as e:
            _log.warning('[Agent] Cycle error for %s: %s', openid[:8], e)

    _save_agent_memory(mem)

    return {
        'status': 'done',
        'cycle': mem['cycles'],
        'users': len(users),
        'actions_executed': len(results),
        'results': results,
    }


def start_agent_loop():
    """启动Agent自主循环（替换scheduler_daemon的旧循环）"""
    import threading
    SCAN_INTERVAL = 300  # 5分钟

    def _loop():
        _log.info('[Agent] Agent loop started (interval=%ds)', SCAN_INTERVAL)
        while True:
            try:
                agent_cycle()
            except Exception as e:
                _log.warning('[Agent] Loop error: %s', e)
            time.sleep(SCAN_INTERVAL)

    t = threading.Thread(target=_loop, daemon=True, name='agent-perceptor')
    t.start()
    _log.info('[Agent] Agent thread started')
    return t
