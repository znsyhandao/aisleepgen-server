#!/usr/bin/env python3
"""
meditation_recommend.py — 眠小兔冥想推荐引擎
基于手环数据+用户情绪标签+使用历史，智能推荐冥想
"""
import json, os
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

def load_history(openid):
    """加载用户冥想历史"""
    path = os.path.join(DATA_DIR, f'meditation_history_{openid}.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"sessions": [], "streak": 0, "last_date": "", "total_minutes": 0}

def save_history(openid, history):
    path = os.path.join(DATA_DIR, f'meditation_history_{openid}.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def record_session(openid, series_id, item_id, title, duration_seconds, completed=True):
    """记录一次冥想会话"""
    history = load_history(openid)
    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    
    entry = {
        "series_id": series_id,
        "item_id": item_id,
        "title": title,
        "timestamp": now.isoformat(),
        "duration": duration_seconds,
        "completed": completed,
    }
    history["sessions"].append(entry)
    
    # 限制会话数量
    if len(history["sessions"]) > 500:
        history["sessions"] = history["sessions"][-500:]
    
    # 连续天数
    if history["last_date"] == today:
        pass  # 今天已记过
    elif history["last_date"] == (now - timedelta(days=1)).strftime('%Y-%m-%d'):
        history["streak"] += 1
    elif history["last_date"] != today:
        history["streak"] = 1
    
    history["last_date"] = today
    history["total_minutes"] = history.get("total_minutes", 0) + duration_seconds // 60
    
    save_history(openid, history)
    return history

def get_recommendation(openid, mood=None):
    """获取推荐冥想
    
    mood: 'sleep' | 'anxiety' | 'focus' | 'energy' | 'stress' | 'general'
    如果不传，根据手环数据自动判断
    """
    from meditation_content import SERIES_TAGS, SERIES_INDEX, get_recommendation_by_mood
    
    # 1. 看有没有手环数据
    huawei_mood = None
    try:
        profile_path = os.path.join(DATA_DIR, f'user_profile_{openid}.json')
        if os.path.exists(profile_path):
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile = json.load(f)
            device = profile.get('devices', {}).get('huawei_band', {}).get('last_sleep_data', {})
            if device:
                total = device.get('total_min', 0)
                deep = device.get('deep_min', 0)
                hrv = device.get('hrv_avg', 0)
                
                if total and total < 360:  # 不足6小时
                    huawei_mood = 'sleep'
                elif deep and deep < 60:  # 深睡不足1小时
                    huawei_mood = 'sleep'
                elif hrv and hrv < 20:  # HRV偏低→压力大
                    huawei_mood = 'stress'
                elif hrv and hrv > 60:  # HRV偏高→可能疲劳
                    huawei_mood = 'energy'
    except Exception:
        pass
    
    effective_mood = mood or huawei_mood or 'general'
    recommended = get_recommendation_by_mood(effective_mood)
    
    # 2. 看历史，排除最近做过的系列
    history = load_history(openid)
    recent_series = set()
    for s in history.get("sessions", [])[-5:]:
        recent_series.add(s.get("series_id"))
    
    # 优先推荐没做过的
    fresh = [r for r in recommended if r["id"] not in recent_series]
    if fresh:
        recommended = fresh + [r for r in recommended if r["id"] in recent_series]
    
    return {
        "mood": effective_mood,
        "reason": _reason_text(effective_mood, huawei_mood),
        "recommendations": recommended[:6],
        "history": {
            "streak": history.get("streak", 0),
            "total_minutes": history.get("total_minutes", 0),
            "sessions_today": sum(1 for s in history.get("sessions", [])
                                  if s.get("timestamp","").startswith(datetime.now().strftime('%Y-%m-%d'))),
        }
    }

def _reason_text(mood, from_band):
    reasons = {
        'sleep': '昨晚睡眠质量分析表明你可能需要助眠引导',
        'anxiety': '检测到压力指标偏高，推荐焦虑消解系列',
        'focus': '专注力有待提升，软能力冥想正在等你',
        'energy': '能量水平偏低，充能冥想帮你恢复活力',
        'stress': 'HRV数据显示你处于压力状态，减压冥想正合适',
        'general': '为你推荐眠小兔精选冥想',
        'sleep_band': '手环数据显示深睡不足，试试助眠冥想',
        'stress_band': '心率变异数据显示压力偏高，减压冥想安排上了',
    }
    if from_band and mood == 'sleep':
        return reasons.get('sleep_band', reasons.get(mood, ''))
    if from_band and mood == 'stress':
        return reasons.get('stress_band', reasons.get(mood, ''))
    return reasons.get(mood, '为你推荐')
