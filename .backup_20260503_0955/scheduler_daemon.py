#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scheduler_daemon.py — AISleepGen 后台调度守护线程

职责：
  1. 每 N 分钟扫描所有活跃用户（3+记录）
  2. 预测今晚睡眠质量
  3. 如需干预且 24h 内未推送 → 写入推送队列
  4. 清理过期推送

运行方式：由 asyncio_server.py 启动时启动独立线程
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
PUSH_LOCK = threading.Lock()

# ===== 扫描配置 =====
SCAN_INTERVAL = 300  # 5 分钟扫描一次
MIN_HISTORY_FOR_PREDICT = 3  # 至少 3 条历史才做预测
PUSH_COOLDOWN_HOURS = 24  # 同一用户 24h 内不重复推送
PUSH_EXPIRE_HOURS = 48  # 推送 48h 后过期

# 各干预策略的冷却时间不同
STRATEGY_COOLDOWN = {
    'fixed_schedule': 48,   # 固定作息 → 2天冷却
    'wind_down': 24,        # 放松仪式 → 1天
    'deep_breathing': 12,   # 深呼吸 → 12小时
    'sleep_hygiene': 48,    # 睡眠卫生 → 2天
    'pain_relief': 24,      # 疼痛舒缓 → 1天
    'bedtime_earlier': 24,  # 提前入睡 → 1天
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
    """获取所有有足够历史记录的用户"""
    from profile_storage import _load_all_profiles
    profiles = _load_all_profiles()
    active = []
    now = time.time()
    for openid, profile in profiles.items():
        history = profile.get('history', [])
        if len(history) >= min_records:
            # 检查最近 7 天内有活动
            recent = [h for h in history if isinstance(h, dict) and h.get('timestamp', '')[:10] >= (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')]
            if recent:
                active.append((openid, profile))
    return active


def _predict_and_schedule(openid, profile):
    """对单个用户运行预测，如需干预则写入推送队列

    返回: (scheduled: bool, intervention_name: str or None)
    """
    if not isinstance(profile, dict):
        _log.warning('[Scheduler] Invalid profile type for %s: %s', openid[:8], type(profile).__name__)
        return False, None

    from prediction_engine import predict_tonight
    from intervention_scheduler import schedule_intervention
    history = profile.get('history', [])
    if not isinstance(history, list):
        _log.warning('[Scheduler] Non-list history for %s', openid[:8])
        return False, None

    # 提取评分记录（过滤非 dict 元素）
    records = []
    for h in history:
        if not isinstance(h, dict):
            continue
        score = h.get('wm_score') or h.get('score')
        if score and isinstance(score, (int, float)):
            records.append({'score': score})

    if len(records) < MIN_HISTORY_FOR_PREDICT:
        return False, None

    prediction = predict_tonight(profile)
    if prediction is None:
        return False, None

    predicted_score = prediction.get('predicted_score', 0)
    if predicted_score >= 60:
        return False, None  # 预测正常，不需要干预

    # 直接让 intervention_scheduler 处理选策略
    scheduled, intervention_info = schedule_intervention(profile, {'total_score': predicted_score})
    if not scheduled or not intervention_info:
        return False, None

    strategy_name = intervention_info.get('name') if isinstance(intervention_info, dict) else intervention_info
    strategy_desc = ''
    if isinstance(intervention_info, dict):
        strategy_desc = intervention_info.get('desc', '')

    # 冷却检查：同用户同策略 24h 内不重复
    queue = _load_push_queue()
    for entry in queue:
        if entry.get('openid') == openid and entry.get('name') == strategy_name:
            pushed_at = entry.get('pushed_at', 0)
            cd = STRATEGY_COOLDOWN.get(strategy_name, PUSH_COOLDOWN_HOURS)
            if time.time() - pushed_at < cd * 3600:
                return False, f'{strategy_name} cooldown ({cd}h)'

    # 写入推送队列
    entry = {
        'id': f'{openid}_{int(time.time())}',
        'openid': openid,
        'name': strategy_name,
        'desc': strategy_desc,
        'reason': f'预测评分={predicted_score:.0f}',
        'pushed_at': time.time(),
        'expires_at': time.time() + PUSH_EXPIRE_HOURS * 3600,
        'read': False,
        'accepted': False,
    }
    with PUSH_LOCK:
        queue.append(entry)
        _save_push_queue(queue)

    _log.info('[Scheduler] Pushed %s for %s (pred=%d)', strategy_name, openid[:8], predicted_score)
    return True, strategy_name


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
    """调度器主循环"""
    _log.info('[Scheduler] Daemon started (interval=%ds)', SCAN_INTERVAL)
    while True:
        try:
            # 清理过期
            _cleanup_expired()

            # 获取活跃用户
            users = _get_active_users()
            _log.info('[Scheduler] Scanning %d active users', len(users))

            scheduled = 0
            for openid, profile in users:
                try:
                    ok, name = _predict_and_schedule(openid, profile)
                    if ok:
                        scheduled += 1
                except Exception as e:
                    import traceback
                    _log.warning('[Scheduler] Error for %s: %s\n%s', openid[:8], e, traceback.format_exc()[-500:])

            if scheduled > 0:
                _log.info('[Scheduler] Scheduled %d interventions', scheduled)

        except Exception as e:
            _log.warning('[Scheduler] Loop error: %s', e)

        time.sleep(SCAN_INTERVAL)


def start_daemon():
    """启动调度守护线程（由 asyncio_server.py 调用）"""
    t = threading.Thread(target=_scheduler_loop, daemon=True, name='scheduler-daemon')
    t.start()
    _log.info('[Scheduler] Daemon thread started')
    return t


# ===== API 接口函数（由 dp_router 调用） =====

def get_pending_pushes(openid):
    """获取用户待处理的推送

    返回: list[dict] — 未读的推送条目
    """
    queue = _load_push_queue()
    now = time.time()
    pushes = []
    for entry in queue:
        if entry.get('openid') == openid and not entry.get('read') and entry.get('expires_at', 0) > now:
            pushes.append({
                'id': entry.get('id'),
                'name': entry.get('name'),
                'desc': entry.get('desc'),
                'reason': entry.get('reason'),
                'pushed_at': entry.get('pushed_at'),
            })
    return pushes


def mark_push_read(push_id=None, openid=None):
    """标记推送为已读

    如果 push_id 为 None，标记该用户所有推送为已读
    """
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
    """标记推送为已接受（用户照做了）"""
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


# ===== 独立测试 =====
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # 测试队列操作
    q = get_pending_pushes('test_user')
    print('Empty queue:', q)
    print('OK')
