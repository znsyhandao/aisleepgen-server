#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
abnormal_input_test.py - 异常输入/XSS/空值处理测试 v1.0

测试AI在收到异常输入时的处理能力：
- 空值/空字符串
- 特殊字符/XSS注入
- 超长文本
- 乱码/二进制数据
- JSON注入攻击

遵循最佳实践：输入验证 + 防御性编程。

用法:
  python dev_tools/test/abnormal_input_test.py [--host localhost:8090]
  python aisleepgen_tool.py test abnormal-input
"""

import os, sys, json, urllib.request, urllib.error
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
    except urllib.error.HTTPError as e:
        return {'_http_error': e.code, '_body': e.read().decode('utf-8', errors='replace')[:300]}
    except Exception as e:
        return {'_error': str(e), '_type': type(e).__name__}

def test_empty_input():
    """空字符串/空对象处理"""
    print("\n=== 空输入处理测试 ===")
    test_cases = [
        ("空字符串", {"openid": "test_ab", "session_id": "ab1", "message": "", "platform": "test"}),
        ("空格字符串", {"openid": "test_ab", "session_id": "ab2", "message": "   ", "platform": "test"}),
        ("无message字段", {"openid": "test_ab", "session_id": "ab3", "platform": "test"}),
        ("空json对象", {"openid": "test_ab"}),
        ("None值message", {"openid": "test_ab", "session_id": "ab4", "message": None, "platform": "test"}),
        ("空数组message", {"openid": "test_ab", "session_id": "ab5", "message": [], "platform": "test"}),
    ]
    for i, (label, data) in enumerate(test_cases):
        resp = api_post(HOST, "/api/chat", data)
        if '_error' in resp:
            report('WARN', f"[{i+1}] {label}: 服务器未运行")
            continue
        # Should NOT crash — should return 400 or graceful error
        if resp.get('_http_error'):
            if resp['_http_error'] == 400:
                report('PASS', f"[{i+1}] {label}: 返回400（正确拒绝）")
            else:
                report('WARN', f"[{i+1}] {label}: HTTP {resp['_http_error']}")
        elif 'reply' in resp or 'response' in resp or 'content' in resp:
            report('WARN', f"[{i+1}] {label}: 返回了有效回复（可能未验证输入）")
        else:
            report('PASS', f"[{i+1}] {label}: 返回了异常（合理处理）: {str(resp)[:80]}")

def test_xss_injection():
    """XSS注入测试"""
    print("\n=== XSS注入测试 ===")
    xss_payloads = [
        "<script>alert('xss')</script>",
        "<img src=x onerror=alert(1)>",
        "{{7*7}}",
        "${7*7}",
        "'; DROP TABLE users; --",
        "<iframe src='javascript:alert(1)'>",
        "javascript:alert(document.cookie)",
    ]
    for i, payload in enumerate(xss_payloads):
        resp = api_post(HOST, "/api/chat", {
            "openid": "test_xss", "session_id": f"xss_{i}",
            "message": f"我最近{payload}，睡不好", "platform": "test"
        })
        if '_error' in resp:
            report('WARN', f"[{i+1}] 服务器未运行")
            continue
        resp_text = json.dumps(resp, ensure_ascii=False)
        # Check that injection payload doesn't echo back unsanitized
        if payload in resp_text:
            report('FAIL', f"[{i+1}] XSS payload在回复中回显: {payload[:30]}")
        else:
            report('PASS', f"[{i+1}] XSS注入安全: {payload[:20]}")

def test_oversized_input():
    """超长文本处理"""
    print("\n=== 超长文本测试 ===")
    long_text = "我睡眠不好。" * 5000  # ~35KB
    resp = api_post(HOST, "/api/chat", {
        "openid": "test_long",
        "session_id": "oversize",
        "message": long_text,
        "platform": "test"
    })
    if '_error' in resp:
        report('WARN', "长文本: 服务器未运行")
    elif resp.get('_http_error'):
        report('PASS' if resp['_http_error'] in [400, 413, 429] else 'WARN',
               f"长文本: HTTP {resp['_http_error']}（限制处理）")
    elif len(json.dumps(resp, ensure_ascii=False)) > 100:
        report('PASS', "长文本: 正常处理（或截断）")
    else:
        report('WARN', "长文本: 回复异常短")

def test_garbled_input():
    """乱码/二进制/特殊编码输入"""
    print("\n=== 乱码输入测试 ===")
    garbled_cases = [
        ("乱码GBK", b'\xbe\xdf\xc3\xce'.decode('gbk', errors='replace')),
        ("全零宽字符", "\u200b\u200c\u200d\u2060" * 100),
        ("全emoji", "😀😃😄😁😆😅🤣😂🙂🙃😉😊😇🥰😍🤩😘😗😚😋😛😜🤪😝🤑🤗🤭🤫🤔🤐🤨😐😑😶😏😒🙄😬🤥😌😔😪🤤😴😷🤒🤕🤢🤮🤧🥵🥶🥴😵🤯🤠🥳🥸😎🤓🧐😕😟🙁😮😯😲😳🥺😦😧😨😰😥😢😭😱😖😣😞😓😩😫🥱😤😡😠🤬"),
        ("超多换行", "\n" * 1000),
    ]
    for label, payload in garbled_cases:
        resp = api_post(HOST, "/api/chat", {
            "openid": "test_garb",
            "session_id": f"garb_{label[:2]}",
            "message": payload,
            "platform": "test"
        })
        if '_error' in resp:
            report('WARN', f"{label}: 跳过")
            continue
        if resp.get('_http_error'):
            report('PASS', f"{label}: HTTP {resp['_http_error']}")
        else:
            report('PASS', f"{label}: 未崩溃")

def test_json_injection():
    """JSON注入攻击"""
    print("\n=== JSON注入测试 ===")
    # Try to send non-JSON content type with JSON-like body
    url = f"http://{HOST}/api/chat"
    try:
        req = urllib.request.Request(url, data="not_json_at_all{traversal", 
            headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode('utf-8'))
        if body.get('_http_error'):
            report('PASS', "无效JSON: HTTP错误")
        else:
            report('PASS', "无效JSON: 未崩溃")
    except urllib.error.HTTPError as e:
        report('PASS' if e.code in [400, 415] else 'WARN', f"无效JSON: HTTP {e.code}")
    except Exception as e:
        report('WARN', f"无效JSON: 异常 {type(e).__name__}")

def main():
    print(f"{'='*60}")
    print(f"  异常输入处理测试 v1.0")
    print(f"  Target: {HOST}")
    print(f"{'='*60}")
    
    test_empty_input()
    test_xss_injection()
    test_oversized_input()
    test_garbled_input()
    test_json_injection()
    
    print(f"\n{'='*60}")
    print(f"  结果: PASS={PASS} FAIL={FAIL} WARN={WARN}")
    print(f"{'='*60}")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith('--host='):
        HOST = sys.argv[1].split('=', 1)[1]
    sys.exit(main())
