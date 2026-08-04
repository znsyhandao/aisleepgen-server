#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cache_layer.py — AISleepGen 推理缓存层

目标：将 /api/chat 响应延迟从 15~30s 降至 <2s（命中时）。

策略：
  1. 世界模型结果缓存（L1: 同用户最近10条 / L2: 语义模板命中）
  2. DeepSeek API 结果缓存（同用户同 query 的回复缓存）
  3. Profile 写入合并（延迟写，不每次请求都写磁盘）
  4. Profile 内存缓存（避免每次请求都读磁盘）

不碰 sleep_world_model.py 一行。
"""

import os
import json
import time
import hashlib
import threading
import logging
from collections import OrderedDict

_log = logging.getLogger('aisleepgen.cache')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(PROJECT_ROOT, 'data', 'cache')

# ===== 内存缓存 =====
_WM_CACHE = OrderedDict()      # {key: {result, ts, ttl}}
_DS_CACHE = OrderedDict()      # {key: {reply, ts, ttl}}
_PROFILE_CACHE = {}            # {openid: {profile, dirty, ts}}
_PROFILE_LOCK = threading.RLock()

# ===== 配置 =====
WM_CACHE_SIZE = 200           # 最多缓存200条世界模型结果
WM_CACHE_TTL = 3600 * 4       # 4小时过期
DS_CACHE_SIZE = 300           # 最多缓存300条DeepSeek结果
DS_CACHE_TTL = 3600 * 2       # 2小时过期
PROFILE_CACHE_TTL = 600       # profile 内存缓存10分钟
PROFILE_FLUSH_INTERVAL = 5    # 延迟写入最多5秒

_PROFILE_DIRTY_FLAG = {}       # {openid: timestamp}


# ===== 初始化 =====
def _init():
    os.makedirs(CACHE_DIR, exist_ok=True)
    # 加载持久化缓存
    _load_persistent_cache('wm_cache.json', _WM_CACHE)
    _load_persistent_cache('ds_cache.json', _DS_CACHE)
    # 启动延迟写入线程
    _start_flush_thread()


def _load_persistent_cache(filename, target_dict):
    """从磁盘加载持久化缓存"""
    path = os.path.join(CACHE_DIR, filename)
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                target_dict.update(data)
                _log.info('[Cache] Loaded %d entries from %s', len(data), filename)
    except Exception as e:
        _log.warning('[Cache] Failed to load %s: %s', filename, e)


def _save_persistent_cache(filename, source_dict, max_entries=500):
    """持久化缓存到磁盘（异步，不阻塞主线程）"""
    path = os.path.join(CACHE_DIR, filename)
    try:
        # 只保留最新的 N 条
        items = list(source_dict.items())[-max_entries:]
        data = {k: v for k, v in items}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        _log.warning('[Cache] Failed to save %s: %s', filename, e)


def _start_flush_thread():
    """启动后台刷盘线程"""
    def _flush_loop():
        while True:
            time.sleep(PROFILE_FLUSH_INTERVAL)
            _flush_dirty_profiles()
            # 定期持久化缓存
            if int(time.time()) % 60 == 0:
                _save_persistent_cache('wm_cache.json', _WM_CACHE)
                _save_persistent_cache('ds_cache.json', _DS_CACHE)

    t = threading.Thread(target=_flush_loop, daemon=True, name='cache-flusher')
    t.start()


# ===== 世界模型缓存 =====

def _make_wm_key(openid, message, history_hash=''):
    """生成世界模型缓存键

    基于用户ID + 消息 + 最近历史hash
    """
    raw = f'{openid}_{message.strip()[:200]}_{history_hash}'
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def get_wm_cache(openid, message, history_hash=''):
    """获取世界模型缓存

    Returns:
        dict or None: 缓存的世界模型结果
    """
    key = _make_wm_key(openid, message, history_hash)
    with _PROFILE_LOCK:
        entry = _WM_CACHE.get(key)
    if entry and (time.time() - entry.get('ts', 0)) < WM_CACHE_TTL:
        _log.info('[Cache] WM HIT for %s (%.1fs old)', openid[:8], time.time() - entry['ts'])
        return entry.get('result')
    return None


def set_wm_cache(openid, message, result, history_hash=''):
    """写入世界模型缓存"""
    key = _make_wm_key(openid, message, history_hash)
    entry = {
        'result': result,
        'ts': time.time(),
        'ttl': WM_CACHE_TTL,
        'openid': openid[:8],
    }
    with _PROFILE_LOCK:
        _WM_CACHE[key] = entry
        while len(_WM_CACHE) > WM_CACHE_SIZE:
            _WM_CACHE.popitem(last=False)


def invalidate_wm_cache(openid):
    """失效指定用户的缓存（用户有新数据时调用）"""
    with _PROFILE_LOCK:
        keys_to_del = [k for k, v in _WM_CACHE.items()
                       if v.get('openid') == openid[:8]]
        for k in keys_to_del:
            _WM_CACHE.pop(k, None)
    if keys_to_del:
        _log.info('[Cache] Invalidated %d WM entries for %s', len(keys_to_del), openid[:8])


# ===== DeepSeek API 缓存 =====

def _make_ds_key(openid, message):
    """生成DeepSeek缓存键"""
    raw = f'{openid}_{message.strip()[:200]}'
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def get_ds_cache(openid, message):
    """获取DeepSeek API缓存

    Returns:
        str or None: 缓存的回复
    """
    key = _make_ds_key(openid, message)
    with _PROFILE_LOCK:
        entry = _DS_CACHE.get(key)
    if entry and (time.time() - entry.get('ts', 0)) < DS_CACHE_TTL:
        _log.info('[Cache] DS HIT for %s (%.1fs old)', openid[:8], time.time() - entry['ts'])
        return entry.get('reply')
    return None


def set_ds_cache(openid, message, reply):
    """写入DeepSeek缓存"""
    if not reply or len(reply) < 20:
        return
    key = _make_ds_key(openid, message)
    entry = {
        'reply': reply,
        'ts': time.time(),
        'ttl': DS_CACHE_TTL,
        'openid': openid[:8],
    }
    with _PROFILE_LOCK:
        _DS_CACHE[key] = entry
        while len(_DS_CACHE) > DS_CACHE_SIZE:
            _DS_CACHE.popitem(last=False)


# ===== Profile 内存缓存 + 延迟写入 =====

def get_cached_profile(openid):
    """获取缓存的用户画像（优先内存，miss才读磁盘）

    相比每次 request 都读磁盘，大幅减少 I/O。

    Returns:
        dict or None
    """
    with _PROFILE_LOCK:
        entry = _PROFILE_CACHE.get(openid)
        if entry:
            # 检查是否过期
            if (time.time() - entry.get('ts', 0)) < PROFILE_CACHE_TTL:
                return entry.get('profile')

    # Cache miss or expired -> 读磁盘
    try:
        from profile_storage import _load_user_profile
        profile = _load_user_profile(openid)
        with _PROFILE_LOCK:
            _PROFILE_CACHE[openid] = {
                'profile': profile,
                'ts': time.time(),
                'dirty': False,
            }
        _log.info('[Cache] Profile cache MISS for %s (disk read)', openid[:8])
        return profile
    except Exception as e:
        _log.warning('[Cache] Profile load error: %s', e)
        return {}


def mark_profile_dirty(openid):
    """标记用户画像为已修改，待延迟写入"""
    with _PROFILE_LOCK:
        entry = _PROFILE_CACHE.get(openid)
        if entry:
            entry['dirty'] = True
            entry['ts'] = time.time()
        _PROFILE_DIRTY_FLAG[openid] = time.time()


def set_cached_profile(openid, profile):
    """设置内存中的画像（标记为dirty，延迟写入磁盘）"""
    # 写入内存
    with _PROFILE_LOCK:
        old_entry = _PROFILE_CACHE.get(openid, {})
        old_profile = old_entry.get('profile', {}) if old_entry else {}

        # 合并（保留profile内已有字段，只更新传入的）
        if isinstance(old_profile, dict) and isinstance(profile, dict):
            merged = dict(old_profile)
            merged.update(profile)
        else:
            merged = profile if isinstance(profile, dict) else {}

        _PROFILE_CACHE[openid] = {
            'profile': merged,
            'ts': time.time(),
            'dirty': True,
        }
    mark_profile_dirty(openid)


def flush_profile(openid):
    """立即刷入某个用户的profile到磁盘（不等待延迟写入）"""
    with _PROFILE_LOCK:
        entry = _PROFILE_CACHE.pop(openid, None)
        _PROFILE_DIRTY_FLAG.pop(openid, None)
    if entry and entry.get('dirty'):
        profile = entry.get('profile', {})
        if profile:
            try:
                from profile_storage import _save_user_profile
                _save_user_profile(profile, openid)
                _log.info('[Cache] Flushed profile for %s', openid[:8])
            except Exception as e:
                _log.warning('[Cache] Flush failed for %s: %s', openid[:8], e)


def _flush_dirty_profiles():
    """刷入所有标记为dirty的profile（延迟写入）"""
    with _PROFILE_LOCK:
        dirty_openids = list(_PROFILE_DIRTY_FLAG.keys())

    flushed = 0
    for openid in dirty_openids:
        with _PROFILE_LOCK:
            entry = _PROFILE_CACHE.get(openid)
            if not entry or not entry.get('dirty'):
                _PROFILE_DIRTY_FLAG.pop(openid, None)
                continue
            profile = entry.get('profile', {})
            entry['dirty'] = False

        if profile:
            try:
                from profile_storage import _save_user_profile
                _save_user_profile(profile, openid)
                flushed += 1
            except Exception as e:
                _log.warning('[Cache] Delayed flush failed for %s: %s', openid[:8], e)

        with _PROFILE_LOCK:
            _PROFILE_DIRTY_FLAG.pop(openid, None)

    if flushed > 0:
        _log.info('[Cache] Flushed %d dirty profiles', flushed)


# ===== 全局缓存状态 =====
def get_cache_stats():
    """获取缓存统计信息"""
    return {
        'wm_cache_size': len(_WM_CACHE),
        'ds_cache_size': len(_DS_CACHE),
        'profile_cache_size': len(_PROFILE_CACHE),
        'dirty_profiles': len(_PROFILE_DIRTY_FLAG),
        'wm_ttl_hours': WM_CACHE_TTL / 3600,
        'ds_ttl_hours': DS_CACHE_TTL / 3600,
    }


# ===== init on import =====
_init()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    # Test basic operations
    test_key = 'test_user', '我昨晚只睡了5个小时'

    # WM cache
    set_wm_cache(*test_key, {'total_score': 42, 'quality': 'poor'})
    hit = get_wm_cache(*test_key)
    print('WM cache hit:', hit is not None, 'score:', hit.get('total_score') if hit else 'N/A')

    # DS cache
    set_ds_cache(*test_key, '这是一条测试回复内容...')
    ds_hit = get_ds_cache(*test_key)
    print('DS cache hit:', ds_hit is not None)

    # Profile cache
    profile = get_cached_profile('test_cache_user')
    print('Profile cache (empty):', type(profile).__name__)

    set_cached_profile('test_cache_user', {'test_field': 123})
    profile2 = get_cached_profile('test_cache_user')
    print('Profile cache (cached):', profile2.get('test_field'))

    # Stats
    print('Cache stats:', get_cache_stats())

    print('OK')
