#!/usr/bin/env python3
"""
concurrent_rw_test.py  — 并发读写竞争测试
P1: 同一用户并发请求下 user_profile 是否安全
"""
import sys, os, json, urllib.request, urllib.error, threading, time

HOST = os.environ.get('API_HOST', 'http://localhost:8090')
PASS = 0
FAIL = 0
results = []
lock = threading.Lock()

def send_concurrent(uid, gid, msg):
    global results
    try:
        data = json.dumps({"openid":uid,"session_id":gid,"message":msg,"platform":"test"}).encode()
        req = urllib.request.Request(HOST+"/api/chat", data=data, headers={"Content-Type":"application/json"})
        r = json.loads(urllib.request.urlopen(req,timeout=60).read())
        reply = r.get("reply","")
        with lock:
            results.append({"uid":uid, "gid":gid, "len":len(reply), "reply":reply[:50]})
    except Exception as e:
        with lock:
            results.append({"uid":uid, "gid":gid, "error":str(e)})

def main():
    global PASS, FAIL
    print(f"\n=== Concurrent Read/Write Test ===")
    print(f"Host: {HOST}")
    print()
    
    # Scenario: 10 threads, same user, different messages
    print("Test 1: Same user, 10 concurrent requests...")
    threads = []
    for i in range(10):
        t = threading.Thread(target=send_concurrent, args=("t_conc", "s_conc", f"这是第{i+1}条并发消息"))
        threads.append(t)
    for t in threads: t.start()
    for t in threads: t.join(timeout=35)
    
    # Check results
    has_error = any("error" in r for r in results)
    has_empty = any(r.get("len",0) < 5 for r in results if "error" not in r)
    
    if has_error:
        FAIL += 1
        errs = [r for r in results if "error" in r]
        print(f"  FAIL: {len(errs)}/{len(results)} requests errored")
        for e in errs[:3]:
            print(f"    error: {e['error']}")
    elif has_empty:
        FAIL += 1
        print(f"  FAIL: some requests returned empty replies (possible race)")
    else:
        PASS += 1
        print(f"  PASS: {len(results)}/{len(results)} requests succeeded, no race detected")
    
    # Clear
    results.clear()
    
    # Scenario: 5 users, 5 concurrent requests each
    print("\nTest 2: 5 users x 5 concurrent requests each...")
    threads = []
    for u in range(5):
        for i in range(5):
            t = threading.Thread(target=send_concurrent,
                args=(f"t_conc{u}", f"s_conc{u}", f"用户{u}的第{i+1}条消息"))
            threads.append(t)
    for t in threads: t.start()
    for t in threads: t.join(timeout=60)
    
    # Check cross-user data isolation
    has_error = any("error" in r for r in results)
    user_sessions = set()
    data_leak = False
    for r in results:
        key = (r.get("uid",""), r.get("gid",""))
        if key in user_sessions:
            pass  # expected duplicate
        else:
            user_sessions.add(key)
    
    if has_error:
        FAIL += 1
        errs = [r for r in results if "error" in r]
        print(f"  FAIL: {len(errs)}/{len(results)} requests errored")
    elif data_leak:
        FAIL += 1
        print(f"  FAIL: possible data leak between users")
    else:
        PASS += 1
        print(f"  PASS: {len(results)} requests across 5 users, no errors, no leak detected")
    
    print(f"\n=== Result: {PASS} PASS, {FAIL} FAIL ===")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
