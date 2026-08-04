#!/usr/bin/env python3
"""
breathing_keyword_collision_test.py  — 呼吸关键词碰撞回归测试
P0: 防止"睡眠呼吸暂停→呼吸引导覆盖"bug复活
"""
import sys, os, json, urllib.request, urllib.error

HOST = os.environ.get('API_HOST', 'http://localhost:8090')
PASS = 0
FAIL = 0

def test(label, message, expect_action=False, expect_disclaimer=False, expect_longer_than=50):
    global PASS, FAIL
    try:
        data = json.dumps({"openid":"t_br","session_id":"s_br","message":message,"platform":"test"}).encode()
        req = urllib.request.Request(HOST+"/api/chat", data=data, headers={"Content-Type":"application/json"})
        r = json.loads(urllib.request.urlopen(req,timeout=30).read())
        reply = r.get("reply","")
        has_action = "action" in r
        
        ok = True
        errors = []
        
        # Test 1: action presence
        if expect_action and not has_action:
            ok = False; errors.append("expected action=False but got action="+str(has_action))
        if not expect_action and has_action:
            ok = False; errors.append("expected no action but got action="+str(r.get("action","?")))
        
        # Test 2: disclaimer
        disclaimers = ["不能替代","不能代替","建议咨询","请咨询","无法诊断","不能做出","不是医学诊断"]
        has_disc = any(m in reply for m in disclaimers)
        if expect_disclaimer and not has_disc:
            ok = False; errors.append("missing disclaimer")
        if not expect_disclaimer and has_disc:
            ok = False; errors.append("unexpected disclaimer")
        
        # Test 3: minimum reply length (not overridden by short text)
        if len(reply) < expect_longer_than:
            ok = False; errors.append(f"reply too short ({len(reply)} < {expect_longer_than})")
        
        if ok:
            PASS += 1
            print(f"  PASS [{label}] len={len(reply)}")
        else:
            FAIL += 1
            print(f"  FAIL [{label}] {'; '.join(errors)}")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL [{label}] exception: {e}")

def main():
    global PASS, FAIL
    print(f"\n=== Breathing Keyword Collision Test ===")
    print(f"Host: {HOST}")
    print()
    
    # 1. Disease name containing "respire" should NOT trigger breathing action
    test("apnea", "我怀疑自己有睡眠呼吸暂停", expect_action=False, expect_disclaimer=True)
    test("apnea2", "睡眠呼吸暂停有什么症状", expect_action=False, expect_disclaimer=True)
    test("breathing_pause", "呼吸暂停会影响睡眠吗", expect_action=False, expect_disclaimer=True)
    
    # 2. Genuine breathing request SHOULD trigger action
    test("breath_pls", "带我做个呼吸练习", expect_action=True, expect_disclaimer=False, expect_longer_than=10)
    test("breath2", "跟着你一起呼吸引导", expect_action=True, expect_disclaimer=False, expect_longer_than=10)
    
    # 3. Neutral sleep talk, no action, no disclaimer needed
    test("normal", "今天睡得好累", expect_action=False, expect_disclaimer=False)
    
    # 4. Disease name + breathing request mixed
    msg4 = "我有睡眠呼吸暂停，带我做个呼吸练习放松一下"
    test("mixed", msg4, expect_action=True, expect_disclaimer=True)
    
    print(f"\n=== Result: {PASS} PASS, {FAIL} FAIL ===")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
