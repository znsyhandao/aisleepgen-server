# push_enhancer.py v1.0 — 推送内容增强引擎
# 替代 wechat_push 生成的纯文本推送
# 把 sieg/diary/audio/ring 数据注入推送内容

import os, json, time
from datetime import datetime

PROJECT_ROOT = r'D:\AISleepGen_Optimized'


def enhance_morning_push(openid, profile, original_title, original_content):
    """增强早间推送：注入自动日记 + 手环数据 + 偏差检测"""
    try:
        from auto_diary import AutoDiary, format_diary_short
        
        ad = AutoDiary()
        diary = ad.generate_diary(openid)
        short = format_diary_short(diary)
        
        # 用自动日记替代原始内容
        return short, 'morning_recap'
    except Exception as e:
        pass
    
    # 保底：如果siege/diary挂了，回到原始内容
    return original_content, 'morning_recap'


def enhance_evening_push(openid, profile, original_title, original_content):
    """增强晚间推送：注入siege预判"""
    try:
        from sleep_siege_engine import SiegePredictor, format_siege_report
        
        sp = SiegePredictor()
        pred = sp.predict(openid)
        report = format_siege_report(pred)
        
        return report, 'evening_siege'
    except Exception as e:
        pass
    
    return original_content, 'evening_care'


def generate_alert_content(openid, profile, alert_type='score_drop', extra=None):
    """生成异常推送（非时段推送）
    
    Args:
        alert_type: 'score_drop' | 'anomaly_detected' | 'ring_sync' | 'audio_issue'
    """
    from wechat_push import generate_alert_content as _legacy_alert
    from auto_diary import AutoDiary

    if alert_type == 'score_drop':
        # 评分骤降 -> 触发诊断书
        try:
            from sleep_diagnosis import SleepDiagnosis
            sd = SleepDiagnosis()
            diag = sd.generate(openid)
            score = diag.get('composite_score', 50)
            trend = diag.get('metrics', {}).get('direction', 'stable')
            if trend == 'declining' or score < 40:
                title = f'⚠️ 睡眠质量下降告警'
                content = f'综合评分 {score}/100，持续下降。建议今晚提前放松，或做一次完整诊断。'
                return title, content, 'alert'
        except Exception:
            pass

    elif alert_type == 'anomaly_detected':
        # 检测到异常模式
        try:
            from behavior_predictor import BehaviorPredictor
            bp = BehaviorPredictor()
            anomaly = bp.anomaly_score(openid)
            if anomaly > 0.7:
                title = '🔔 检测到异常状态'
                content = f'近期睡眠模式与历史差异较大（异常指数{anomaly:.0%}）。可能受到外部因素影响，建议记录一下最近的饮食和压力情况。'
                return title, content, 'alert'
        except Exception:
            pass

    elif alert_type == 'ring_sync':
        # 手环有新数据
        try:
            from ring_ocr import get_ring_extractor
            ex = get_ring_extractor()
            known = ex.extract_known_values()
            if known and known.get('sleep_score', 0) > 0:
                score = known['sleep_score']
                deep = known.get('deep_sleep_min', 0)
                total = known.get('total_sleep_min', 0)
                title = '⌚ 手环数据已同步'
                content = f'睡眠评分{score}分，深睡{deep}min/总{total}min'
                return title, content, 'alert'
        except Exception:
            pass

    elif alert_type == 'audio_issue':
        # 音频检测到异常
        try:
            from audio_pomdp_bridge import get_latest_audio_observation
            obs = get_latest_audio_observation(openid)
            if obs:
                raw = obs.get('_raw_audio_obs', {})
                snore = raw.get('snore_pct', 0)
                stability = raw.get('stability', 50)
                if snore > 60:
                    title = '👃 鼾声检测提醒'
                    content = f'昨晚鼾声占比较高（{snore:.0f}%），可能与睡眠呼吸通畅度有关。建议侧卧睡眠。'
                    return title, content, 'alert'
                if stability < 30:
                    title = '🔄 睡眠稳定性偏低'
                    content = f'睡眠稳定性评分较低（{stability}/100），夜间可能频繁翻身或醒转。'
                    return title, content, 'alert'
        except Exception:
            pass

    # fallback到原来的
    return _legacy_alert(profile, alert_type, extra)


# ============ 快捷入口：供 dp_router 调用的推送触发 ============

def push_morning(openid, profile):
    """执行早间推送"""
    from wechat_push import generate_morning_content, send_subscribe_message
    from scheduler_daemon import _load_push_queue, _save_push_queue
    import time

    # 生成原始内容（保底）
    original = generate_morning_content(profile)
    if original is None:
        return False
    
    original_title, original_content, push_type = original
    
    # 用siege增强
    enhanced_content, enhanced_type = enhance_morning_push(openid, profile, original_title, original_content)
    
    # 尝试发送
    template_id = ''
    result = send_subscribe_message(openid, template_id, {
        'thing1': '睡眠日记',
        'thing2': enhanced_content[:50],
    }, page='pages/index/index')
    
    success = result.get('success', False)
    
    # 记录到推送队列
    entry = {
        'id': f'{openid}_morning_{int(time.time())}',
        'openid': openid,
        'title': '☀️ 睡眠日记',
        'content': enhanced_content,
        'push_type': enhanced_type,
        'strategy': 'morning_siege',
        'reason': 'morning_window',
        'pushed_at': time.time(),
        'expires_at': time.time() + 48 * 3600,
        'sent': success,
        'send_result': result.get('errmsg', ''),
    }
    queue = _load_push_queue() if success else []
    if success:
        queue.append(entry)
        _save_push_queue(queue)
    
    return success


def push_evening(openid, profile):
    """执行晚间推送"""
    from wechat_push import generate_evening_content, send_subscribe_message
    from scheduler_daemon import _load_push_queue, _save_push_queue
    import time

    original = generate_evening_content(profile)
    if original is None:
        return False
    
    original_title, original_content, push_type = original
    
    enhanced_content, enhanced_type = enhance_evening_push(openid, profile, original_title, original_content)
    
    template_id = ''
    result = send_subscribe_message(openid, template_id, {
        'thing1': '睡前关怀',
        'thing2': enhanced_content[:50],
    }, page='pages/index/index')
    
    success = result.get('success', False)
    
    entry = {
        'id': f'{openid}_evening_{int(time.time())}',
        'openid': openid,
        'title': '🌙 睡前预判',
        'content': enhanced_content,
        'push_type': enhanced_type,
        'strategy': 'evening_siege',
        'reason': 'evening_window',
        'pushed_at': time.time(),
        'expires_at': time.time() + 48 * 3600,
        'sent': success,
        'send_result': result.get('errmsg', ''),
    }
    queue = _load_push_queue() if success else []
    if success:
        queue.append(entry)
        _save_push_queue(queue)
    
    return success
