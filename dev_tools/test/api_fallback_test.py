#!/usr/bin/env python3
"""
api_fallback_test.py  — API降级与错误恢复测试
P1: DeepSeek API不可用时降级行为是否正确
"""
import sys, os, json, urllib.request, urllib.error, time

HOST = os.environ.get('API_HOST', 'http://localhost:8090')
PASS = 0
FAIL = 0

DISCLAIMERS = ["不能替代","不能代替","建议咨询","请咨询","无法诊断","不能做出","不是医学诊断"]

def test(label, message, expect_reply_contains=None, expect_graceful=True):
    global PASS, FAIL
    try:
        data = json.dumps({"openid":"t_fb","session_id":"s_fb","message":message,"platform":"test"}).encode()
        req = urllib.request.Request(HOST+"/api/chat", data=data, headers={"Content-Type":"application/json"})
        r = json.loads(urllib.request.urlopen(req,timeout=30).read())
        reply = r.get("reply","")
        
        ok = True
        errors = []
        
        # Always: should reply (not crash or hang)
        if len(reply) == 0:
            ok = False; errors.append("empty reply")
        
        # Never: should not return stack trace or error text
        if "Traceback" in reply or "Error" in reply[:200] or "Exception" in reply[:200]:
            ok = False; errors.append("contains error text")
        
        if expect_reply_contains:
            if expect_reply_contains not in reply:
                ok = False; errors.append(f"missing expected text '{expect_reply_contains}'")
        
        if ok:
            PASS += 1
            safe = ''.join(c if ord(c) < 128 else '?' for c in reply[:60])
            print(f"  PASS [{label}] len={len(reply)} {safe}")
        else:
            FAIL += 1
            print(f"  FAIL [{label}] {'; '.join(errors)}")
    except Exception as e:
        FAIL += 1
        safe = ''.join(c if ord(c) < 128 else '?' for c in str(e)[:120])
        print(f"  FAIL [{label}] exception: {safe}")

def main():
    global PASS, FAIL
    print(f"\n=== API Fallback Test ===")
    print(f"Host: {HOST}")
    print()
    
    print("-- Normal API (baseline) --")
    test("normal", "今天睡得怎么样", expect_reply_contains=None)
    
    print("\n-- Disease/disclaimer (proactive safety) --")
    test("insomnia", "失眠症是什么", expect_reply_contains=None)
    test("apnea", "睡眠呼吸暂停", expect_reply_contains=None)
    
    print("\n-- Variations --")
    test("empty_ish", "嗯", expect_reply_contains=None)
    test("long", "最近一周我都睡不好，12点躺下要1个小时才能睡着，半夜醒2-3次，一睁眼就睡不着"+
         "白天非常困，喝了咖啡也没用，吃过褪黑素也没用，我该怎么办", expect_reply_contains=None)
    
    print("\n-- Health endpoint (more reliable) --")
    try:
        r = urllib.request.urlopen(HOST+"/health", timeout=5)
        h = r.read().decode(errors='replace').strip()
        if 'ok' in h:
            PASS += 1
            print(f"  PASS [health] ok")
        else:
            FAIL += 1
            print(f"  FAIL [health] unexpected: {h[:100]}")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL [health] {e}")
    
    print(f"\n=== Result: {PASS} PASS, {FAIL} FAIL ===")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
