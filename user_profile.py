#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
user_profile.py — 用户画像管理模块（从 deepseek_proxy.py 拆出）
职责：用户数据的加载/保存/缓存/默认画像
"""
import os, json, time, threading, datetime
from copy import deepcopy
from config import DATA_DIR, USER_PROFILE_FILE

# ============================================================
# 缓存
# ============================================================
_PROFILE_CACHE: dict = {}
_PROFILE_CACHE_TIME: float = 0
_PROFILE_CACHE_TTL: int = 60  # 秒
_write_lock = threading.Lock()


# ============================================================
# 默认画像
# ============================================================
def get_default_profile() -> dict:
    """返回一个全新的默认用户画像"""
    return {
        'meta_params': {
            'anti_aging_level': 0, 'circadian_level': 0,
            'sleep_quality_level': 0, 'emotional_support_level': 0,
            'glymphatic_level': 0, 'cognitive_level': 0,
            'curation_effort': 0.5, 'self_disclosure': 0.5,
            'inference_boldness': 0.5, 'emotional_expression': 0.5,
            'history_delta_hours': 4, 'depth_mm': 0.0,
            'target_wake_min': 300, 'sleep_latency_default': 30,
            'backup_total_sleep': 420, 'awake_times_default': 1,
        },
        'preferences': {
            'known_nightmare_themes': [], 'preferred_music_genres': [],
            'disliked_music_genres': [], 'preferred_voice': '默认',
            'known_trauma_triggers': [], 'known_sleep_aids': [],
            'preferred_playlist': '',
        },
        'user_info': {
            'username': '', 'age': '', 'gender': '', 'main_issue': '',
            'medications': '', 'known_conditions': [],
        },
        'behavior_stats': {
            'total_relax_sessions': 0, 'common_emotions': [],
            'preferred_relax_type': '', 'peak_usage_hour': 0,
            'total_feedback_count': 0, 'feedback_positive_ratio': 0.0,
            'last_feedback_date': '',
        },
        'conversation_summaries': [],
        'latest': {},
        'history': [],
        'emotion_timeline': [],
        'user_conditions': [],
        'created_at': datetime.datetime.now().isoformat(),
    }


# ============================================================
# 文件读写
# ============================================================
def load_all_profiles() -> dict:
    """从磁盘加载全部用户画像"""
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(USER_PROFILE_FILE) and os.path.getsize(USER_PROFILE_FILE) > 5:
        try:
            with open(USER_PROFILE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f'[Profile] 加载失败: {e}，返回空')
    return {}


def save_all_profiles(profiles: dict) -> None:
    """保存全部用户画像到磁盘"""
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = USER_PROFILE_FILE + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
        os.replace(tmp, USER_PROFILE_FILE)
    except Exception as e:
        print(f'[Profile] 保存失败: {e}')


def invalidate_cache(openid: str | None = None) -> None:
    """使指定用户（或全部）的缓存失效"""
    global _PROFILE_CACHE_TIME
    if openid:
        _PROFILE_CACHE.pop(openid, None)
    else:
        _PROFILE_CACHE.clear()
        _PROFILE_CACHE_TIME = 0


# ============================================================
# 单用户操作
# ============================================================
def load_user_profile(openid: str = 'default') -> dict:
    """加载指定用户的画像（带内存缓存）"""
    global _PROFILE_CACHE_TIME
    now = time.time()
    if now - _PROFILE_CACHE_TIME < _PROFILE_CACHE_TTL and openid in _PROFILE_CACHE:
        return _PROFILE_CACHE[openid]
    all_profiles = load_all_profiles()
    if openid not in all_profiles:
        print(f'[ProfileCreate] 新用户 {openid}')
        all_profiles[openid] = get_default_profile()
        save_all_profiles(all_profiles)
    profile = all_profiles[openid]
    _PROFILE_CACHE[openid] = profile
    _PROFILE_CACHE_TIME = now
    if 'meta_params' not in profile:
        default = get_default_profile()
        profile['meta_params'] = deepcopy(default['meta_params'])
    return profile


def save_user_profile(profile: dict, openid: str = 'default') -> None:
    """保存指定用户的画像
    
    参数顺序: save_user_profile(PROFILE, OPENID) - profile在前，openid在后。
    """
    assert isinstance(profile, dict), (
        f'save_user_profile: profile必须是dict，收到{type(profile).__name__}'
    )
    assert isinstance(openid, str), (
        f'save_user_profile: openid必须是str，收到{type(openid).__name__}'
    )
    with _write_lock:
        all_profiles = load_all_profiles()
        all_profiles[openid] = profile
        save_all_profiles(all_profiles)
    invalidate_cache(openid)


def get_conversation_summaries(openid: str = 'default') -> list:
    """获取用户的对话摘要列表"""
    profile = load_user_profile(openid)
    return profile.get('conversation_summaries', [])


def append_conversation_summary(openid: str, summary: dict) -> None:
    """追加一条对话摘要"""
    profile = load_user_profile(openid)
    summaries = profile.setdefault('conversation_summaries', [])
    summaries.append(summary)
    if len(summaries) > 50:
        profile['conversation_summaries'] = summaries[-50:]
    save_user_profile(profile, openid)
