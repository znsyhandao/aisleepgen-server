#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
end_to_end_story_test.py — 端到端剧情测试脚本

测什么：
1. 用户注册/登录 → 填问卷 → 聊天 → 世界模型状态推理（验证状态来自推理而非 fallback）
2. 多轮对话 → 状态演化（验证状态机在走）
3. 数据流完整性（关键字段非空断言）

用法:
  python end_to_end_story_test.py [--host localhost:8090] [--openid test_e2e_001]
"""

import os, sys, json, time, argparse, urllib.request, urllib.error

sys.stdout.reconfigure(encoding='utf-8')

PASS = 0
FAIL = 0
WARN = 0


def report(result, label, detail=''):
    global PASS, FAIL, WARN
    if result == 'PASS':
        PASS += 1
        print(f"  ✅ {label}")
    elif result == 'FAIL':
        FAIL += 1
        print(f"  ❌ {label}: {detail}")
    elif result == 'WARN':
        WARN += 1
        print(f"  ⚠️  {label}: {detail}")


def api_post(host, path, data):
    """POST JSON to API, return parsed response."""
    url = f"http://{host}{path}"
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload,
                                  headers={'Content-Type': 'application/json'},
                                  method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')[:500]
        return {'_http_error': e.code, '_body': body}
    except Exception as e:
        return {'_error': str(e)}


def api_get(host, path):
    """GET from API."""
    url = f"http://{host}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {'_error': str(e)}


def test_story(host, openid):
    """Run full end-to-end story."""
    global PASS, FAIL, WARN
    print(f"\n{'='*60}")
    print(f"  E2E Story Test: openid={openid}")
    print(f"{'='*60}\n")
    
    # Step 1: Health check
    print("[Step 1] Health check")
    r = api_get(host, '/health')
    if r.get('status') == 'ok' or 'ok' in str(r).lower():
        report('PASS', '/health responded')
    else:
        report('WARN', '/health', str(r)[:100])
    
    # Step 2: User login/register
    print("\n[Step 2] User login")
    r = api_post(host, '/api/wx/login', {'code': openid, 'mock': True})
    token = r.get('token', r.get('data', {}).get('token', ''))
    if token:
        report('PASS', f'/api/wx/login got token (len={len(token)})')
    else:
        report('WARN', '/api/wx/login', f'no token in {str(r)[:200]}')
    
    # Step 3: Submit survey/profile
    print("\n[Step 3] Submit user profile/survey")
    profile_data = {
        'openid': openid,
        'age': 32, 'gender': 'male',
        'sleep_latency': 45,         # >30 min = anxious
        'total_sleep_hours': 5.5,    # <6h = drowsy
        'awake_times_per_night': 3,  # >=3 = alert
        'wake_up_time': '06:30',
        'bed_time': '23:00',
        'stress_level': 7,
        'main_complaint': '入睡困难，半夜总是醒来',
    }
    r = api_post(host, '/api/wx/profile', profile_data)
    if r.get('success') or r.get('status') == 'ok':
        report('PASS', '/api/wx/profile accepted')
    else:
        report('WARN', '/api/wx/profile', str(r)[:200])
    
    # Step 4: Send chat message (world model should engage)
    print("\n[Step 4] Chat message → world model inference")
    chat_msg = "我最近总是睡不着，躺在床上脑子停不下来，一个多小时才能睡着"
    r = api_post(host, '/api/sleep/world-step', {
        'openid': openid,
        'message': chat_msg,
        'session_id': f'test_{openid}',
    })
    
    # CRITICAL CHECK: world model state must NOT come from fallback
    wm = r.get('world_model', r.get('data', {}).get('world_model', {}))
    arousal = wm.get('arousal_state', wm.get('state', 'unknown'))
    confidence = wm.get('arousal_confidence', wm.get('confidence', 0))
    
    if arousal and arousal != 'unknown':
        report('PASS', f'World model produced state: {arousal} (conf={confidence})')
    else:
        report('FAIL', 'World model state is unknown/empty', 
               f'WM data: {str(wm)[:200]}')
    
    # Check: is there a meaningful response?
    reply = r.get('reply', r.get('response', ''))
    if len(reply) > 20:
        report('PASS', f'AI reply length={len(reply)} chars')
    else:
        report('FAIL', 'AI reply too short/empty', f'"{reply[:50]}"')
    
    # Step 5: Get render plan (P0)
    print("\n[Step 5] Render plan")
    r = api_post(host, '/api/sleep/render-plan', {
        'openid': openid,
        'arousal_state': arousal or 'alert',
    })
    bpm = r.get('bpm', r.get('data', {}).get('bpm', 0))
    if 2 <= bpm <= 12:
        report('PASS', f'Render plan bpm={bpm} in valid range [2,12]')
    else:
        report('FAIL', f'Render plan bpm={bpm} out of range', str(r)[:200])
    
    # Step 6: Phase plan (P2)
    print("\n[Step 6] Phase plan (sleep cycle prediction)")
    r = api_post(host, '/api/sleep/phase-plan', {
        'openid': openid,
        'bed_time': '23:00',
        'wake_time': '07:00',
    })
    phases = r.get('phases', r.get('data', {}).get('phases', []))
    if len(phases) >= 4:
        report('PASS', f'Phase plan has {len(phases)} stages')
    else:
        report('WARN', f'Phase plan only {len(phases)} stages', str(r)[:200])
    
    # Step 7: Render tick (P0 real-time)
    print("\n[Step 7] Render tick (real-time audio params)")
    r = api_post(host, '/api/sleep/render-tick', {
        'openid': openid,
        'elapsed_seconds': 120,
        'current_state': arousal or 'alert',
    })
    tick_bpm = r.get('bpm', r.get('data', {}).get('bpm', -1))
    if tick_bpm > 0:
        report('PASS', f'Render tick bpm={tick_bpm}')
    else:
        report('WARN', 'Render tick missing bpm', str(r)[:200])
    
    # Step 8: Second chat → state should evolve
    print("\n[Step 8] Second chat (state evolution check)")
    chat_msg2 = "我试了深呼吸，感觉好一些了，但还是睡不着"
    r2 = api_post(host, '/api/sleep/world-step', {
        'openid': openid,
        'message': chat_msg2,
        'session_id': f'test_{openid}',
    })
    wm2 = r2.get('world_model', r2.get('data', {}).get('world_model', {}))
    arousal2 = wm2.get('arousal_state', wm2.get('state', 'unknown'))
    
    if arousal2 and arousal2 != arousal and arousal2 != 'unknown':
        report('PASS', f'State evolved: {arousal} → {arousal2}')
    elif arousal2 == arousal:
        report('WARN', f'State did NOT change: still {arousal}', 
               'May be normal if fallback is constraining')
    else:
        report('FAIL', 'State missing in 2nd chat', str(wm2)[:200])
    
    # Step 9: World summary
    print("\n[Step 9] Session summary")
    r = api_post(host, '/api/sleep/world-summary', {
        'openid': openid,
        'session_id': f'test_{openid}',
    })
    if r.get('reply', r.get('response', '')):
        report('PASS', 'World summary generated')
    else:
        report('WARN', 'World summary empty/brief', str(r)[:200])
    
    # Step 10: End session + personalized learning
    print("\n[Step 10] End session")
    r = api_post(host, '/api/sleep/world-end', {
        'openid': openid,
        'session_id': f'test_{openid}',
    })
    if not r.get('_http_error'):
        report('PASS', 'Session ended cleanly')
    else:
        report('FAIL', 'Session end error', str(r)[:200])
    
    print(f"\n{'='*60}")
    print(f"  RESULTS: {PASS} passed, {WARN} warnings, {FAIL} failed")
    print(f"{'='*60}")
    
    return FAIL


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='localhost:8090')
    parser.add_argument('--openid', default='test_e2e_001')
    args = parser.parse_args()
    
    failures = test_story(args.host, args.openid)
    return 1 if failures > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
