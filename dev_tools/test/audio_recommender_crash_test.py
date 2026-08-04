#!/usr/bin/env python3
"""
audio_recommender_crash_test.py — audio_recommender import崩溃回归测试
Bug: Huawei云缺少soundfile模块, import audio_recommender 会 ModuleNotFoundError
    但 import 在 try 块内，理论上被catch。需要验证是否真的被安全吞掉。
"""
import sys, os, json, urllib.request, urllib.error

HOST = os.environ.get('API_HOST', 'http://localhost:8090')
PASS = 0
FAIL = 0

def main():
    global PASS, FAIL
    print(f"\n=== Audio Recommender Import Crash Test ===")
    print(f"Host: {HOST}")
    print()
    
    # Test: specific scenarios that trigger audio_recommender import
    scenarios = [
        ("relax+stress", {"openid":"t_audio1","session_id":"s_audio1",
                          "message":"我最近压力很大，推荐一些放松音频",
                          "platform":"test","history":[]}),
        ("sleep+stress", {"openid":"t_audio2","session_id":"s_audio2",
                          "message":"我睡不着，有什么助眠音频推荐",
                          "platform":"test","history":[]}),
        ("normal", {"openid":"t_audio3","session_id":"s_audio3",
                    "message":"今天睡得还行",
                    "platform":"test","history":[]}),
    ]
    
    for label, payload in scenarios:
        try:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(HOST+"/api/chat", data=data,
                headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read().decode())
                reply = body.get("reply", "")
                has_action = "action" in body
                
                if len(reply) > 0 and not reply.startswith("Error"):
                    PASS += 1
                    safe = ''.join(c if ord(c) < 128 else '?' for c in reply[:60])
                    print(f"  PASS [{label}] reply={safe}")
                else:
                    FAIL += 1
                    print(f"  FAIL [{label}] empty/error reply")
        except Exception as e:
            FAIL += 1
            safe = ''.join(c if ord(c) < 128 else '?' for c in str(e)[:120])
            print(f"  FAIL [{label}] crashed: {safe}")
    
    print(f"\n=== Result: {PASS} PASS, {FAIL} FAIL ===")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
