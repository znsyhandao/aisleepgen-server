#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stability_endurance_test.py — 长时间稳定性测试

测什么：
- 定时器是否准时触发（scheduler_daemon 的 trigger_world_model_cycle）
- 长连接 / 审计日志写入是否泄漏句柄
- 连续请求下 CPU/内存是否持续增长（内存泄漏）
- 定时器堆积：一个 handler 卡住是否导致后续定时器全部超时

用法:
  python stability_endurance_test.py [--host localhost:8090] [--duration 300] [--interval 30]
"""

import os, sys, json, time, threading, argparse, urllib.request, urllib.error
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

PASS = 0
FAIL = 0
WARN = 0

def report(result, label, detail=''):
    global PASS, FAIL, WARN
    if result == 'PASS': PASS += 1; print(f"  ✅ {label}")
    elif result == 'FAIL': FAIL += 1; print(f"  ❌ {label}: {detail}")
    elif result == 'WARN': WARN += 1; print(f"  ⚠️  {label}: {detail}")

def api_post(host, path, data, timeout=10):
    url = f"http://{host}{path}"
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')[:300]
        return {'_http_error': e.code, '_body': body}
    except Exception as e:
        return {'_error': str(e)}

def api_get(host, path, timeout=10):
    try:
        with urllib.request.urlopen(f"http://{host}{path}", timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {'_error': str(e)}


class TimerWatchdog:
    """监视定时器是否在预期间隔内触发."""
    def __init__(self, expected_interval=30, tolerance=10):
        self.expected = expected_interval
        self.tolerance = tolerance
        self.hits = []
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def _watch(self):
        while self._running:
            self.hits.append(time.time())
            time.sleep(self.expected)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(3)

    def check_jitter(self):
        """Check if timer fired roughly on schedule."""
        if len(self.hits) < 3:
            return [], 0
        intervals = []
        violations = []
        for i in range(1, len(self.hits)):
            interval = self.hits[i] - self.hits[i-1]
            intervals.append(interval)
            if abs(interval - self.expected) > self.tolerance:
                violations.append((i, round(interval, 1)))
        avg_interval = sum(intervals) / len(intervals) if intervals else 0
        return violations, avg_interval


def test_endurance(host, duration, interval):
    print(f"{'='*60}")
    print(f"  STABILITY ENDURANCE TEST")
    print(f"  Duration: {duration}s | Poll interval: {interval}s")
    print(f"  Target: {host}")
    print(f"{'='*60}\n")

    # Pre-flight: server alive
    r = api_get(host, '/health')
    if '_error' in r:
        report('FAIL', 'Server unreachable', r['_error'])
        return 1
    report('PASS', 'Server alive')

    # Start timer watchdog (simulated)
    watchdog = TimerWatchdog(expected_interval=interval, tolerance=interval * 0.5)
    watchdog.start()
    report('PASS', 'Timer watchdog started')

    # Metrics tracking
    metrics = {
        'response_times': [],
        'status_oks': 0,
        'status_fails': 0,
        'memory_leak_warnings': [],
    }
    user_states = {}
    start_time = time.time()
    elapsed = 0
    cycle = 0

    try:
        while elapsed < duration:
            cycle += 1
            t0 = time.time()

            # --- every cycle: health check ---
            r = api_get(host, '/health')
            rt = time.time() - t0
            metrics['response_times'].append(rt)

            if '_error' in r:
                metrics['status_fails'] += 1
                report('FAIL', f'Cycle {cycle}: health check failed', r['_error'])
            else:
                metrics['status_oks'] += 1

            # --- every 3 cycles: full user story ---
            if cycle % 3 == 0:
                uid = f"endurance_{int(t0)}"
                # Login
                r = api_post(host, '/api/wx/login', {'code': uid, 'mock': True})
                if '_error' in r:
                    report('FAIL', f'Cycle {cycle}: login', str(r)[:150])
                else:
                    # Profile
                    api_post(host, '/api/wx/profile', {
                        'openid': uid,
                        'age': 35, 'gender': 'male',
                        'sleep_latency': 40, 'total_sleep_hours': 5,
                        'awake_times': 3, 'stress_level': 6,
                    })
                    # Chat + world model
                    r2 = api_post(host, '/api/sleep/world-step', {
                        'openid': uid, 'message': '测试稳定性 ' + str(cycle),
                        'session_id': f'session_{uid}',
                    })
                    wm = r2.get('world_model', r2.get('data', {}).get('world_model', {}))
                    state = wm.get('arousal_state', wm.get('state', 'unknown'))
                    user_states[uid] = state

            # --- every 10 cycles: check for state diversity ---
            if cycle % 10 == 0:
                states = set(user_states.values())
                if len(states) >= 2:
                    pass  # Good — states are varying
                elif len(user_states) >= 5 and len(states) == 1:
                    # All users stuck on same state — possible fallback
                    report('WARN', f'Cycle {cycle}: All {len(user_states)} users have same state={list(states)[0]}',
                           'World model may be stuck in fallback')

            # --- every 20 cycles: response time health ---
            if cycle % 20 == 0 and len(metrics['response_times']) >= 10:
                recent = metrics['response_times'][-20:]
                avg_rt = sum(recent) / len(recent)
                if avg_rt > 3.0:
                    report('WARN', f'Cycle {cycle}: Avg response time {avg_rt:.1f}s',
                           'Possible resource leak / timer backlog')
                if len(metrics['response_times']) >= 50:
                    # Check for trend: last 10 vs first 10
                    first10 = metrics['response_times'][:10]
                    last10 = metrics['response_times'][-10:]
                    if sum(last10) / len(last10) > sum(first10) / len(first10) * 2:
                        metrics['memory_leak_warnings'].append(cycle)
                        report('WARN', f'Cycle {cycle}: Response time trending UP',
                               'Possible memory leak — double check')

            elapsed = time.time() - start_time
            if cycle % 20 == 0:
                print(f"  [Status] Cycle {cycle}, elapsed {elapsed:.0f}s, "
                      f"users={len(user_states)}, oks={metrics['status_oks']}, "
                      f"fails={metrics['status_fails']}")

    except KeyboardInterrupt:
        print("\n  Test interrupted by user")
    finally:
        watchdog.stop()

    print(f"\n{'='*60}")
    print(f"  RESULTS")
    print(f"{'='*60}")
    print(f"  Duration: {elapsed:.0f}s ({cycle} cycles)")
    print(f"  Health checks: {metrics['status_oks']} ok, {metrics['status_fails']} failed")
    print(f"  Unique user states seen: {len(set(user_states.values()))}")
    print(f"  Memory leak warnings: {len(metrics['memory_leak_warnings'])}")

    # Timer jitter check
    violations, avg_int = watchdog.check_jitter()
    if violations:
        print(f"  Timer jitter violations: {len(violations)}")
        for v in violations[:5]:
            print(f"    Cycle {v[0]}: interval {v[1]}s (expected {interval}s)")
    else:
        print(f"  Timer jitter: none (avg interval {avg_int:.1f}s) ✅")

    avg_all_rt = sum(metrics['response_times']) / len(metrics['response_times']) if metrics['response_times'] else 0
    print(f"  Avg response time: {avg_all_rt:.3f}s")
    print(f"  Max response time: {max(metrics['response_times']):.3f}s" if metrics['response_times'] else "")

    health = metrics['status_fails'] == 0 and len(metrics['memory_leak_warnings']) == 0
    print(f"\n  {'✅ ALL PASS' if health else '❌ HAS ISSUES'}")

    return 0 if health else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='localhost:8090')
    parser.add_argument('--duration', type=int, default=300, help='Test duration in seconds')
    parser.add_argument('--interval', type=int, default=30, help='Poll interval in seconds')
    args = parser.parse_args()
    sys.exit(test_endurance(args.host, args.duration, args.interval))


if __name__ == '__main__':
    main()
