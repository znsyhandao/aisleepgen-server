#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
body_context.py — AISleepGen 具身上下文模块 (v1.0)

SCAN启示第2条的实现：将零散的睡眠数据、情绪记录、陪伴模式上报等
"生理碎片"合成为持续的身体上下文状态。

核心输出：get_body_context(openid)
    → 一个统一的 dict，描述用户当前的"身体状态"：
        - physiological: 心率趋势(如有)、体动、呼吸引导阶段
        - sleep_rhythm: 入睡时间模式、睡眠剥夺风险、昼夜节律偏移
        - emotional_baseline: 近期情绪基线 + 当前情绪波动
        - recovery_state: 恢复状态评估(充分/不足/风险)
        - context_timestamp: 上下文生成时间

不依赖大模型，纯规则引擎，~3ms。
"""

import json, os, time, logging, threading
from datetime import datetime, timedelta
from collections import defaultdict

_body_log = logging.getLogger('aisleepgen.body_context')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ==================== 内部状态缓存 ====================
# 体动/陪伴状态全局缓存（由 companion update 写入）
_BODY_CACHE = {}      # {openid: {last_movement, last_quiet_start, companion_state, ...}}
_BODY_LOCK = threading.RLock()

# ==================== 公开 API ====================

def report_body_event(openid, event_type, data=None):
    """记录一个身体事件（由其他模块调用）。

    event_type:
        'companion_movement' — 陪伴模式下的体动上报
        'companion_start' — 用户进入陪伴模式
        'companion_exit' — 陪伴模式结束
        'survey_submitted' — 用户填写了睡眠问卷
        'emotion_detected' — 情绪检测结果
        'chat_activity' — 用户聊天活动

    data: dict, 事件相关数据
    """
    with _BODY_LOCK:
        cache = _BODY_CACHE.setdefault(openid, {
            'events': [],
            'last_movement_time': None,
            'last_quiet_start': None,
            'companion_active': False,
            'companion_state': None,
            'companion_start_time': None,
            'today_survey': None,
        })

        now = time.time()
        ts = datetime.now().isoformat()

        # 记录事件（最多保留最近50条）
        cache['events'].append({
            'type': event_type,
            'ts': ts,
            'ts_epoch': now,
            'data': data or {}
        })
        if len(cache['events']) > 50:
            cache['events'] = cache['events'][-50:]

        # 更新特定字段
        if event_type == 'companion_movement':
            cache['last_movement_time'] = now
            cache['last_quiet_start'] = None
        elif event_type == 'companion_start':
            cache['companion_active'] = True
            cache['companion_state'] = data.get('state', 'CALMING')
            cache['companion_start_time'] = now
            cache['last_quiet_start'] = None
        elif event_type == 'companion_exit':
            cache['companion_active'] = False
            cache['companion_state'] = None
            time_in_companion = (now - cache.get('companion_start_time', now)) if cache.get('companion_start_time') else 0
            cache['last_companion_duration'] = round(time_in_companion / 60, 1)  # minutes
            cache['last_companion_time'] = now
        elif event_type == 'survey_submitted':
            cache['today_survey'] = {
                'ts': ts,
                'ts_epoch': now,
                'data': data or {}
            }
        elif event_type == 'emotion_detected':
            cache['last_emotion'] = {
                'ts': ts,
                'ts_epoch': now,
                'emotion': data.get('emotion', 'neutral'),
                'score': data.get('score', 0),
            }

        return True


def get_body_context(openid='default'):
    """获取用户的完整身体上下文。

    返回 dict:
    {
        'available': bool,         # 是否有足够数据
        'physiological': { ... },  # 来自陪伴模式+体动上报
        'sleep_rhythm': { ... },  # 来自survey+history
        'emotional_baseline': { ... },  # 来自情绪检测
        'recovery_state': { ... },  # 综合评估
        'last_activity': { ... },  # 最近活动记录
        'context_ts': str,         # 本上下文的生成时间
    }
    """
    with _BODY_LOCK:
        cache = _BODY_CACHE.get(openid, {})
        events = cache.get('events', [])

    # 从持久化profile加载睡眠数据
    profile = _load_profile_for_context(openid)

    context = {
        'available': False,
        'physiological': {},
        'sleep_rhythm': {},
        'emotional_baseline': {},
        'recovery_state': {},
        'last_activity': {},
        'context_ts': datetime.now().isoformat(),
    }

    # ===== 1. 生理层 (physiological) =====
    phys = {}
    with _BODY_LOCK:
        cache = _BODY_CACHE.get(openid, {})

        if cache.get('companion_active'):
            phys['in_companion'] = True
            phys['companion_state'] = cache.get('companion_state')
            companion_duration = time.time() - cache.get('companion_start_time', time.time())
            phys['companion_duration_seconds'] = round(companion_duration)
            phys['companion_duration_display'] = _format_duration(companion_duration)
        else:
            phys['in_companion'] = False
            # 上次陪伴模式结束距今
            last_comp = cache.get('last_companion_time')
            if last_comp:
                phys['last_companion_minutes_ago'] = round((time.time() - last_comp) / 60, 1)

        if cache.get('last_movement_time'):
            quiet_minutes = (time.time() - cache['last_movement_time']) / 60
            phys['quiet_minutes'] = round(quiet_minutes, 1)
            phys['is_resting'] = quiet_minutes > 5  # 超过5分钟无体动=休息中

        # 今日是否已填问卷
        if cache.get('today_survey'):
            phys['today_survey_submitted'] = True
            phys['survey_data'] = cache['today_survey']['data']
        else:
            phys['today_survey_submitted'] = False

    # 从profile中读取最新评分
    latest = profile.get('latest', {})
    if latest:
        phys['last_reported_duration'] = latest.get('total_duration', 0)
        phys['last_reported_latency'] = latest.get('sleep_latency', 0)
        phys['last_reported_awake_times'] = latest.get('awake_times', 0)
        phys['last_reported_bedtime'] = latest.get('bedtime', '')

    context['physiological'] = phys

    # ===== 2. 睡眠节律层 (sleep_rhythm) =====
    rhythm = _analyze_sleep_rhythm(profile)
    context['sleep_rhythm'] = rhythm

    # ===== 3. 情绪基底层 (emotional_baseline) =====
    emotion = _analyze_emotion_baseline(profile)
    context['emotional_baseline'] = emotion

    # ===== 4. 恢复状态评估 (recovery_state) =====
    recovery = _assess_recovery(phys, rhythm, emotion)
    context['recovery_state'] = recovery

    # ===== 5. 近期活跃度 =====
    activity = _get_activity_level(profile, events)
    context['last_activity'] = activity

    # ===== 整体可用性标记 =====
    context['available'] = bool(
        phys.get('today_survey_submitted') or
        phys.get('in_companion') or
        rhythm.get('has_data') or
        emotion.get('has_data')
    )

    # v3.0: 昼夜节律数据使系统可用（即使无问卷/陪伴记录）
    try:
        from homeostatic_circuit import get_circuit_context
        cc = get_circuit_context(openid)
        if cc.get('drowsiness') or cc.get('circadian_drift'):
            context['available'] = True
    except (ImportError, Exception):
        pass

    return context


def _load_profile_for_context(openid):
    """轻量加载profile，不走缓存层避免循环依赖"""
    profile_path = os.path.join(PROJECT_ROOT, 'user_profile.json')
    try:
        if os.path.exists(profile_path):
            with open(profile_path, 'r', encoding='utf-8-sig') as f:
                all_profiles = json.load(f)
            return all_profiles.get(openid, {})
    except Exception as e:
        _body_log.warning('[BodyCtx] Profile load failed: %s', e)
    return {}


def _analyze_sleep_rhythm(profile):
    """分析睡眠节律——从历史数据提炼模式"""
    result = {
        'has_data': False,
        'typical_bedtime': None,
        'bedtime_consistency': 'unknown',  # regular | irregular | unknown
        'avg_duration_minutes': 0,
        'sleep_debt': 'unknown',   # normal | moderate | severe
        'circadian_risk': False,   # 昼夜节律紊乱风险
        'sleep_deprivation_risk': False,  # 睡眠剥夺风险
    }

    history = profile.get('history', [])
    if not history:
        return result

    # 提取有数据的记录
    records = []
    for h in history:
        if not isinstance(h, dict):
            continue
        bedtime = h.get('bedtime', '')
        duration = h.get('total_duration', 0)
        score = h.get('wm_score', 0)
        latency = h.get('sleep_latency', 0)
        awake = h.get('awake_times', 0)
        records.append({
            'date': h.get('date', ''),
            'bedtime': bedtime,
            'duration': duration,
            'score': score,
            'latency': latency,
            'awake': awake,
        })

    if len(records) < 2:
        return result

    result['has_data'] = True
    result['record_count'] = len(records)

    # ---- 入睡时间模式 ----
    bedtimes = [r['bedtime'] for r in records if r['bedtime']]
    if bedtimes:
        # 解析为分钟数
        bedtime_minutes = []
        for bt in bedtimes:
            try:
                parts = bt.split(':')
                h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
                # 跨天：22点以后算当天，6点以前算前一天深夜
                mins = h * 60 + m
                if h < 12:  # 凌晨 -> 加24小时统一为"深夜"尺度
                    mins += 24 * 60
                bedtime_minutes.append(mins)
            except:
                continue

        if bedtime_minutes:
            avg_mins = sum(bedtime_minutes) / len(bedtime_minutes)
            # 还原为日常时间
            display_mins = avg_mins % (24 * 60)
            display_h = int(display_mins // 60)
            display_m = int(display_mins % 60)
            result['typical_bedtime'] = f'{display_h:02d}:{display_m:02d}'

            # 一致性评判：标准差 > 90分钟 = 不规律
            variance = sum((m - avg_mins) ** 2 for m in bedtime_minutes) / len(bedtime_minutes)
            std_dev = variance ** 0.5
            if std_dev > 90:
                result['bedtime_consistency'] = 'irregular'
            elif std_dev > 45:
                result['bedtime_consistency'] = 'somewhat_irregular'
            else:
                result['bedtime_consistency'] = 'regular'

            # 判断典型入睡时间是否偏晚（跨天后的22点=22h, 23点=23h, 凌晨1点=25h）
            raw_avg = avg_mins % (24 * 60)
            if raw_avg >= 22 * 60 or raw_avg < 3 * 60:
                result['late_bedtime'] = True
            else:
                result['late_bedtime'] = False

    # ---- 平均时长 ----
    durations = [r['duration'] for r in records if r['duration'] > 0]
    if durations:
        avg_dur = sum(durations) / len(durations)
        result['avg_duration_minutes'] = round(avg_dur, 1)
        # 判断时长健康度（7-9小时为理想）
        if avg_dur < 360:  # < 6小时
            result['sleep_debt'] = 'severe'
        elif avg_dur < 420:  # < 7小时
            result['sleep_debt'] = 'moderate'
        else:
            result['sleep_debt'] = 'normal'

    # ---- 睡眠剥夺风险（连续3天 < 6小时） ----
    recent = records[-5:]  # 最近5天
    short_sleep_days = sum(1 for r in recent if 0 < r['duration'] < 360)
    if len(recent) >= 3 and short_sleep_days >= 3:
        result['sleep_deprivation_risk'] = True

    # ---- 昼夜节律紊乱风险（入睡时间波动 > 2小时） ----
    if len(bedtime_minutes) >= 3:
        recent_bedtimes = bedtime_minutes[-5:]
        if len(recent_bedtimes) >= 3:
            b_var = sum((m - sum(recent_bedtimes)/len(recent_bedtimes)) ** 2 for m in recent_bedtimes) / len(recent_bedtimes)
            b_std = b_var ** 0.5
            if b_std > 120:  # > 2小时标准差
                result['circadian_risk'] = True

    # ---- 最近一晚的入睡潜伏期 ----
    recent_latencies = [r['latency'] for r in records if r['latency'] > 0]
    if recent_latencies:
        avg_latency = sum(recent_latencies[-3:]) / min(len(recent_latencies[-3:]), 3)
        result['avg_latency_minutes'] = round(avg_latency, 1)
        # 入睡困难标记
        result['sleep_onset_difficulty'] = avg_latency > 30

    return result


def _analyze_emotion_baseline(profile):
    """分析情绪基线——从情绪记录中提取模式"""
    result = {
        'has_data': False,
        'current_emotion': 'neutral',
        'mood_trend': 'stable',   # improving | declining | stable
        'anxiety_risk': False,    # 持续焦虑模式
        'emotional_exhaustion': False,  # 情绪耗竭
    }

    # 从profile中的情绪历史
    emotion_history = profile.get('emotion_history', [])
    if not emotion_history:
        # 也可能在局部缓存中有
        return result

    result['has_data'] = True

    # 最新情绪
    latest = emotion_history[-1] if emotion_history else {}
    result['current_emotion'] = latest.get('emotion', 'neutral')
    result['current_score'] = latest.get('score', 0)

    # 近期情绪趋势（最近7条）
    recent = emotion_history[-7:] if len(emotion_history) >= 7 else emotion_history
    if recent:
        scores = [e.get('score', 0) for e in recent]
        avg_score = sum(scores) / len(scores)
        result['recent_avg_score'] = round(avg_score, 2)

        if len(scores) >= 3:
            first_3 = sum(scores[:3]) / 3
            last_3 = sum(scores[-3:]) / 3
            diff = last_3 - first_3
            if diff < -0.5:
                result['mood_trend'] = 'declining'
            elif diff > 0.5:
                result['mood_trend'] = 'improving'
            else:
                result['mood_trend'] = 'stable'

        # 焦虑检测：最近7条中超过40%是焦虑
        anxiety_count = sum(1 for e in recent if e.get('emotion') == 'anxiety')
        if len(recent) >= 5 and anxiety_count / len(recent) >= 0.4:
            result['anxiety_risk'] = True

        # 情绪耗竭：连续负面且强度高
        recent_scores = [e.get('score', 0) for e in recent]
        consecutive_negative = 0
        for s in recent_scores:
            if s < 0:
                consecutive_negative += 1
            else:
                consecutive_negative = 0
        if consecutive_negative >= 4:
            result['emotional_exhaustion'] = True

    return result


def _assess_recovery(physiological, rhythm, emotional):
    """综合评估恢复状态"""
    result = {
        'status': 'unknown',    # sufficient | insufficient | at_risk
        'score_estimate': 50,   # 综合恢复评分
        'primary_concern': None,
        'suggested_mode': None,  # chat | companion | quiet | coach
    }

    signals = {'negative': 0, 'positive': 0}

    # 睡眠层面
    if rhythm.get('has_data'):
        if rhythm.get('sleep_deprivation_risk'):
            signals['negative'] += 2
            result['primary_concern'] = 'sleep_deprivation'
        if rhythm.get('circadian_risk'):
            signals['negative'] += 1
            if result['primary_concern'] is None:
                result['primary_concern'] = 'circadian_disruption'
        if rhythm.get('sleep_debt') == 'severe':
            signals['negative'] += 2
        elif rhythm.get('sleep_debt') == 'moderate':
            signals['negative'] += 1
        if rhythm.get('avg_duration_minutes', 0) >= 420:
            signals['positive'] += 1
        if rhythm.get('bedtime_consistency') == 'regular':
            signals['positive'] += 1

    # 情绪层面
    if emotional.get('has_data'):
        if emotional.get('anxiety_risk'):
            signals['negative'] += 2
            result['primary_concern'] = 'anxiety'
        if emotional.get('emotional_exhaustion'):
            signals['negative'] += 2
            result['primary_concern'] = 'emotional_exhaustion'
        if emotional.get('mood_trend') == 'improving':
            signals['positive'] += 1
        if emotional.get('recent_avg_score', 0) > 0.5:
            signals['positive'] += 1

    # 生理即时状态
    if physiological.get('is_resting'):
        signals['positive'] += 1
    if physiological.get('in_companion'):
        signals['positive'] += 1  # 已经在陪伴模式了，是好事

    net = signals['positive'] - signals['negative']

    if net >= 1:
        result['status'] = 'sufficient'
        result['score_estimate'] = 60 + net * 8
    elif net >= -1:
        result['status'] = 'insufficient'
        result['score_estimate'] = 40 + net * 10
    else:
        result['status'] = 'at_risk'
        result['score_estimate'] = max(15, 35 + net * 8)

    # 行动模式建议
    concern = result.get('primary_concern')
    if concern == 'anxiety' or concern == 'emotional_exhaustion':
        result['suggested_mode'] = 'companion'  # 情绪问题优先陪伴
    elif concern == 'sleep_deprivation':
        result['suggested_mode'] = 'coach'  # 缺觉出教练建议
    elif concern == 'circadian_disruption':
        result['suggested_mode'] = 'coach'
    elif net < 0:
        result['suggested_mode'] = 'chat'
    else:
        result['suggested_mode'] = 'quiet'  # 状态好 → 别打扰

    result['score_estimate'] = max(10, min(100, result['score_estimate']))

    return result


def _get_activity_level(profile, events):
    """评估近期活跃度"""
    result = {
        'has_data': False,
        'last_active': None,
        'hours_since_last': 999,
        'session_count_today': 0,
    }

    now = time.time()
    activity_times = []

    # 从events中提取最近活跃时间
    for ev in events:
        if ev['type'] == 'chat_activity':
            ts = ev.get('ts_epoch', 0)
            if ts:
                activity_times.append(ts)

    if activity_times:
        latest_activity = max(activity_times)
        result['last_active'] = datetime.fromtimestamp(latest_activity).isoformat()
        result['hours_since_last'] = round((now - latest_activity) / 3600, 1)
        result['has_data'] = True

        # 今日会话数
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        result['session_count_today'] = sum(1 for t in activity_times if t >= today_start)

    return result


def _format_duration(seconds):
    """将秒数格式化为可读字符串"""
    if seconds < 60:
        return f'{int(seconds)}秒'
    minutes = seconds / 60
    if minutes < 60:
        return f'{int(minutes)}分钟'
    hours = minutes / 60
    return f'{int(hours)}小时{int(minutes % 60)}分钟'


def render_body_context_text(context):
    """将body context渲染为自然语言文本，供prompt注入使用。

    SCAN启示：身体状态作为AI回复的"生理背景"，而非额外功能。
    """
    if not context.get('available'):
        return ''

    parts = ['[当前身体状态]']
    phys = context.get('physiological', {})
    rhythm = context.get('sleep_rhythm', {})
    emotion = context.get('emotional_baseline', {})
    recovery = context.get('recovery_state', {})

    # 恢复状态一行
    status_map = {
        'sufficient': '✅ 恢复状态良好',
        'insufficient': '⚠️ 恢复状态不足',
        'at_risk': '🔴 需要关注',
        'unknown': '❓ 数据不足',
    }
    status_text = status_map.get(recovery.get('status', 'unknown'), '未知')
    parts.append(f'恢复评估: {status_text}')

    # 睡眠节律 + 昼夜节律相位
    if rhythm.get('has_data'):
        bt = rhythm.get('typical_bedtime', '未知')
        avg_dur = rhythm.get('avg_duration_minutes', 0)
        dur_text = f'{avg_dur/60:.1f}小时' if avg_dur else '未知'
        parts.append(f'典型入睡: {bt} | 平均时长: {dur_text} | 规律性: {rhythm.get("bedtime_consistency", "未知")}')

        if rhythm.get('sleep_deprivation_risk'):
            parts.append('⚠️ 连续多天睡眠不足')
        if rhythm.get('circadian_risk'):
            parts.append('⚠️ 作息不规律')

    # 昼夜节律相位（v3.0: 从稳态回路读取的时间感知）
    try:
        openid = context.get('_openid', 'default')
        from homeostatic_circuit import get_circuit_context
        circ_ctx = get_circuit_context(openid)
        drowsiness = circ_ctx.get('drowsiness')
        drift = circ_ctx.get('circadian_drift')
        in_window = circ_ctx.get('in_bedtime_window')

        if drowsiness:
            now_h = datetime.now().hour
            now_min = datetime.now().minute
            time_str = f'{now_h:02d}:{now_min:02d}'

            if drowsiness == 'high':
                parts.append(f'🌙 当前时间{time_str}，困意偏高')
                if in_window:
                    parts.append('⏰ 处于最佳就寝窗口')
            elif drowsiness == 'low' and 21 <= now_h or now_h <= 6:
                parts.append(f'🧠 当前时间{time_str}，精神较清醒')
            elif drowsiness == 'moderate':
                parts.append(f'当前时间{time_str}，处于日常清醒状态')

            if drift:
                drift_label = {'severe': '显著后移', 'moderate': '轻微后移', 'stable': '稳定'}.get(drift, '稳定')
                if drift in ('severe', 'moderate'):
                    parts.append(f'⚠️ 作息时间正在{drift_label}')
    except (ImportError, Exception):
        pass

    # 情绪基线
    if emotion.get('has_data'):
        mood_text = {
            'improving': '正在改善',
            'declining': '持续下滑',
            'stable': '平稳',
        }.get(emotion.get('mood_trend', 'stable'), '稳定')
        parts.append(f'情绪趋势: {mood_text} | 当前: {emotion.get("current_emotion", "neutral")}')

        if emotion.get('anxiety_risk'):
            parts.append('🔴 持续焦虑模式')
        if emotion.get('emotional_exhaustion'):
            parts.append('🔴 情绪耗竭信号')

    # 生理状态（如果有）
    if phys.get('in_companion'):
        parts.append(f'🧘 陪伴模式进行中({phys.get("companion_state", "?")})')

    if phys.get('is_resting'):
        parts.append(f'😴 已安静{phys.get("quiet_minutes", 0)}分钟')

    # 行动建议
    suggested = recovery.get('suggested_mode')
    if suggested:
        mode_map = {
            'companion': '🧘 建议开启陪伴模式放松',
            'coach': '📋 建议出睡眠改善建议',
            'chat': '💬 建议聊天倾听',
            'quiet': '🤫 状态良好，保持安静',
        }
        if suggested in mode_map:
            parts.append(mode_map[suggested])

    return '\n'.join(parts)


# ==================== 模块自测 ====================
def _self_test():
    """简单的自测：验证基本流程不报错"""
    test_openid = '_test_body_ctx'
    report_body_event(test_openid, 'companion_start', {'state': 'CALMING'})
    report_body_event(test_openid, 'companion_movement', {})
    report_body_event(test_openid, 'emotion_detected', {'emotion': 'anxiety', 'score': -1})

    ctx = get_body_context(test_openid)
    assert isinstance(ctx, dict), 'body context must be dict'
    assert 'physiological' in ctx, 'must have physiological'
    assert 'sleep_rhythm' in ctx, 'must have sleep_rhythm'
    assert 'recovery_state' in ctx, 'must have recovery_state'

    text = render_body_context_text(ctx)
    assert isinstance(text, str), 'rendered text must be string'

    print('[BodyCtx] Self-test PASS')
    ctx_preview = json.dumps(ctx, ensure_ascii=False, indent=2)[:500]
    print(f'[BodyCtx] Sample context: {ctx_preview[:200]}...')
    print('[BodyCtx] Rendered text bytes:', len(text.encode('utf-8')), 'chars:', len(text))


if __name__ == '__main__':
    _self_test()
