#!/usr/bin/env python3
"""隔离测试：cache_layer 回写逻辑 — _handle_decision_quality 改动验证"""
import sys, os, json

# 模拟 cache_layer 的核心行为
PROFILE_CACHE = {}

def set_cached_profile(openid, profile):
    old = PROFILE_CACHE.get(openid, {})
    merged = dict(old)
    merged.update(profile)
    PROFILE_CACHE[openid] = merged

def get_cached_profile(openid):
    return PROFILE_CACHE.get(openid, {})

_openid = 'test_dq_user'
_now = '2026-06-02T09:40:00'

# === 第1次调用：初始化 clarity ===
print('=== Test 1: First call (init clarity) ===')
_existing = get_cached_profile(_openid) or {}
_clarity = dict(_existing.get('clarity', {}))
_clarity['last_decision_quality'] = 'strong'
_clarity['last_confidence'] = 0.82
_clarity['last_mental_load'] = 30
_clarity['last_checked'] = _now
_history = list(_clarity.get('history', []))
_history.append({'quality': 'strong', 'confidence': 0.82, 'mental_load': 30, 'timestamp': _now})
_clarity['history'] = _history[-7:]
_existing['clarity'] = _clarity
set_cached_profile(_openid, _existing)

p = get_cached_profile(_openid)
assert 'clarity' in p, 'clarity key missing'
assert len(p['clarity']['history']) == 1, f'expected 1 history entry, got {len(p["clarity"]["history"])}'
assert p['clarity']['last_decision_quality'] == 'strong'
print('  PASS: clarity created, 1 history entry')

# === 第2次调用：追加 history ===
_now2 = '2026-06-02T10:00:00'
print('=== Test 2: Second call (append history) ===')
_existing2 = get_cached_profile(_openid) or {}
_clarity2 = dict(_existing2.get('clarity', {}))
_clarity2['last_decision_quality'] = 'moderate'
_clarity2['last_confidence'] = 0.55
_clarity2['last_mental_load'] = 60
_clarity2['last_checked'] = _now2
_history2 = list(_clarity2.get('history', []))
_history2.append({'quality': 'moderate', 'confidence': 0.55, 'mental_load': 60, 'timestamp': _now2})
_clarity2['history'] = _history2[-7:]
_existing2['clarity'] = _clarity2
set_cached_profile(_openid, _existing2)

p2 = get_cached_profile(_openid)
assert len(p2['clarity']['history']) == 2, f'expected 2 history entries, got {len(p2["clarity"]["history"])}'
assert p2['clarity']['history'][0]['quality'] == 'strong'
assert p2['clarity']['history'][1]['quality'] == 'moderate'
assert p2['clarity']['last_decision_quality'] == 'moderate'
print('  PASS: history appended, 2 entries')

# === 第3次调用：历史截断到7条 ===
print('=== Test 3: History truncation (max 7) ===')
for i in range(10):
    _existing = get_cached_profile(_openid) or {}
    _cl = dict(_existing.get('clarity', {}))
    _cl['last_decision_quality'] = 'avoid'
    _h = list(_cl.get('history', []))
    _h.append({'quality': 'avoid', 'confidence': 0.3, 'mental_load': 80, 'timestamp': f'2026-06-02T{i+11}:00:00'})
    _cl['history'] = _h[-7:]
    _existing['clarity'] = _cl
    set_cached_profile(_openid, _existing)

p3 = get_cached_profile(_openid)
assert len(p3['clarity']['history']) == 7, f'expected 7 history entries, got {len(p3["clarity"]["history"])}'
print(f'  PASS: history truncated to 7 entries')

# === 第4次调用：其他字段不丢失 ===
print('=== Test 4: Other profile fields preserved ===')
_existing4 = get_cached_profile(_openid) or {}
_existing4['name'] = '至尊宝'
_existing4['preferences'] = {'theme': 'dark', 'language': 'zh'}
_existing4['latest'] = {'total_score': 72}
set_cached_profile(_openid, _existing4)

_cl4 = dict(_existing.get('clarity', {}))  # 空修改
_existing4b = get_cached_profile(_openid)  # 拿回完整 profile
assert _existing4b.get('name') == '至尊宝', 'name field lost'
assert _existing4b.get('preferences', {}).get('theme') == 'dark', 'preferences lost'
assert _existing4b.get('latest', {}).get('total_score') == 72, 'latest lost'
print('  PASS: name, preferences, latest all preserved')

print()
print('=== ALL TESTS PASSED ===')
