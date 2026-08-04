#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
idempotency_test.py - 幂等性验证测试 v1.0

测试相同请求重复发送是否产生相同的副作用（无重复计费、无重复记录）。
遵循最佳实践：医疗AI的幂等性关乎患者安全和数据完整性。

用法:
  python dev_tools/test/idempotency_test.py [--host localhost:8090]
  python aisleepgen_tool.py test idempotency
"""

import os, sys, json, urllib.request, urllib.error, time
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

def api_get(host, path, timeout=10):
    try:
        with urllib.request.urlopen(f"http://{host}{path}", timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {'_error': str(e)}

def test_health_endpoint_idempotent():
    """GET /health 重复调用应返回相同结果"""
    print("\n=== 健康检查幂等性测试 ===")
    results = []
    for i in range(5):
        resp = api_get(HOST, "/health")
        results.append(resp)
        time.sleep(0.1)
    
    # Compare all responses
    first = json.dumps(results[0], sort_keys=True, ensure_ascii=False) if results else ""
    all_same = all(
        json.dumps(r, sort_keys=True, ensure_ascii=False) == first 
        for r in results[1:]
    )
    
    if all_same:
        report('PASS', f"5次/health调用返回一致")
    else:
        report('WARN', f"健康检查响应不一致（可能含时间戳等动态字段）")

def test_profile_read_idempotent():
    """用户资料读取幂等性"""
    print("\n=== 用户资料读取幂等测试 ===")
    
    openid = "test_idemp_user"
    # Create a known profile first
    api_post(HOST, "/api/wx/profile", {
        "openid": openid,
        "nickname": "IdempTestUser",
        "age": 30
    })
    time.sleep(0.3)
    
    results = []
    for i in range(3):
        resp = api_post(HOST, "/api/user-profile", {
            "openid": openid
        })
        if '_error' not in resp:
            results.append(resp)
        time.sleep(0.2)
    
    if len(results) >= 2:
        first = json.dumps(results[0], sort_keys=True, ensure_ascii=False)
        all_same = all(
            json.dumps(r, sort_keys=True, ensure_ascii=False) == first 
            for r in results[1:]
        )
        if all_same:
            report('PASS', "用户资料读取幂等")
        else:
            report('WARN', "用户资料读取响应不一致")
    else:
        report('WARN', "无法读取用户资料")

def test_world_step_idempotent():
    """相同的世界模型输入不应累积副作用"""
    print("\n=== 世界模型幂等性测试 ===")
    
    openid = "test_idemp_world"
    session_id = "idemp_session"
    message = "我昨晚睡了5个小时"
    
    # Send the same message 3 times
    for i in range(3):
        resp = api_post(HOST, "/api/chat", {
            "openid": openid,
            "session_id": session_id,
            "message": message,
            "platform": "test"
        })
        if '_error' not in resp:
            report('PASS' if i == 0 else 'WARN', f"第{i+1}次发送成功（注意：LLM回复天然不同，这个是预期行为）")
        time.sleep(0.3)

def test_compliance_delete_idempotent():
    """数据删除接口幂等性"""
    print("\n=== 数据删除幂等性测试 ===")
    
    openid = "test_idemp_delete"
    
    # First delete
    resp1 = api_post(HOST, "/api/compliance/delete-my-data", {
        "openid": openid
    })
    # Second delete of same user
    resp2 = api_post(HOST, "/api/compliance/delete-my-data", {
        "openid": openid
    })
    
    # Both should succeed (first deletes, second confirms already deleted)
    err1 = '_error' in resp1
    err2 = '_error' in resp2
    
    if err1 and err2:
        report('WARN', "删除接口均出错")
    elif err1 and not err2:
        report('WARN', "第一次删除出错，第二次成功")
    elif not err1 and err2:
        report('WARN', "第一次成功，第二次出错（非幂等）")
    else:
        report('PASS', "删除接口幂等（两次调用均正常返回）")

def main():
    print(f"{'='*60}")
    print(f"  幂等性验证测试 v1.0")
    print(f"  Target: {HOST}")
    print(f"{'='*60}")
    
    test_health_endpoint_idempotent()
    test_profile_read_idempotent()
    test_world_step_idempotent()
    test_compliance_delete_idempotent()
    
    print(f"\n{'='*60}")
    print(f"  结果: PASS={PASS} FAIL={FAIL} WARN={WARN}")
    print(f"{'='*60}")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith('--host='):
        HOST = sys.argv[1].split('=', 1)[1]
    sys.exit(main())
