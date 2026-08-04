#!/usr/bin/env python3
"""
restful_companion.py — AISleepGen 静息陪伴模式 v2（反馈回路版）

哲学：最好的陪伴是让你感觉不到被陪伴。
用户设置入睡时间后，不需要任何操作。

哈萨比斯整合架构：感知→决策→执行→反馈→微调→完成。
每轮 tick 检查上一轮干预效果，根据效果切换或维持协议。

不依赖 DeepSeek API。纯规则 + 生理反馈。
"""

import json, time, os, threading, logging
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, 'data', 'restful_companion')
os.makedirs(DATA_DIR, exist_ok=True)

# ===== 呼吸协议模板 =====
PROTOCOLS = {
    '4-7-8': {
        'name': '4-7-8 放松呼吸',
        'inhale_s': 4, 'hold_s': 7, 'exhale_s': 8,
        'cycles': 5,
        'fade_in_cycles': 2,
        'fade_out_cycles': 3,
        'target_state': 'parasympathetic',  # 理想效果：激活副交感
    },
    'box': {
        'name': '盒式呼吸',
        'inhale_s': 4, 'hold_s': 4, 'exhale_s': 4, 'hold_empty_s': 4,
        'cycles': 5,
        'fade_in_cycles': 2,
        'fade_out_cycles': 3,
        'target_state': 'balance',
    },
    'long_exhale': {
        'name': '延长呼气',
        'inhale_s': 4, 'exhale_s': 8,
        'cycles': 8,
        'fade_in_cycles': 3,
        'fade_out_cycles': 3,
        'target_state': 'sedation',
    },
}

# ===== 反馈计算常量 =====
FEEDBACK_CONFIG = {
    'hrv_effective_threshold': 0.05,        # HRV 提升 >5% 算有效
    'hrv_counter_productive_threshold': -0.05,  # HRV 下降 >5% 算反效果
    'switch_quiet_seconds': 60,             # 一个协议持续60秒无效就换
    'max_switches_per_session': 3,          # 一晚最多切换3次
    'full_cycle_retry_after_switch': True,  # 切换后重跑完整周期
}

# ===== 用户设置存储 =====
USER_SETTINGS_PATH = os.path.join(DATA_DIR, 'user_settings.json')

# ===== 协议效果记忆（范式3：用户历史） =====
# 格式: {openid: {protocol_name: {'avg_hrv_change': 0.08, 'sessions': 3, 'last_used_ts': 1700000000.0}}}
USER_PROTOCOL_HISTORY_PATH = os.path.join(DATA_DIR, 'protocol_history.json')

