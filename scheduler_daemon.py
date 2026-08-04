#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scheduler_daemon.py — AISleepGen 后台调度守护线程

职责:
  1. 每 N 分钟扫描所有活跃用户（3+记录）
  2. 预测今晚睡眠质量
  3. 如果预测差 -> 生成推送内容 -> 通过微信服务通知发送
  4. 清理过期推送

运行方式：由 asyncio_server.py 启动时拉起线程
v2.3: 新增微信服务通知推送 + 内容智能生成
"""

import os
import json
import time
import threading
import logging
from datetime import datetime, timedelta

# 稳态回路集成：读取信号板而非重新扫描profile
try:
    from homeostatic_circuit import signal_board as _ho_board, get_circuit_context
    _HAS_HOMEOSTATIC = True
except ImportError:
    _HAS_HOMEOSTATIC = False

# 跨模块工具函数
from push_decision import _get_delay_to_next_slot

_log = logging.getLogger('aisleepgen.scheduler')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PUSH_QUEUE_PATH = os.path.join(PROJECT_ROOT, 'data', 'push_queue.json')
PUSH_LOG_PATH = os.path.join(PROJECT_ROOT, 'data', 'push_log.json')
PUSH_LOCK = threading.Lock()

# ===== 扫描参数 =====
SCAN_INTERVAL = 300  # 5 分钟扫描一次
MIN_HISTORY_FOR_PREDICT = 3  # 至少 3 条历史才能预测
PUSH_COOLDOWN_HOURS = 24  # 同一用户 24h 内不重复推送
PUSH_EXPIRE_HOURS = 48  # 推送 48h 过期

# 时段推送参数
PUSH_MORNING_HOURS = (7, 9)    # 早上 7-9 点：日回顾
PUSH_EVENING_HOURS = (20, 22)  # 晚上 8-10 点：睡前关怀

# 不同策略的冷却时间不同
STRATEGY_COOLDOWN = {
    'fixed_schedule': 48,
    'wind_down': 24,
    'deep_breathing': 12,
    'sleep_hygiene': 48,
    'pain_relief': 24,
    'bedtime_earlier': 24,
}


def _load_push_queue():
    """加载推送队列"""
    try:
        if os.path.exists(PUSH_QUEUE_PATH):
            with open(PUSH_QUEUE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        _log.warning('[Scheduler] Failed to load push queue: %s', e)
    return []


def _save_push_queue(queue):
    """保存推送队列"""
    try:
        os.makedirs(os.path.dirname(PUSH_QUEUE_PATH), exist_ok=True)
        with open(PUSH_QUEUE_PATH, 'w', encoding='utf-8') as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _log.warning('[Scheduler] Failed to save push queue: %s', e)


def _get_active_users(min_records=3):
    """获取活跃用户列表"""
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


def _check_time_window():
    """检查当前是否在推送时段内

    Returns:
        'morning' | 'evening' | None
    """
    hour = datetime.now().hour
    if PUSH_MORNING_HOURS[0] <= hour < PUSH_MORNING_HOURS[1]:
        return 'morning'
    if PUSH_EVENING_HOURS[0] <= hour < PUSH_EVENING_HOURS[1]:
        return 'evening'
    return None


def _generate_push_entry(openid, profile, strategy_name, strategy_desc, prediction):
    """生成推送条目（含智能内容）

    Args:
        openid: 用户ID
        profile: 用户画像
        strategy_name: 调度器选择的策略名
        strategy_desc: 策略描述
        prediction: 预测结果

    Returns:
        dict or None
    """
    from wechat_push import generate_push_content, get_cooldown_hours

    # 生成推送内容
    result = generate_push_content(profile, strategy_name, strategy_desc, prediction)
    if result is None:
        return None

    title, content, push_type = result

    # 检查冷却
    queue = _load_push_queue()
    for entry in queue:
        if entry.get('openid') == openid and entry.get('push_type') == push_type:
            pushed_at = entry.get('pushed_at', 0)
            cd = get_cooldown_hours(push_type)
            if time.time() - pushed_at < cd * 3600:
                return None  # 冷却中

    now = time.time()
    return {
        'id': f'{openid}_{int(now)}',
        'openid': openid,
        'title': title,
        'content': content,
        'push_type': push_type,
        'strategy': strategy_name,
        'reason': f'pred={prediction.get("predicted_score", 0):.0f}' if prediction else '',
        'pushed_at': now,
        'expires_at': now + PUSH_EXPIRE_HOURS * 3600,
        'sent': False,
        'send_result': None,
    }


def _try_send_push_entry(entry):
    """尝试通过微信服务通知发送推送"""
    from wechat_push import send_subscribe_message

    template_id = ''  # 可配置
    result = send_subscribe_message(
        entry['openid'],
        template_id,
        {
            'thing1': entry.get('title', ''),
            'thing2': entry.get('content', ''),
        },
        page='pages/index/index',
    )
    return result


def _scan_emotion_triggers(users):
    """扫描用户的情绪触发条件（备用通道——基于稳态回路信号）"""
    if not _HAS_HOMEOSTATIC:
        # 旧路径：直接读profile
        return _scan_emotion_triggers_legacy(users)

    for openid, profile in users:
        try:
            ctx = get_circuit_context(openid)
            signals = ctx.get('signals', {})

            # 读取稳态回路的信号
            inactive_days = ctx.get('inactive_days', 0)
            recovery_status = ctx.get('recovery_status')
            anxiety_risk = ctx.get('anxiety_risk', False)

            # 只有信号积累到足够强烈 + 冷却允许才行动
            if not ctx.get('push_cooldown_ok', True):
                continue

            if inactive_days >= 2 and recovery_status in ('insufficient', 'at_risk'):
                from push_decision import decide_interaction, queue_delayed_push
                decision = decide_interaction(openid, 'inactive', {'days': inactive_days}, profile)
                if decision['action'] == 'delay_push':
                    queue_delayed_push(openid, decision.get('title', ''), decision.get('content', ''),
                                       reason=decision['detail'], delay_hours=decision.get('delay_hours', 8))
                    _log.info('[Scheduler] HO-driven inactive push for %s (%dd, status=%s)',
                              openid[:8], inactive_days, recovery_status)
        except Exception as e:
            _log.warning('[Scheduler] HO emotion scan error for %s: %s', openid[:8], e)


def _scan_emotion_triggers_legacy(users):
    """旧路径：直接读profile（无稳态回路时使用）"""
    from push_decision import decide_interaction, _get_last_active_days, queue_delayed_push

    for openid, profile in users:
        try:
            inactive_days = _get_last_active_days(profile)
            if inactive_days >= 2:
                decision = decide_interaction(openid, 'inactive', {'days': inactive_days}, profile)
                if decision['action'] == 'delay_push':
                    queue_delayed_push(openid, decision.get('title', ''), decision.get('content', ''),
                                       reason=decision['detail'], delay_hours=decision.get('delay_hours', 8))
                    _log.info('[Scheduler] Legacy inactive push for %s (%dd)', openid[:8], inactive_days)
        except Exception as e:
            _log.warning('[Scheduler] Legacy emotion scan error for %s: %s', openid[:8], e)


def _process_user(openid, profile):
    """处理单个用户：增强推送 + 旧版fallback

    Returns:
        (processed: bool, info: str)
    """
    from prediction_engine import predict_tonight
    from intervention_scheduler import schedule_intervention

    time_window = _check_time_window()

    # 优先使用增强推送引擎
    if time_window:
        try:
            from push_enhancer import push_morning, push_evening
            if time_window == 'morning':
                result = push_morning(openid, profile)
            else:
                result = push_evening(openid, profile)

            action = 'push_enhanced' if result else 'fallback'
            if result:
                _log.info('[Scheduler] Enhanced push sent to %s (%s)', openid[:8], time_window)
                return True, f'{action}: {time_window}'
        except ImportError:
            pass  # 无 push_enhancer 时走旧路径
        except Exception as e:
            _log.warning('[Scheduler] Enhanced push error for %s: %s', openid[:8], e)

    # 旧路径：使用 prediction_engine
    history = profile.get('history', [])
    if not isinstance(history, list):
        return False, 'no history'

    # 提取评分记录
    records = []
    for h in history:
        if not isinstance(h, dict):
            continue
        score = h.get('wm_score') or h.get('score')
        if score and isinstance(score, (int, float)):
            records.append({'score': score})

    if len(records) < MIN_HISTORY_FOR_PREDICT:
        return False, 'insufficient records'

    # 预测
    prediction = predict_tonight(profile, openid=openid)
    if prediction is None:
        return False, 'no prediction'

    predicted_score = prediction.get('predicted_score', 0)

    # 检查是否在推送时段
    time_window = _check_time_window()
    is_alert = predicted_score < 50  # 严重偏低时不分时段推

    if not time_window and not is_alert:
        return False, f'outside push window, score={predicted_score:.0f}'

    # 仅在以下情况推送：
    # 1. 早上时段：回顾昨日评分（不加分限制）
    # 2. 晚间时段：预测 < 65 分
    # 3. 任何时候：预测 < 50 分（异常提醒）
    should_push = False
    if time_window == 'morning':
        should_push = True  # 早上回顾，有数据就推
    elif time_window == 'evening' and predicted_score < 65:
        should_push = True
    elif is_alert:
        should_push = True

    if not should_push:
        return False, f'no need, score={predicted_score:.0f}'

    # 获取干预策略
    scheduled, intervention_info = schedule_intervention(profile, {'total_score': predicted_score})
    strategy_name = ''
    strategy_desc = ''
    if scheduled and isinstance(intervention_info, dict):
        strategy_name = intervention_info.get('name', '')
        strategy_desc = intervention_info.get('desc', '')

    # 生成推送内容
    entry = _generate_push_entry(openid, profile, strategy_name, strategy_desc, prediction)
    if entry is None:
        return False, 'cooldown or no content'

    # 尝试发送微信推送
    send_result = _try_send_push_entry(entry)
    entry['sent'] = send_result.get('success', False)
    entry['send_result'] = send_result.get('errmsg', '')

    # 保存到队列（无论是否成功发送，都写入队列供小程序轮询）
    with PUSH_LOCK:
        queue = _load_push_queue()
        queue.append(entry)
        _save_push_queue(queue)

    if send_result.get('success'):
        _log.info('[Scheduler] WeChat push sent to %s: %s', openid[:8], entry.get('title', '')[:40])
    else:
        _log.info('[Scheduler] Push queued for %s (no WX config): %s', openid[:8], entry.get('title', '')[:40])

    return True, f'pushed: {strategy_name or "general"}'


def _cleanup_expired():
    """清理过期推送"""
    queue = _load_push_queue()
    now = time.time()
    before = len(queue)
    queue = [e for e in queue if e.get('expires_at', 0) > now]
    if len(queue) < before:
        with PUSH_LOCK:
            _save_push_queue(queue)
            _log.info('[Scheduler] Cleaned %d expired pushes', before - len(queue))


def _scheduler_loop():
    """调度器主循环（决策引擎驱动）"""
    _log.info('[Scheduler] Daemon started (interval=%ds) — decision engine mode', SCAN_INTERVAL)
    while True:
        try:
            _cleanup_expired()

            # 1. 处理延迟推送队列（决策引擎的定时触发）
            try:
                from push_decision import process_delayed_queue
                processed = process_delayed_queue()
                if processed > 0:
                    _log.info('[Scheduler] Processed %d delayed pushes', processed)
            except Exception as e:
                _log.warning('[Scheduler] Delayed queue error: %s', e)

            users = _get_active_users()
            _log.info('[Scheduler] Scanning %d active users', len(users))

            # 2. 定时扫描：读取稳态回路信号 + 调用决策引擎
            processed = 0
            for openid, profile in users:
                try:
                    # 优先从稳态回路读取信号（如果可用）
                    ho_signals = {}
                    ho_recovery = None
                    ho_suggested = None
                    if _HAS_HOMEOSTATIC:
                        try:
                            ctx = get_circuit_context(openid)
                            ho_signals = ctx.get('signals', {})
                            ho_recovery = ctx.get('recovery_status')
                            ho_suggested = ctx.get('suggested_mode')
                        except Exception:
                            pass

                    # 只在冷却允许 + 信号足够强烈时才由稳态回路触发
                    push_cooldown_ok = ho_signals.get('push_cooldown_expired', True)

                    if _HAS_HOMEOSTATIC and ho_recovery in ('insufficient', 'at_risk') and push_cooldown_ok:
                        # 稳态回路积累的信号足够强，触发干预回路
                        from push_decision import execute_push, queue_delayed_push
                        recovery_score = ho_signals.get('recovery_score', 40)
                        suggested_mode = ho_suggested

                        if suggested_mode == 'coach':
                            title = f'💙 睡眠改善提醒'
                            content = f'近期睡眠质量评估偏低（{recovery_score}分），建议今晚尝试早睡，做放松练习。'
                            queue_delayed_push(openid, title, content, reason=f'HO_recovery={ho_recovery}',
                                               delay_hours=_get_delay_to_next_slot('evening'))
                            processed += 1
                            _log.info('[Scheduler] HO-driven coach push for %s (score=%d, status=%s)',
                                      openid[:8], recovery_score, ho_recovery)
                        elif suggested_mode in ('companion', 'chat'):
                            title = f'🧘 需要放松一下吗？'
                            content = f'看起来最近状态不太好。试试深呼吸练习，或者和我聊聊。'
                            queue_delayed_push(openid, title, content, reason=f'HO_suggested={suggested_mode}',
                                               delay_hours=_get_delay_to_next_slot('evening'))
                            processed += 1
                            _log.info('[Scheduler] HO-driven companion push for %s (status=%s)',
                                      openid[:8], ho_recovery)
                    else:
                        # 无稳态回路信号或冷却中：走旧路径
                        from push_decision import decide_interaction, queue_delayed_push, execute_push
                        decision = decide_interaction(openid, 'periodic_scan', {}, profile)
                        if decision['action'] == 'push_now':
                            execute_push(openid, decision.get('title', ''), decision.get('content', ''))
                            processed += 1
                            _log.info('[Scheduler] Periodic push for %s: %s', openid[:8], decision['detail'][:40])
                        elif decision['action'] == 'delay_push':
                            queue_delayed_push(openid, decision.get('title', ''), decision.get('content', ''),
                                               reason=decision['detail'], delay_hours=decision.get('delay_hours', 8))
                            processed += 1
                except Exception as e:
                    import traceback
                    _log.warning('[Scheduler] Error for %s: %s\n%s', openid[:8], e, traceback.format_exc()[-300:])

            # 3. 教练提醒扫描
            try:
                from sleep_coach import get_scheduled_reminders
                for openid, profile in users:
                    reminders = get_scheduled_reminders(openid, profile)
                    for r in reminders:
                        from push_decision import queue_delayed_push
                        queue_delayed_push(openid, r['title'], r['body'],
                                           reason=r['type'], delay_hours=0)
                        processed += 1
                        _log.info('[Coach] Reminder for %s: %s', openid[:8], r['title'][:30])
            except ImportError:
                pass  # sleep_coach 模块尚未部署
            except Exception as e:
                _log.warning('[Scheduler] Coach scan error: %s', e)

            # 4. 情绪扫描（备用，主触发走 handle_chat）
            try:
                _scan_emotion_triggers(users)
            except Exception as e:
                _log.warning('[Scheduler] Emotion scan error: %s', e)

            # 5. 主动健康管理 (v6.5.0)
            try:
                from proactive_manager import get_proactive_manager
                pm = get_proactive_manager()
                proactive_processed = 0
                for openid, profile in users:
                    pending = pm.evaluate_triggers(openid)
                    for trigger in pending:
                        # 检查今日是否已达推送上限
                        if not pm.check_daily_limit(openid):
                            _log.info('[Proactive] Daily limit reached for %s, skipping', openid[:8])
                            continue

                        message = pm.execute_trigger(openid, trigger)
                        _log.info('[Proactive] Triggered %s for %s: %s',
                                  trigger['name'], openid[:8], message[:40])

                        # 通过推送队列发送
                        entry = {
                            'id': f'{openid}_proactive_{int(time.time())}',
                            'openid': openid,
                            'title': message.split('：')[0][:40],
                            'content': message.split('：')[1] if '：' in message else message,
                            'push_type': 'proactive',
                            'strategy': trigger['name'],
                            'reason': trigger['name'],
                            'pushed_at': time.time(),
                            'expires_at': time.time() + PUSH_EXPIRE_HOURS * 3600,
                            'sent': False,
                            'send_result': None,
                        }
                        with PUSH_LOCK:
                            queue = _load_push_queue()
                            queue.append(entry)
                            _save_push_queue(queue)

                        proactive_processed += 1

                if proactive_processed > 0:
                    _log.info('[Proactive] %d proactive triggers executed', proactive_processed)
            except ImportError:
                pass  # proactive_manager 可选模块
            except Exception as e:
                _log.warning('[Proactive] Scan error: %s', e)

            # 6. 元学习每日审查（每天深夜执行一次）
            try:
                from meta_learner import MetaLearner
                meta = MetaLearner()
                now = time.time()
                hour = datetime.now().hour
                last_review = getattr(_scheduler_loop, '_last_meta_review', 0)
                # 23:00~02:00 之间且距上次审查>12小时
                if (hour >= 23 or hour < 3) and (now - last_review) > 43200:
                    _log.info('[Scheduler] Starting meta-learner review...')
                    result = meta.daily_review()
                    _scheduler_loop._last_meta_review = now
                    n_adj = len(result.get('adjustments', []))
                    if n_adj > 0:
                        _log.info('[Scheduler] Meta review: %d adjustments applied', n_adj)
            except ImportError:
                pass
            except Exception as e:
                _log.warning('[Scheduler] Meta review error: %s', e)

            if processed > 0:
                _log.info('[Scheduler] Processed %d interventions this cycle', processed)

        except Exception as e:
            _log.warning('[Scheduler] Loop error: %s', e)

        time.sleep(SCAN_INTERVAL)


def start_daemon():
    """启动守护线程，由 asyncio_server.py 调用"""
    t = threading.Thread(target=_scheduler_loop, daemon=True, name='scheduler-daemon')
    t.start()
    _log.info('[Scheduler] Daemon thread started')
    return t


# ===== API 接口（供 dp_router 调用） =====

def get_pending_pushes(openid):
    """获取用户待处理的推送"""
    queue = _load_push_queue()
    now = time.time()
    pushes = []
    for entry in queue:
        if entry.get('openid') == openid and not entry.get('read') and entry.get('expires_at', 0) > now:
            pushes.append({
                'id': entry.get('id'),
                'title': entry.get('title'),
                'content': entry.get('content'),
                'push_type': entry.get('push_type'),
                'pushed_at': entry.get('pushed_at'),
                'strategy': entry.get('strategy'),
            })
    return pushes


def mark_push_read(push_id=None, openid=None):
    """标记推送为已读"""
    queue = _load_push_queue()
    changed = False
    for entry in queue:
        if push_id and entry.get('id') == push_id:
            if not entry.get('read'):
                entry['read'] = True
                changed = True
            break
        elif openid and entry.get('openid') == openid and not entry.get('read'):
            entry['read'] = True
            changed = True
    if changed:
        with PUSH_LOCK:
            _save_push_queue(queue)
    return changed


def mark_push_accepted(push_id):
    """标记推送为已接受"""
    queue = _load_push_queue()
    changed = False
    for entry in queue:
        if entry.get('id') == push_id:
            entry['accepted'] = True
            entry['read'] = True
            changed = True
            break
    if changed:
        with PUSH_LOCK:
            _save_push_queue(queue)
    return changed


# ===== 自测 =====
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    q = get_pending_pushes('test_user')
    print('Empty queue:', q)
    time_window = _check_time_window()
    print(f'Current time window: {time_window}')
    print('OK')

# ============================================================
# 世界模型定时触发 (由 scheduler_daemon 驱动)
# ============================================================

def trigger_world_model_cycle(openid: str = "default",
                               hr: float = None,
                               stress: int = None):
    """
    由调度器定时触发世界模型闭环

    安装方式:
      - 在定时任务中调用 trigger_world_model_cycle(openid, hr, stress)
      - 不阻塞主调度循环
    """
    try:
        from world_model_coordinator import get_coordinator
        coord = get_coordinator(openid)
        coord.step(hr=hr, stress=stress)
    except ImportError:
        pass  # coordinator 未部署时不报错
    except Exception:
        import traceback; traceback.print_exc()


def schedule_world_model_cycle(scheduler, interval_min: int = 15):
    """
    注册一个定时世界模型闭环任务

    Args:
        scheduler: scheduler_daemon 的调度器实例
        interval_min: 执行间隔 (分钟)
    """
    try:
        from world_model_coordinator import get_coordinator
        scheduler.add_job(
            func=lambda: get_coordinator("default").step(),
            trigger='interval',
            minutes=interval_min,
            id='world_model_cycle',
            replace_existing=True,
        )
        return True
    except Exception:
        return False
