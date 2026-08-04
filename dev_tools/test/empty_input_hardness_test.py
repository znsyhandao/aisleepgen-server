#!/usr/bin/env python3
"""
empty_input_hardness_test.py — 极简输入/非睡眠话题的鲁棒性测试
Bug: openid/空message/非睡眠话题 → 是否吞异常或返回无意义回复
"""
import sys, os, json, urllib.request, urllib.error

HOST = os.environ.get('API_HOST', 'http://localhost:8090')
PASS = 0
FAIL = 0

EMPTY_TESTS = [
    ("empty_msg", {"openid":"t_empty1","session_id":"s_empty1","message":"","platform":"test"}),
    ("space_msg", {"openid":"t_empty2","session_id":"s_empty2","message":"  ","platform":"test"}),
    ("no_openid", {"session_id":"s_empty3","message":"睡不着","platform":"test"}),
    ("no_session", {"openid":"t_empty4","message":"睡不着","platform":"test"}),
    ("emoji_only", {"openid":"t_empty5","session_id":"s_empty5","message":"😊","platform":"test"}),
    ("random_chars", {"openid":"t_empty6","session_id":"s_empty6","message":"asdfjkl1234^%^%DFG","platform":"test"}),
    ("super_long", {"openid":"t_empty7","session_id":"s_empty7","message":"测"*5000,"platform":"test"}),
    ("mixed_lang", {"openid":"t_empty8","session_id":"s_empty8","message":"Hello你好한국어日本語","platform":"test"}),
]

# Non-sleep topics that should still get graceful response
NON_SLEEP = [
    ("math", "1+1等于几"),
    ("weather", "今天天气怎么样"),
    ("song", "给我写首歌"),
    ("topic_politics", "你怎么看最近的经济形势"),
    ("code", "帮我写个Python爬虫"),
]

def run(label, payload):
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(HOST+"/api/chat", data=data,
            headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read().decode())
            reply = body.get("reply", "")
            
            ok = True
            errs = []
            if not reply:
                ok = False; errs.append("empty reply")
            if "Traceback" in reply or "Error" in reply[:200]:
                ok = False; errs.append("leaked error message")
            if len(reply) > 5000:
                ok = False; errs.append(f"reply too long ({len(reply)})")
            
            if ok:
                return "PASS", f"len={len(reply)}"
            else:
                return "FAIL", "; ".join(errs)
    except Exception as e:
        return "FAIL", str(e)[:80]

def main():
    global PASS, FAIL
    print(f"\n=== Empty/Extreme Input Hardness Test ===")
    print(f"Host: {HOST}")
    
    print("\n-- Empty/Special inputs --")
    for label, payload in EMPTY_TESTS:
        status, detail = run(label, payload)
        if status == "PASS":
            PASS += 1
        else:
            FAIL += 1
        print(f"  {status} [{label}] {detail}")
    
    print("\n-- Non-sleep topics --")
    for label, msg in NON_SLEEP:
        payload = {"openid":"t_ns","session_id":"s_ns","message":msg,"platform":"test"}
        status, detail = run(label, payload)
        if status == "PASS":
            PASS += 1
        else:
            FAIL += 1
        safe = ''.join(c if ord(c) < 128 else '?' for c in detail)
        print(f"  {status} [{label}] {safe}")
    
    print(f"\n=== Result: {PASS} PASS, {FAIL} FAIL ===")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
