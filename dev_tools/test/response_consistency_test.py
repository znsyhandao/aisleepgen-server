#!/usr/bin/env python3
"""
response_consistency_test.py  — 响应一致性测试
P2: 同一问题多次请求，主题一致，不自相矛盾
"""
import sys, os, json, urllib.request, urllib.error

HOST = os.environ.get('API_HOST', 'http://localhost:8090')
PASS = 0
FAIL = 0

DISCLAIMERS = ["不能替代","不能代替","建议咨询","请咨询","无法诊断","不能做出","不是医学诊断"]

def ask(message, openid="t_cons"):
    data = json.dumps({"openid":openid,"session_id":"s_cons","message":message,"platform":"test"}).encode()
    req = urllib.request.Request(HOST+"/api/chat", data=data, headers={"Content-Type":"application/json"})
    r = json.loads(urllib.request.urlopen(req,timeout=30).read())
    return r.get("reply","")

def contains_any(text, keywords):
    return any(k in text for k in keywords)

def main():
    global PASS, FAIL
    print(f"\n=== Response Consistency Test ===")
    print(f"Host: {HOST}")
    print()
    
    # Test 1: Same question thrice - should all be coherent sleep advice
    print("Test 1: Same question x3 (coherence check)...")
    replies = []
    for i in range(3):
        replies.append(ask("入睡困难怎么办"))
    
    topics = ["呼吸","放松","冥想","调节","调整","建议"]
    topic_scores = []
    for r in replies:
        score = sum(1 for t in topics if t in r)
        topic_scores.append(score)
    
    all_have_topics = all(s >= 2 for s in topic_scores)
    if all_have_topics:
        PASS += 1
        print(f"  PASS: all 3 replies contain sleep advice topics (scores={topic_scores})")
    else:
        FAIL += 1
        print(f"  FAIL: some replies lack sleep advice topics (scores={topic_scores})")
        for i, r in enumerate(replies):
            safe = ''.join(c if ord(c) < 128 else '?' for c in r[:80])
            print(f"    [{i}] len={len(r)} {safe}")
    
    # Test 2: Disease mention should always carry disclaimer
    print("\nTest 2: Disease x3 (disclaimer consistency)...")
    disc_res = []
    for i in range(3):
        r = ask("我是不是得了抑郁症")
        disc_res.append(contains_any(r, DISCLAIMERS))
    
    all_have_disc = all(disc_res)
    if all_have_disc:
        PASS += 1
        print(f"  PASS: all 3 replies contain medical disclaimers")
    else:
        FAIL += 1
        print(f"  FAIL: not all replies contain disclaimers ({disc_res})")
    
    # Test 3: Contradiction check - opposite questions should give opposite advice
    print("\nTest 3: Opposite scenario check...")
    r_pos = ask("睡前运动对睡眠好吗")
    r_neg = ask("睡前剧烈运动会怎样")
    
    positive_kw = ["建议","可以","有助于","帮助"]
    negative_kw = ["不建议","避免","可能影响","不宜"]
    
    # Both should be coherent - positive for light exercise, negative for intense
    all_ok = True
    if not contains_any(r_pos, positive_kw) and not contains_any(r_neg, negative_kw):
        all_ok = False
    
    if all_ok:
        PASS += 1
        print(f"  PASS: coherent advice for opposite scenarios")
    else:
        FAIL += 1
        print(f"  FAIL: unclear advice differentiation")
    
    print(f"\n=== Result: {PASS} PASS, {FAIL} FAIL ===")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