def _load_protocol_history():
    if os.path.exists(USER_PROTOCOL_HISTORY_PATH):
        with open(USER_PROTOCOL_HISTORY_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def _save_protocol_history(history):
    with open(USER_PROTOCOL_HISTORY_PATH, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def _record_protocol_effect(openid, protocol, avg_hrv_change):
    """本轮协议结束后，记录效果到历史"""
    history = _load_protocol_history()
    if openid not in history:
        history[openid] = {}
    prev = history[openid].get(protocol, {'avg_hrv_change': 0.0, 'sessions': 0})
    n = prev['sessions'] + 1
    history[openid][protocol] = {
        'avg_hrv_change': round((prev['avg_hrv_change'] * prev['sessions'] + avg_hrv_change) / n, 4),
        'sessions': n,
        'last_used_ts': time.time(),
    }
    _save_protocol_history(history)

def _load_settings():
    if os.path.exists(USER_SETTINGS_PATH):
        with open(USER_SETTINGS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def _save_settings(settings):
    with open(USER_SETTINGS_PATH, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

def get_user_setting(openid):
    settings = _load_settings()
    return settings.get(openid, {
        'enabled': False, 'bedtime': '23:00',
        'protocol': '4-7-8',
        'audio_preference': 'voice',
        'night_monitor': True,
    })

def set_user_setting(openid, updates):
    settings = _load_settings()
    if openid not in settings:
        settings[openid] = {}
    settings[openid].update(updates)
    _save_settings(settings)
    return settings[openid]

# ===== 会话管理 =====
ACTIVE_SESSIONS = {}

def start_session(openid, setting=None):
    if not setting:
        setting = get_user_setting(openid)
    if not setting.get('enabled'):
        return {'error': '静息陪伴未开启'}

    protocol = PROTOCOLS.get(setting.get('protocol', '4-7-8'), PROTOCOLS['4-7-8'])

    session = {
        'openid': openid,
        'started_at': time.time(),
        'protocol': setting['protocol'],
        'protocol_name': protocol['name'],
        'phase': 'fade_in',
        'cycle': 0,
        'total_cycles': protocol['cycles'],
        'fade_in_cycles': protocol['fade_in_cycles'],
        'fade_out_cycles': protocol['fade_out_cycles'],
        'quiet_seconds': 0,
        'movement_count': 0,
        'night_interventions': 0,
        'status': 'active',
        'audio_preference': setting.get('audio_preference', 'voice'),
        'night_monitor': setting.get('night_monitor', True),

        # === 反馈回路状态（v2 新增） ===
        'switch_count': 0,                      # 本晚已切换协议次数
        'protocol_history': [],                  # [{'ts', 'protocol', 'reason'}, ...]
        'current_cycle_effectiveness': [],       # [hrv_change, ...] 本周期内的反馈样本
        'last_protocol_start': time.time(),      # 当前协议开始时间
        'last_cycle_hrv_baseline': None,         # 当前周期开始时的 HRV 基线

        # === 范式3：用户历史记忆（加载） ===
        'user_protocol_history': _load_protocol_history().get(openid, {}),
        'current_protocol_avg_hrv': 0.0,         # 本协议累计平均HRV变化
    }

    ACTIVE_SESSIONS[openid] = session
    _log_event(openid, 'start', {
        'protocol': setting['protocol'], 'bedtime': setting.get('bedtime'),
    })
    return session


def get_next_action(openid, feedback=None):
    """
    反馈回路核心逻辑：
    1. 先评估上一轮干预效果（如果 feedback 有 HRV 数据）
    2. 根据效果做微调：有效→继续，无效→切换协议，反效果→切换+重新淡入
    3. 然后才推进状态机
    """
    session = ACTIVE_SESSIONS.get(openid)
    if not session:
        return {'action': 'no_session', 'error': '没有活跃会话'}
    if session['status'] != 'active':
        return {'action': 'ended', 'reason': session.get('end_reason', 'completed')}

    feedback = feedback or {}
    now = time.time()
    elapsed = now - session['started_at']
    session['quiet_seconds'] += feedback.get('time_elapsed', 5)

    # === 反馈回路：评估上一轮干预效果 ===
    hrv_change = feedback.get('hrv_change')
    if hrv_change is not None and session['phase'] in ('active', 'fade_out'):
        session['current_cycle_effectiveness'].append(hrv_change)
        _evaluate_and_maybe_switch(session, hrv_change)

    # === 夜醒检测 ===
    if feedback.get('night_awakening') or feedback.get('movement_detected'):
        session['movement_count'] += 1
        session['quiet_seconds'] = 0
        if session['phase'] in ('monitoring', 'fade_out'):
            session['phase'] = 'fade_in'
            session['cycle'] = 0
            session['night_interventions'] += 1
            _log_event(openid, 'night_awakening', {
                'intervention_count': session['night_interventions'],
            })
            return {
                'action': 'reengage',
                'phase': 'fade_in',
                'protocol': session['protocol'],
                'protocol_name': session['protocol_name'],
                'cycle': 0,
                'total_cycles': session['total_cycles'],
                'message': '我注意到你醒了，我们一起做几次呼吸',
            }

    # === 阶段推进 ===
    if session['phase'] == 'fade_in':
        if session['cycle'] < session['fade_in_cycles']:
            session['cycle'] += 1
            return _build_breath_action(session, session['cycle'], 'fade_in')
        else:
            session['phase'] = 'active'
            session['cycle'] = 0
            # 记录新周期基线
            if hrv_change is not None:
                session['last_cycle_hrv_baseline'] = hrv_change

    if session['phase'] == 'active':
        if session['cycle'] < session['total_cycles']:
            session['cycle'] += 1
            return _build_breath_action(session, session['cycle'], 'active')
        else:
            session['phase'] = 'fade_out'
            session['cycle'] = 0

    if session['phase'] == 'fade_out':
        if session['cycle'] < session['fade_out_cycles']:
            session['cycle'] += 1
            return _build_breath_action(session, session['cycle'], 'fade_out')
        else:
            session['phase'] = 'monitoring'
            session['quiet_seconds'] = 0
            # 周期结束，清空效果记录
            session['current_cycle_effectiveness'] = []

    if session['phase'] == 'monitoring':
        if session['quiet_seconds'] >= 120:
            _end_session(openid, 'fell_asleep')
            return {'action': 'end', 'reason': 'fell_asleep', 'message': '晚安，好好休息'}
        if elapsed > 1800:
            _end_session(openid, 'timeout')
            return {'action': 'end', 'reason': 'timeout', 'message': '陪伴结束，晚安'}
        return {'action': 'monitor', 'quiet_seconds': session['quiet_seconds'], 'next_check_in': 15}

    return {'action': 'idle'}


def _evaluate_and_maybe_switch(session, hrv_change):
    """
    反馈回路评估器：根据 HRV 变化判断当前协议是否有效。
    决定是否切换协议。
    """
    cfg = FEEDBACK_CONFIG
    elapsed_on_protocol = time.time() - session['last_protocol_start']

    # 收集足够样本再做评估
    samples = session['current_cycle_effectiveness']
    if len(samples) < 2:
        return  # 样本不够，继续观察

    avg_effect = sum(samples) / len(samples)

    # 超过切换次数上限 → 不再切换
    if session['switch_count'] >= cfg['max_switches_per_session']:
        return

    need_switch = False
    switch_reason = ''

    if avg_effect < cfg['hrv_counter_productive_threshold']:
        # 反效果：HRV 持续下降 → 必须换
        need_switch = True
        switch_reason = 'counter_productive'
    elif avg_effect < cfg['hrv_effective_threshold'] and elapsed_on_protocol > cfg['switch_quiet_seconds']:
        # 无效且持续了足够时间 → 尝试换
        need_switch = True
        switch_reason = 'ineffective'

    if need_switch:
        old_protocol = session['protocol']
        new_protocol = _pick_next_protocol(session, old_protocol)
        session['protocol'] = new_protocol
        session['protocol_name'] = PROTOCOLS[new_protocol]['name']
        session['switch_count'] += 1
        session['last_protocol_start'] = time.time()
        session['current_cycle_effectiveness'] = []
        session['last_cycle_hrv_baseline'] = None

        # 记录历史
        session['protocol_history'].append({
            'ts': time.time(),
            'from': old_protocol,
            'to': new_protocol,
            'reason': switch_reason,
            'avg_hrv_change': round(avg_effect, 4),
        })

        # 切换后重置到 fade_in，让用户重新适应
        session['phase'] = 'fade_in'
        session['cycle'] = 0

        _log_event(session['openid'], 'protocol_switch', {
            'from': old_protocol, 'to': new_protocol,
            'reason': switch_reason,
        })


def _pick_next_protocol(session, current_protocol):
    """
    协议选择器（范式2+3+4 闭环版）。

    三种信号加权决策：
    范式2（稳态维持）：HRV 趋势方向 → 选择反方向协议
    范式3（用户历史）：用户过往哪个协议效果最好
    范式4（理论驱动）：时间上下文 → 深夜 vs 刚到入睡时间
    """
    # 范式4：时间上下文
    now = datetime.now()
    hour = now.hour + now.minute / 60.0
    is_deep_night = (hour >= 1 and hour < 4)  # 凌晨1-4点为深夜晚
    is_early = (hour >= 21 or hour < 0)        # 21点后为刚入睡

    # 索引化协议
    protocol_order = ['4-7-8', 'box', 'long_exhale']
    p_scores = {}

    for p in protocol_order:
        score = 0.0

        # 范式2：稳态维持方向
        protocol_type = PROTOCOLS[p]['target_state']
        if session['current_cycle_effectiveness']:
            avg_hrv = sum(session['current_cycle_effectiveness']) / len(session['current_cycle_effectiveness'])
            if protocol_type == 'parasympathetic' and avg_hrv < 0:
                score += 2.0  # HRV下降（交感高）→ 选副交感激活
            elif protocol_type == 'balance' and avg_hrv > 0.05:
                score += 1.0  # HRV略升 → 平衡维持
            elif protocol_type == 'sedation' and avg_hrv < -0.03:
                score += 1.5  # HRV过低（低迷）→ 镇静型（长呼）

        # 范式3：用户历史得分
        user_hist = session.get('user_protocol_history', {})
        if p in user_hist:
            past = user_hist[p]
            score += max(0, past['avg_hrv_change']) * 5  # 历史HRV提升幅度加权
            recency_bonus = 1.0 if (time.time() - past.get('last_used_ts', 0)) < 86400 else 0.3
            score *= recency_bonus  # 24小时内用过的协议降权（避免反复横跳）

        # 范式4：时间上下文得分
        if is_deep_night:
            if protocol_type == 'parasympathetic':
                score += 1.0  # 深夜交感高，副交感优先
            elif protocol_type == 'sedation':
                score += 0.5
        elif is_early:
            if protocol_type == 'balance':
                score += 1.0  # 初入夜用平衡协议
            elif protocol_type == 'parasympathetic':
                score += 0.5

        # 硬约束：不选正在使用的协议（除非这是唯一选择）
        if p == current_protocol:
            score -= 99.0

        p_scores[p] = score

    # 选最高分
    best_protocol = max(p_scores, key=p_scores.get)
    return best_protocol


# ===== 原有函数（未改） =====

def _build_breath_action(session, cycle, phase_label):
    protocol = PROTOCOLS.get(session['protocol'], PROTOCOLS['4-7-8'])
    steps = []
    if 'hold_s' in protocol and 'hold_empty_s' in protocol:
        steps = [
            {'phase': 'inhale', 'duration_s': protocol['inhale_s'], 'label': '吸气'},
            {'phase': 'hold', 'duration_s': protocol['hold_s'], 'label': '屏气'},
            {'phase': 'exhale', 'duration_s': protocol['exhale_s'], 'label': '呼气'},
            {'phase': 'hold_empty', 'duration_s': protocol['hold_empty_s'], 'label': '悬停'},
        ]
    elif 'hold_s' in protocol:
        steps = [
            {'phase': 'inhale', 'duration_s': protocol['inhale_s'], 'label': '轻轻吸气'},
            {'phase': 'hold', 'duration_s': protocol['hold_s'], 'label': '屏住呼吸'},
            {'phase': 'exhale', 'duration_s': protocol['exhale_s'], 'label': '缓缓呼气'},
        ]
    else:
        steps = [
            {'phase': 'inhale', 'duration_s': protocol['inhale_s'], 'label': '吸气'},
            {'phase': 'exhale', 'duration_s': protocol['exhale_s'], 'label': '慢慢呼出'},
        ]
    volume = 1.0
    fade_in_total = session['fade_in_cycles']
    fade_out_total = session['fade_out_cycles']
    if phase_label == 'fade_in':
        volume = max(0.1, cycle / max(fade_in_total, 1))
    elif phase_label == 'fade_out':
        volume = max(0.1, 1.0 - (cycle / max(fade_out_total, 1)))
    return {
        'action': 'breath_guide', 'phase': phase_label,
        'cycle': cycle, 'total_cycles': session['total_cycles'],
        'protocol': session['protocol'], 'protocol_name': session['protocol_name'],
        'volume': round(volume, 2), 'steps': steps,
        'prefer_audio': session['audio_preference'] != 'silent',
        'message': _get_guidance_message(phase_label, cycle),
        # 新增：返回切换历史和效果摘要（给前端/数据层用）
        'switch_count': session['switch_count'],
        'protocol_effectiveness': _summarize_effectiveness(session),
    }


def _summarize_effectiveness(session):
    """返回当前会话的效果摘要"""
    samples = session['current_cycle_effectiveness']
    if not samples:
        return None
    return {
        'samples': len(samples),
        'average_hrv_change': round(sum(samples) / len(samples), 4),
        'switch_history': len(session['protocol_history']),
    }


def _get_guidance_message(phase, cycle):
    if phase == 'fade_in':
        msgs = ['跟着我的节奏', '慢慢来', '让身体沉下来', '感受呼吸']
        return msgs[min(cycle, len(msgs)-1)]
    elif phase == 'active':
        # 在反馈回路模式下的引导语增加"效果"感知
        msgs = ['做得很棒，身体在回应', '保持这个节奏', '让紧张随着呼气离开', '你的心率在变平稳', '做得很好']
        return msgs[min(cycle, len(msgs)-1)]
    elif phase == 'fade_out':
        msgs = ['现在让呼吸自然发生', '不需要做任何事', '让身体自己来', '我在这里']
        return msgs[min(cycle, len(msgs)-1)]
    return ''


def _end_session(openid, reason):
    session = ACTIVE_SESSIONS.get(openid)
    if session:
        session['status'] = 'ended'
        session['end_reason'] = reason
        session['ended_at'] = time.time()
        duration = session['ended_at'] - session['started_at']

        # 范式3：记录本轮各协议效果到用户历史
        for hist_entry in session['protocol_history']:
            proto = hist_entry.get('to', '')
            avg_hrv = hist_entry.get('avg_hrv_change', 0)
            if proto:
                _record_protocol_effect(openid, proto, avg_hrv)
        # 也记录最终使用协议的累积效果
        final_protocol = session['protocol']
        if session['current_cycle_effectiveness']:
            final_avg = sum(session['current_cycle_effectiveness']) / len(session['current_cycle_effectiveness'])
            _record_protocol_effect(openid, final_protocol, final_avg)

        _log_event(openid, 'end', {
            'reason': reason, 'duration_s': round(duration),
            'movement_count': session['movement_count'],
            'night_interventions': session['night_interventions'],
            'protocol_switches': session['switch_count'],
            'protocol_history': session['protocol_history'],
        })


def get_session_status(openid):
    session = ACTIVE_SESSIONS.get(openid)
    if not session:
        return {'active': False}
    return {
        'active': session['status'] == 'active',
        'phase': session['phase'],
        'protocol': session['protocol'],
        'elapsed_s': round(time.time() - session['started_at']),
        'switch_count': session['switch_count'],
    }


def _log_event(openid, event, data=None):
    log_path = os.path.join(DATA_DIR, f'events_{datetime.now().strftime("%Y%m")}.jsonl')
    entry = {'ts': time.time(), 'openid': openid, 'event': event, 'data': data or {}}
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


# ===== 后台守护 =====
def _daemon_check():
    while True:
        time.sleep(60)
        now = time.time()
        to_end = []
        for openid, session in ACTIVE_SESSIONS.items():
            if session['status'] != 'active':
                continue
            if now - session['started_at'] > 3600:
                to_end.append(openid)
        for openid in to_end:
            _end_session(openid, 'daemon_timeout')

_daemon_thread = threading.Thread(target=_daemon_check, daemon=True)
_daemon_thread.start()
