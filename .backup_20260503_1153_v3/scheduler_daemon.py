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
    """扫描用户的情绪触发条件，产生推送队列条目

    1. 从 profile 取出 emotion_summary
    2. 调用 emotion_monitor.get_emotion_trigger()
    3. 有触发时生成推送内容并写入队列（如果不在冷却中）
    """
    from emotion_monitor import get_emotion_trigger, generate_emotion_push_content

    for openid, profile in users:
        try:
            trigger = get_emotion_trigger(profile)
            if trigger is None:
                continue

            # 检查冷却：同用户同类型 12h 内不重复
            queue = _load_push_queue()
            in_cooldown = False
            for entry in queue:
                if (entry.get('openid') == openid
                        and entry.get('push_type') == 'emotion_care'
                        and not entry.get('read')):
                    in_cooldown = True
                    break
            if in_cooldown:
                continue

            content = generate_emotion_push_content(trigger, profile)
            if content is None:
                continue

            now = time.time()
            entry = {
                'id': f'{openid}_emo_scan_{int(now)}',
                'openid': openid,
                'title': content[0],
                'content': content[1],
                'push_type': 'emotion_care',
                'strategy': 'emotion_monitor',
                'reason': trigger['trigger_type'] + '/' + trigger['severity'],
                'pushed_at': now,
                'expires_at': now + PUSH_EXPIRE_HOURS * 3600,
                'sent': False,
                'read': False,
            }
            # 尝试微信发送
            send_result = _try_send_push_entry(entry)
            entry['sent'] = send_result.get('success', False)
            entry['send_result'] = send_result.get('errmsg', '')

            with PUSH_LOCK:
                queue = _load_push_queue()
                queue.append(entry)
                _save_push_queue(queue)

            _log.info('[Scheduler] Emotion push for %s: %s (severity=%s)',
                      openid[:8], trigger['trigger_type'], trigger['severity'])
        except Exception as e:
            import traceback
            _log.warning('[Scheduler] Emotion scan error for %s: %s', openid[:8], e)


def _process_user(openid, profile):
    """处理单个用户：预测+生成推送+发送

    Returns:
        (processed: bool, info: str)
    """
    from prediction_engine import predict_tonight
    from intervention_scheduler import schedule_intervention

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
    prediction = predict_tonight(profile)
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
    """调度器主循环（含情绪扫描）"""
    _log.info('[Scheduler] Daemon started (interval=%ds)', SCAN_INTERVAL)
    while True:
        try:
            _cleanup_expired()

            users = _get_active_users()
            _log.info('[Scheduler] Scanning %d active users', len(users))

            # 情绪推送扫描（新增）
            try:
                _scan_emotion_triggers(users)
            except Exception as e:
                _log.warning('[Scheduler] Emotion scan error: %s', e)

            processed = 0
            for openid, profile in users:
                try:
                    ok, info = _process_user(openid, profile)
                    if ok:
                        processed += 1
                        _log.info('[Scheduler] Processed %s: %s', openid[:8], info)
                except Exception as e:
                    import traceback
                    _log.warning('[Scheduler] Error for %s: %s\n%s', openid[:8], e, traceback.format_exc()[-500:])

            if processed > 0:
                _log.info('[Scheduler] Processed %d users this cycle', processed)

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
