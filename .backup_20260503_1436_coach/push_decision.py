#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push_decision.py — AISleepGen 推送决策引擎

单一决策入口，统一处理所有推送场景。

职责:
  1. 接收各种事件（聊天情绪/评分更新/不活跃/定时扫描）
  2. 判断是否干预、何时干预、如何干预
  3. 防骚扰合并（同用户24h内最多1次干预）
  4. 输出决策结果（立即推送/延迟推送/随聊天融入/不干预）

使用:
  from push_decision import decide_intervention, record_intervention
"""

import time
import json
import logging
from datetime import datetime, timedelta

_log = logging.getLogger('aisleepgen.push_decision')

# ===== 常数 =====
MIN_INTERVAL_HOURS = 20      # 同一用户最小推送间隔（小时）
INACTIVE_DAYS_THRESHOLD = 2  # 超过N天不活跃触发关怀
DELAY_PUSH_MAX = 18          # 延迟推送最大等待小时数（避免跨太多天）
DELAY_QUEUE_PATH = None      # 延迟推送队列路径（由 _init_paths 设置）

# 延迟推送的时间槽配置（"凌晨检测到的问题，延迟到早上推"）
DELAY_SLOTS = {
    'morning': (6, 9),       # 早6-9点发：适合不活跃/昨日回顾
    'evening': (19, 22),     # 晚7-10点发：适合睡前关怀/情绪关怀
}

# 干预方式权重
_IN_CHAT_EMOTION_THRESHOLD = -1.0  # 聊天中情绪低于此值，才在回复融入关怀
_IN_CHAT_MIN_WORDS = 15            # 回复至少需要这么多字才能嵌入关怀


def _init_paths():
    """延迟初始化路径"""
    global DELAY_QUEUE_PATH
    if DELAY_QUEUE_PATH is None:
        import os
        from scheduler_daemon import PROJECT_ROOT
        DELAY_QUEUE_PATH = os.path.join(PROJECT_ROOT, 'data', 'delay_push_queue.json')


def _load_delay_queue():
    """加载延迟推送队列"""
    _init_paths()
    try:
        import os, json
        if os.path.exists(DELAY_QUEUE_PATH):
            with open(DELAY_QUEUE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        _log.warning('[Decision] Failed to load delay queue: %s', e)
    return []


def _save_delay_queue(queue):
    """保存延迟推送队列"""
    _init_paths()
    try:
        import os, json
        os.makedirs(os.path.dirname(DELAY_QUEUE_PATH), exist_ok=True)
        with open(DELAY_QUEUE_PATH, 'w', encoding='utf-8') as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _log.warning('[Decision] Failed to save delay queue: %s', e)


def _get_profile(openid):
    """获取用户画像（懒加载避免循环import）"""
    try:
        from profile_storage import _load_user_profile
        return _load_user_profile(openid)
    except Exception:
        return {}


def _get_last_active_days(profile):
    """获取用户最近活跃距今的天数

    从 profile.history 最后一条记录的 timestamp 推算。
    如果没有记录，返回一个很大的数字。
    """
    history = profile.get('history', [])
    if not history:
        return 999
    last = history[-1]
    if isinstance(last, dict):
        ts = last.get('timestamp', '')
        if ts:
            try:
                last_time = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                return (datetime.now() - last_time).days
            except Exception:
                pass
    return 0


def _get_recent_interventions(openid, hours=MIN_INTERVAL_HOURS):
    """获取最近N小时内干预过的类型列表（用于防骚扰去重）"""
    from scheduler_daemon import _load_push_queue
    queue = _load_push_queue()
    now = time.time()
    cutoff = now - hours * 3600
    recent = []
    for entry in queue:
        if entry.get('openid') == openid and entry.get('pushed_at', 0) > cutoff:
            recent.append(entry.get('push_type', '') or entry.get('strategy', ''))
    return list(set(recent))


def _record_intervention_log(openid, intervention_type, detail):
    """记录干预日志（用于防骚扰+追踪效果）"""
    try:
        from profile_storage import _atomic_write_profile
        def modifier(p):
            log = p.setdefault('_intervention_log', [])
            log.append({
                'type': intervention_type,
                'detail': detail,
                'timestamp': datetime.now().isoformat(),
                'time': time.time(),
            })
            if len(log) > 50:
                p['_intervention_log'] = log[-50:]
            return p
        _atomic_write_profile(openid, modifier)
    except Exception:
        pass


def _get_in_chat_care_text(emotion_result, profile):
    """生成聊天回复中嵌入的关怀段

    不是"推送"内容，而是AI回复里的自然融入。
    返回 str（嵌入文本）或 ''（不嵌入）
    """
    if not emotion_result:
        return ''

    emotion = emotion_result.get('emotion', '')
    score = emotion_result.get('score', 0)
    confidence = emotion_result.get('confidence', 0)

    # 只有负面情绪且置信度足够才嵌入
    if score >= 0 or confidence < 0.3:
        return ''

    # 根据情绪类型生成嵌入文本
    if emotion == '崩溃':
        text = '\n\n感受到你的情绪很低落，如果愿意的话，可以跟我聊聊发生了什么。有时候说出来会好受一些。'
    elif emotion == '焦虑':
        text = '\n\n听上去你现在有些焦虑，如果今晚因此睡不着，可以试试【深呼吸】练习，能帮助平复心情。'
    elif emotion == '疲惫':
        text = '\n\n你看起来很疲惫，今晚建议早点休息。如果睡不着，试试【身体扫描】引导，可以更快放松。'
    elif emotion == '低落':
        text = '\n\n感觉你情绪有些低落，没关系，每个人都会有这样的时刻。今晚睡个好觉，明天会不一样的。'
    else:
        text = ''

    return text


def decide_interaction(openid, event_type, event_data, profile=None):
    """核心决策函数：根据事件决定如何干预

    Args:
        openid: 用户ID
        event_type: 事件类型
            - 'chat_emotion': 聊天中检测到情绪
            - 'score_update': 评分更新（handle_sleep_analyze 调用）
            - 'inactive': 不活跃检测
            - 'periodic_scan': 定时扫描（scheduler 调用）
        event_data: 事件数据 dict
            chat_emotion: { 'emotion': {...}, 'message': str, 'reply_len': int }
            score_update: { 'total_score': float }
            inactive: { 'days': int }
            periodic_scan: {} (空)
        profile: 用户画像（可选，自动加载）

    Returns:
        dict: {
            'action': 'in_chat' | 'push_now' | 'delay_push' | 'skip',
            'content': str,           # 推送内容或嵌入文本
            'title': str or None,     # 推送标题（action=push时）
            'detail': str,            # 决策理由（日志用）
            'delay_hours': int or None,  # 延迟小时数（action=delay_push时）
        }
    """
    if profile is None:
        profile = _get_profile(openid)

    # ===== 防骚扰检查 =====
    recent_types = _get_recent_interventions(openid)
    should_skip = len(recent_types) > 0  # 只要最近有推送就不额外推

    # ===== 事件处理 =====
    if event_type == 'chat_emotion':
        return _decide_chat_emotion(openid, event_data, profile, should_skip)

    elif event_type == 'score_update':
        return _decide_score_update(openid, event_data, profile, should_skip)

    elif event_type == 'inactive':
        return _decide_inactive(openid, event_data, profile)

    elif event_type == 'periodic_scan':
        return _decide_periodic(openid, profile, should_skip)

    else:
        return {'action': 'skip', 'content': '', 'title': None, 'detail': f'unknown event: {event_type}'}


def _decide_chat_emotion(openid, event_data, profile, should_skip):
    """聊天情绪事件决策

    优先融入回复（in_chat），不额外推送。
    除非情绪极端且用户很久没主动聊过天。
    """
    emotion = event_data.get('emotion', {})
    message = event_data.get('message', '')
    reply_len = event_data.get('reply_len', 0)

    score = emotion.get('score', 0)
    confidence = emotion.get('confidence', 0)

    # 非负面情绪或置信度低 → 不干预
    if score >= 0 or confidence < 0.3:
        return {'action': 'skip', 'content': '', 'title': None, 'detail': 'positive/low confidence emotion'}

    # 生成嵌入关怀文本
    care_text = _get_in_chat_care_text(emotion, profile)
    in_chat = care_text and reply_len >= _IN_CHAT_MIN_WORDS

    # 极端负面 + 置信度高 → 嵌入关怀 + 记录（供后续推送参考）
    if score <= -1.5 and confidence >= 0.5:
        if in_chat:
            _record_intervention_log(openid, 'chat_emotion_care', emotion.get('emotion', ''))
            return {
                'action': 'in_chat',
                'content': care_text,
                'title': None,
                'detail': f'severe emotion ({emotion.get("emotion","?")}) embedded in reply',
            }
        else:
            return {'action': 'skip', 'content': '', 'title': None, 'detail': 'reply too short for in-chat care'}

    # 一般负面 → 只嵌入（不另外推）
    if in_chat:
        return {
            'action': 'in_chat',
            'content': care_text,
            'title': None,
            'detail': f'mild emotion ({emotion.get("emotion","?")}) embedded in reply',
        }

    return {'action': 'skip', 'content': '', 'title': None, 'detail': 'no action needed'}


def _decide_score_update(openid, event_data, profile, should_skip):
    """评分更新事件决策

    评分下降+情绪也差 → 合并推送（不分两条）
    单纯评分下降但不严重 → 延迟到早上回顾时段推送
    """
    score = event_data.get('total_score', 0)

    # 获取最近情绪
    emotion_summary = profile.get('emotion_summary', {})
    last_24h = emotion_summary.get('last_24h', {})
    negative_ratio = last_24h.get('negative_ratio', 0)

    has_emotion_issue = negative_ratio >= 0.5 and last_24h.get('total_entries', 0) >= 2

    # 评分不低 + 无情绪问题 → 不干预
    if score >= 55 and not has_emotion_issue:
        return {'action': 'skip', 'content': '', 'title': None, 'detail': 'score ok, no emotion issue'}

    # 防骚扰：最近有推送就不额外推
    if should_skip:
        return {'action': 'skip', 'content': '', 'title': None, 'detail': 'recent intervention exists'}

    # 生成合并推送内容
    from wechat_push import _get_username
    username = _get_username(profile) or '朋友'

    if score < 50 and has_emotion_issue:
        # 评分低 + 情绪差 → 合并关怀
        title = f'💙 {username}，需要聊聊吗？'
        content = f'昨晚评分{score}分，加上注意到你最近情绪不太好。今晚可以试试早点放下手机，做几分钟深呼吸放松一下。如果需要，我随时在。'
        _record_intervention_log(openid, 'score_emotion_combined', f'score={score}')
        return {
            'action': 'delay_push',
            'content': content,
            'title': title,
            'detail': f'score={score} + negative_ratio={negative_ratio:.0%} combined care',
            'delay_hours': _get_delay_to_next_slot('morning'),
        }

    elif score < 45:
        # 评分极低 → 立即推送（不论时段）
        title = f'💤 {username}，睡眠需要关注'
        content = f'昨晚评分{score}分，明显偏低。建议回顾一下今天的作息和压力源，今晚试试更早放松。'
        _record_intervention_log(openid, 'score_alert', f'score={score}')
        return {
            'action': 'push_now',
            'content': content,
            'title': title,
            'detail': f'very low score={score}',
        }

    elif score < 55 and has_emotion_issue:
        # 评分偏低 + 情绪差 → 延迟到早上推
        content = f'昨晚评分{score}分，需要留意。今晚睡前试试放松一下，别让白天的压力影响睡眠。'
        _record_intervention_log(openid, 'score_mild', f'score={score}')
        return {
            'action': 'delay_push',
            'content': content,
            'title': f'🌙 {username}，睡前放松一下',
            'detail': f'mild low score={score}',
            'delay_hours': _get_delay_to_next_slot('evening'),
        }

    return {'action': 'skip', 'content': '', 'title': None, 'detail': 'no strong trigger'}


def _decide_inactive(openid, event_data, profile):
    """不活跃检测事件决策

    用户连续N天没打开小程序 → 关怀推送
    """
    days = event_data.get('days', INACTIVE_DAYS_THRESHOLD)

    if days < INACTIVE_DAYS_THRESHOLD:
        return {'action': 'skip', 'content': '', 'title': None, 'detail': f'only {days}d inactive'}

    from wechat_push import _get_username
    username = _get_username(profile) or '朋友'

    if days >= 7:
        title = f'👋 {username}，好久不见'
        content = f'已经{days}天没见到你了，最近睡得好吗？如果有什么在困扰你，随时可以找我聊聊。'
    elif days >= 3:
        title = f'💬 {username}，最近怎么样？'
        content = f'{days}天没见了，有点挂念。今晚睡得好吗？如果有什么想说的，我一直在。'
    else:
        title = f'🌙 {username}，今晚睡了吗？'
        content = f'最近看到你没有记录睡眠，是太忙了吗？要是需要帮忙，随时找我。'

    _record_intervention_log(openid, 'inactive_push', f'{days}d')
    return {
        'action': 'delay_push',
        'content': content,
        'title': title,
        'detail': f'inactive {days}d',
        'delay_hours': _get_delay_to_next_slot('morning'),
    }


def _decide_periodic(openid, profile, should_skip):
    """定时扫描决策（scheduler 调用）

    检查：
    1. 不活跃用户
    2. 延迟推送队列里的到期推送
    """
    if should_skip:
        return {'action': 'skip', 'content': '', 'title': None, 'detail': 'recent intervention'}

    # 检查延迟推送队列
    queue = _load_delay_queue()
    now = time.time()
    for entry in queue:
        if entry.get('openid') == openid and not entry.get('sent'):
            due_at = entry.get('due_at', 0)
            if now >= due_at:
                return {
                    'action': 'push_now',
                    'content': entry.get('content', ''),
                    'title': entry.get('title', ''),
                    'detail': f'delayed push due: {entry.get("reason", "?")}',
                }
            else:
                wait_hours = (due_at - now) / 3600
                return {'action': 'skip', 'content': '', 'title': None, 'detail': f'delayed push in {wait_hours:.1f}h'}

    return {'action': 'skip', 'content': '', 'title': None, 'detail': 'periodic scan: no action'}


def _get_delay_to_next_slot(target_slot):
    """计算到下一个推送时间槽的延迟小时数

    Args:
        target_slot: 'morning' 或 'evening'

    Returns:
        int: 延迟小时数
    """
    now = datetime.now()
    target_hours = DELAY_SLOTS.get(target_slot, (8, 9))
    target_hour = target_hours[0]  # 取槽的开始时间

    # 计算目标时间
    target_time = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)

    # 如果目标时间已经过了，推到明天
    if target_time <= now:
        target_time += timedelta(days=1)

    delay = (target_time - now).total_seconds() / 3600
    return min(int(delay), DELAY_PUSH_MAX)


def queue_delayed_push(openid, title, content, reason='', delay_hours=8):
    """将延迟推送加入队列

    Args:
        openid: 用户ID
        title: 推送标题
        content: 推送内容
        reason: 推送理由（日志用）
        delay_hours: 延迟小时数

    Returns:
        bool: 是否成功入队
    """
    if delay_hours <= 0:
        return False  # 用 push_now 代替

    now = time.time()
    entry = {
        'id': f'{openid}_delayed_{int(now)}',
        'openid': openid,
        'title': title,
        'content': content,
        'reason': reason,
        'created_at': now,
        'due_at': now + delay_hours * 3600,
        'sent': False,
        'push_type': 'delayed',
    }

    queue = _load_delay_queue()
    queue.append(entry)
    _save_delay_queue(queue)
    _log.info('[Decision] Delayed push queued for %s in %dh: %s', openid[:8], delay_hours, reason[:50])
    return True


def execute_push(openid, title, content):
    """执行立即推送（写入 scheduler 的推送队列 + 尝试微信发送）

    Args:
        openid: 用户ID
        title: 推送标题
        content: 推送内容

    Returns:
        bool: 推送是否已启用
    """
    from scheduler_daemon import _load_push_queue, _save_push_queue, PUSH_LOCK, _try_send_push_entry, PUSH_EXPIRE_HOURS

    now = time.time()
    entry = {
        'id': f'{openid}_decision_{int(now)}',
        'openid': openid,
        'title': title,
        'content': content,
        'push_type': 'decision',
        'strategy': 'push_decision',
        'reason': 'decision_engine',
        'pushed_at': now,
        'expires_at': now + PUSH_EXPIRE_HOURS * 3600,
        'sent': False,
        'read': False,
    }

    # 尝试微信发送
    send_result = _try_send_push_entry(entry)
    entry['sent'] = send_result.get('success', False)
    entry['send_result'] = send_result.get('errmsg', '')

    import threading as _th
    with getattr(_th, 'Lock', lambda: _th.Lock)() if False else PUSH_LOCK:
        queue = _load_push_queue()
        queue.append(entry)
        _save_push_queue(queue)

    _log.info('[Decision] Push executed for %s: %s (wx=%s)', openid[:8], title[:30], entry['sent'])
    return entry['sent']


def process_delayed_queue():
    """处理延迟推送队列（由 scheduler 定时调用）

    检查到期的延迟推送，执行推送。

    Returns:
        int: 本次处理的推送数
    """
    queue = _load_delay_queue()
    now = time.time()
    processed = 0

    for entry in queue:
        if entry.get('sent'):
            continue
        if now >= entry.get('due_at', 0):
            openid = entry.get('openid', '')
            title = entry.get('title', '')
            content = entry.get('content', '')
            if openid and title and content:
                execute_push(openid, title, content)
                entry['sent'] = True
                entry['sent_at'] = now
                processed += 1

    if processed > 0:
        _save_delay_queue(queue)
        _log.info('[Decision] Processed %d delayed pushes', processed)

    return processed


# ===== 自测 =====
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    test_profile = {
        'history': [
            {'date': '2026-05-01', 'wm_score': 65, 'timestamp': '2026-05-01 22:00:00'},
            {'date': '2026-05-02', 'wm_score': 48, 'timestamp': '2026-05-02 21:30:00'},
        ],
        'emotion_summary': {
            'last_24h': {'avg_score': -1.2, 'negative_ratio': 0.67, 'total_entries': 3, 'top_emotions': [{'emotion': '焦虑', 'count': 2}]},
            'last_7d': {'avg_score': -0.8, 'negative_ratio': 0.5, 'total_entries': 6},
        }
    }

    print('=== 1. Chat emotion (negative) ===')
    r = decide_interaction('test_user', 'chat_emotion', {
        'emotion': {'emotion': '焦虑', 'score': -1.5, 'confidence': 0.67},
        'message': '最近压力很大',
        'reply_len': 200,
    }, test_profile)
    print('  Action:', r['action'])
    print('  Detail:', r['detail'])
    if r['action'] == 'in_chat':
        print('  In-chat text:', repr(r['content'][:60]))

    print()
    print('=== 2. Score + emotion combined ===')
    r = decide_interaction('test_user', 'score_update', {'total_score': 42}, test_profile)
    print('  Action:', r['action'])
    print('  Title:', r.get('title', ''))
    print('  Content:', r.get('content', '')[:80])

    print()
    print('=== 3. Inactive 3 days ===')
    r = decide_interaction('test_user', 'inactive', {'days': 3}, test_profile)
    print('  Action:', r['action'])
    print('  Title:', r.get('title', ''))
    print('  Content:', r.get('content', '')[:80])

    print()
    print('=== 4. Inactive 7 days ===')
    r = decide_interaction('test_user', 'inactive', {'days': 8}, test_profile)
    print('  Action:', r['action'])
    print('  Title:', r.get('title', ''))
    print('  Content:', r.get('content', '')[:80])

    print()
    print('OK')
