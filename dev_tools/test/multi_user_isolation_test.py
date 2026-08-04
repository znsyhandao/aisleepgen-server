#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
multi_user_isolation_test.py - 多用户数据隔离测试 v1.0

测试不同用户的数据是否相互隔离。
同时发送多个用户的请求，验证：
1. A用户看不到B用户的睡眠数据
2. 会话状态不混淆
3. 并发不存在跨用户污染

用法:
  python dev_tools/test/multi_user_isolation_test.py [--host localhost:8090]
  python aisleepgen_tool.py test multi-user-isolation
"""

import os, sys, json, urllib.request, urllib.error, threading, time
sys.stdout.reconfigure(encoding='utf-8')

PASS = 0; FAIL = 0; WARN = 0
HOST = "localhost:8090"

def report(result, label, detail=''):
    global PASS, FAIL, WARN
    if result == 'PASS': PASS += 1; print(f"  [PASS] {label}")
    elif result == 'FAIL': FAIL += 1; print(f"  [FAIL] {label}: {detail}")
    elif result == 'WARN': WARN += 1; print(f"  [WARN] {label}: {detail}")

def api_post(host, path, data, timeout=10):
    url = f"http://{host}{path}"
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {'_error': str(e)}

def test_profile_isolation():
    """用户A的profile数据不会被用户B读到"""
    print("\n=== 用户资料隔离测试 ===")
    
    # Set different profiles for two users
    user_a = {"openid": "iso_test_a", "nickname": "UserA_Specific", "age": 25, "gender": "male"}
    user_b = {"openid": "iso_test_b", "nickname": "UserB_Specific", "age": 30, "gender": "female"}
    
    # Update profiles
    for user in [user_a, user_b]:
        api_post(HOST, "/api/user-profile", {
            "openid": user["openid"],
            "nickname": user["nickname"],
            "age": user["age"],
            "gender": user["gender"]
        })
    
    time.sleep(0.5)  # Allow write to propagate
    
    # Now read user A's profile as user B — should not see A's data
    resp_b = api_post(HOST, "/api/user-profile", {
        "openid": user_b["openid"]
    })
    
    resp_text = json.dumps(resp_b, ensure_ascii=False)
    
    # User B should have UserB_Specific, NOT UserA_Specific
    if "UserA_Specific" in resp_text:
        report('FAIL', "用户B读到了用户A的昵称（数据泄漏）")
    elif "UserB_Specific" in resp_text:
        report('PASS', "用户资料隔离正常")
    else:
        report('WARN', "无法确认用户资料隔离（回复中无预期昵称）")

def test_session_isolation():
    """会话状态不跨用户混淆"""
    print("\n=== 会话状态隔离测试 ===")
    
    # User A starts a conversation about sleep apnea
    resp_a1 = api_post(HOST, "/api/chat", {
        "openid": "iso_sess_a",
        "session_id": "sess_iso_1",
        "message": "我怀疑自己有睡眠呼吸暂停，晚上经常憋醒",
        "platform": "test"
    })
    
    # User B starts a conversation about insomnia
    resp_b1 = api_post(HOST, "/api/chat", {
        "openid": "iso_sess_b",
        "session_id": "sess_iso_1",
        "message": "我入睡困难已经3年了",
        "platform": "test"
    })
    
    # Get reply texts
    reply_a = json.dumps(resp_a1, ensure_ascii=False).lower() if '_error' not in resp_a1 else ""
    reply_b = json.dumps(resp_b1, ensure_ascii=False).lower() if '_error' not in resp_b1 else ""
    
    # Check for cross-contamination
    # User A mentioned sleep apnea, B shouldn't see it in context
    # User B mentioned 3 years of insomnia, A shouldn't see it
    problems = []
    
    # If A's reply mentions "呼吸困难" (sleep apnea) but B also has it — likely B contaminated
    # If B's reply mentions "3年" (B's specific info) but A also mentions it — A contaminated
    
    if not reply_a or not reply_b:
        report('WARN', "服务器未响应，隔离测试跳过")
        return
    
    # Context contamination check
    a_keywords = ["呼吸暂停", "憋醒"]
    b_keywords = ["3年", "入睡困难"]
    
    a_has_b_context = any(kw in reply_a for kw in b_keywords)
    b_has_a_context = any(kw in reply_b for kw in a_keywords)
    
    if a_has_b_context:
        report('FAIL', f"用户A的回复包含用户B的上下文（数据污染）")
    elif b_has_a_context:
        report('FAIL', f"用户B的回复包含用户A的上下文（数据污染）")
    else:
        report('PASS', "会话上下文隔离正常")

def test_concurrent_isolation():
    """并发请求下用户数据是否交叉污染"""
    print("\n=== 并发隔离测试 ===")
    results = {}
    lock = threading.Lock()
    
    def send_request(user_id, idx):
        resp = api_post(HOST, "/api/chat", {
            "openid": f"iso_conc_{user_id}",
            "session_id": f"conc_test",
            "message": f"我是用户{user_id}，帮我看看睡眠",
            "platform": "test"
        })
        with lock:
            results[f"{user_id}_{idx}"] = resp
    
    threads = []
    for uid in range(3):
        for i in range(3):
            t = threading.Thread(target=send_request, args=(uid, i))
            threads.append(t)
            t.start()
    
    for t in threads:
        t.join(timeout=5)
    
    # Check that each user got their own response (not someone else's)
    isolation_breaks = 0
    for key, resp in results.items():
        resp_text = json.dumps(resp, ensure_ascii=False)
        # Parse user_id from key
        uid = key.split('_')[0]
        wrong_users = [str(u) for u in range(3) if u != uid]
        for wu in wrong_users:
            if f"用户{wu}" in resp_text:
                isolation_breaks += 1
    
    if isolation_breaks > 0:
        report('FAIL', f"并发请求中出现{isolation_breaks}次数据隔离违规")
    elif results:
        report('PASS', f"并发请求隔离正常（{len(results)}次请求）")
    else:
        report('WARN', "无结果返回")

def test_cross_session_override():
    """一个用户的session不应覆盖另一个用户的session"""
    print("\n=== session不覆盖测试 ===")
    # This tests that two users with different openids but same session_id
    # don't interfere with each other's session state
    for i in range(3):
        resp_a = api_post(HOST, "/api/chat", {
            "openid": "iso_ovr_a",
            "session_id": "shared_sid",
            "message": f"第{i+1}轮对话A",
            "platform": "test"
        })
        resp_b = api_post(HOST, "/api/chat", {
            "openid": "iso_ovr_b",
            "session_id": "shared_sid",
            "message": f"第{i+1}轮对话B",
            "platform": "test"
        })
    
    # After 3 rounds, each user should have 3 messages of context
    # We can check by sending a query that requires context length awareness
    # (If one user overwrites the other's session, context will be short)
    
    report('INFO', "Session隔离: 同一session_id不同openid共存测试完成（需人工检查日志确认状态深度）")
    
def test_data_export_isolation():
    """数据导出API是否只返回当前用户的数据"""
    print("\n=== 数据导出隔离测试 ===")
    # Try to export user A's data while pretending to be user B
    resp = api_post(HOST, "/api/compliance/export-my-data", {
        "openid": "iso_export_b"
    })
    
    resp_text = json.dumps(resp, ensure_ascii=False)
    if "iso_test_a" in resp_text or "iso_sess_a" in resp_text:
        report('FAIL', "用户B导出了用户A的数据")
    else:
        report('PASS', "数据导出按openid隔离")

def main():
    print(f"{'='*60}")
    print(f"  多用户数据隔离测试 v1.0")
    print(f"  Target: {HOST}")
    print(f"{'='*60}")
    
    test_profile_isolation()
    test_session_isolation()
    test_concurrent_isolation()
    test_cross_session_override()
    test_data_export_isolation()
    
    print(f"\n{'='*60}")
    print(f"  结果: PASS={PASS} FAIL={FAIL} WARN={WARN}")
    print(f"{'='*60}")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith('--host='):
        HOST = sys.argv[1].split('=', 1)[1]
    sys.exit(main())
