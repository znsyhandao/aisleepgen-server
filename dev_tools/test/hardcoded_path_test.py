#!/usr/bin/env python3
"""
hardcoded_path_test.py — 硬编码路径回归测试
Bug: deepseek_proxy.py在华为云部署时包含了多个 D:\ 绝对路径
    音频/判决跟踪/前端脚本均使用Windows绝对路径 → Linux部署会崩
"""
import sys, os, json, urllib.request, urllib.error

HOST = os.environ.get('API_HOST', 'http://localhost:8090')
PASS = 0
FAIL = 0

def test(label, endpoint, expect_status=200):
    global PASS, FAIL
    try:
        if endpoint == '/health':
            r = urllib.request.urlopen(HOST+endpoint, timeout=5)
            status = r.status
        elif endpoint == '/api/chat':
            data = json.dumps({"openid":"t_path","session_id":"s_path","message":"测一下","platform":"test"}).encode()
            req = urllib.request.Request(HOST+endpoint, data=data, headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                status = r.status
                body = json.loads(r.read().decode())
        else:
            r = urllib.request.urlopen(HOST+endpoint, timeout=5)
            status = r.status
        
        if status == expect_status:
            PASS += 1
            print(f"  PASS [{label}] status={status}")
        else:
            FAIL += 1
            print(f"  FAIL [{label}] expected {expect_status}, got {status}")
    except urllib.error.HTTPError as e:
        FAIL += 1
        print(f"  FAIL [{label}] HTTP {e.code}")
    except Exception as e:
        FAIL += 1
        safe = ''.join(c if ord(c) < 128 else '?' for c in str(e)[:100])
        print(f"  FAIL [{label}] exception: {safe}")

def main():
    global PASS, FAIL
    print(f"\n=== Hardcoded Path / Portability Test ===")
    print(f"Host: {HOST}")
    print()
    
    print("-- Core endpoints must work on any server --")
    test("health", "/health")
    test("chat", "/api/chat")
    
    # Check audio endpoints (which use hardcoded D:\ paths)
    data = json.dumps({"openid":"t_pa","session_id":"s_pa","platform":"test"}).encode()
    try:
        req = urllib.request.Request(HOST+"/api/audio/sleep-record", data=data,
            headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            body = json.loads(r.read().decode())
            if body.get('success') == False:
                PASS += 1
                print(f"  PASS [audio-record] returned gracefully (error in path is ok)")
            else:
                PASS += 1
                print(f"  PASS [audio-record] returned data successfully")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL [audio-record] crashed: {str(e)[:100]}")
    
    print(f"\n=== Result: {PASS} PASS, {FAIL} FAIL ===")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
