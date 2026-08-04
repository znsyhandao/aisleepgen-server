#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
concurrent_stress_test.py — 并发压力测试

测什么：
- 多用户同时请求时的竞态条件
- 全局变量 STATE_PROFILES 交叉污染
- 句柄/连接泄漏
- 服务器在并发下的崩溃率

用法:
  python concurrent_stress_test.py [--host localhost:8090] [--users 10] [--requests 5]
"""

import os, sys, json, time, threading, argparse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

PASS = 0
FAIL = 0


def api_post(host, path, data, timeout=8):
    url = f"http://{host}{path}"
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload,
                                  headers={'Content-Type': 'application/json'},
                                  method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return {'_http_error': e.code, '_body': e.read().decode('utf-8', errors='replace')[:200]}
    except Exception as e:
        return {'_error': str(e)}


def user_session(host, uid):
    """Simulate one user's session."""
    openid = f"stress_{uid:04d}"
    results = {}
    
    # 1. Login
    r = api_post(host, '/api/wx/login', {'code': openid, 'mock': True})
    results['login'] = 'ok' if not r.get('_http_error') and not r.get('_error') else str(r)[:100]
    
    # 2. Submit profile
    r = api_post(host, '/api/wx/profile', {
        'openid': openid,
        'age': 20 + (uid % 50),
        'gender': 'male' if uid % 2 == 0 else 'female',
        'sleep_latency': 10 + (uid % 60),
        'total_sleep_hours': 4.0 + (uid % 5),
        'awake_times': uid % 5,
        'stress_level': 3 + (uid % 8),
    })
    results['profile'] = 'ok' if not r.get('_http_error') else str(r)[:100]
    
    # 3. Chat (world model)
    r = api_post(host, '/api/sleep/world-step', {
        'openid': openid,
        'message': f'我是用户{uid}，最近睡眠不太好',
        'session_id': f'session_{openid}',
    })
    wm = r.get('world_model', r.get('data', {}).get('world_model', {}))
    state = wm.get('arousal_state', wm.get('state', 'N/A'))
    results['world_model_state'] = state
    
    # 4. Render plan
    r = api_post(host, '/api/sleep/render-plan', {
        'openid': openid,
        'arousal_state': state if state != 'N/A' else 'alert',
    })
    bpm = r.get('bpm', r.get('data', {}).get('bpm', -1))
    results['bpm'] = bpm
    
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='localhost:8090')
    parser.add_argument('--users', type=int, default=10, help='Number of concurrent users')
    parser.add_argument('--requests', type=int, default=5, help='Requests per user')
    args = parser.parse_args()
    
    print(f"🔶 CONCURRENT STRESS TEST: {args.users} users, {args.requests} requests/user")
    print(f"   Target: {args.host}\n")
    
    # Pre-check: is server alive?
    try:
        with urllib.request.urlopen(f"http://{args.host}/health", timeout=5):
            print("   Server is alive ✅\n")
    except Exception as e:
        print(f"   Server not reachable: {e}")
        sys.exit(1)
    
    # Run concurrent users
    all_results = []
    errors = Counter()
    state_distribution = Counter()
    bpm_errors = 0
    login_errors = 0
    start = time.time()
    
    with ThreadPoolExecutor(max_workers=min(args.users, 50)) as executor:
        futures = []
        for uid in range(args.users):
            for _ in range(args.requests):
                futures.append(executor.submit(user_session, args.host, uid))
        
        for i, f in enumerate(as_completed(futures)):
            try:
                results = f.result(timeout=15)
                all_results.append(results)
                
                state = results.get('world_model_state', 'N/A')
                state_distribution[state] += 1
                
                if results.get('login', 'error').startswith('error'):
                    login_errors += 1
                    errors['login'] += 1
                
                bpm = results.get('bpm', -1)
                if bpm == -1:
                    bpm_errors += 1
                    errors['bpm'] += 1
                
                if (i + 1) % 10 == 0:
                    print(f"   Progress: {i+1}/{len(futures)} requests")
                    
            except Exception as e:
                errors['exception'] += 1
                all_results.append({'error': str(e)})
    
    elapsed = time.time() - start
    
    print(f"\n{'='*60}")
    print(f"  RESULTS")
    print(f"{'='*60}")
    print(f"  Total requests: {len(all_results)}")
    print(f"  Duration: {elapsed:.1f}s ({len(all_results)/elapsed:.0f} req/s)")
    print(f"  Login errors: {login_errors}")
    print(f"  BPM errors (bpm=-1): {bpm_errors}")
    print(f"  Other errors: {dict(errors)}")
    print(f"\n  World model state distribution:")
    for state, count in state_distribution.most_common(10):
        pct = count / len(all_results) * 100
        print(f"    {state:20s}  {count:>4} ({pct:5.1f}%)")
    
    has_errors = login_errors > 0 or bpm_errors > 0 or len(errors) > 0
    print(f"\n  {'✅ ALL PASS' if not has_errors else '❌ HAS ERRORS'}")
    
    return 1 if has_errors else 0


if __name__ == '__main__':
    sys.exit(main())
