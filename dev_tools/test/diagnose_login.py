#!/usr/bin/env python3
"""诊断：登录端点返回了什么"""
import urllib.request, json

BASE = "http://localhost:8090"

# 测登录——看原始响应
data = json.dumps({"openid": "test_user_001", "nickName": "摸底测试"}).encode()
req = urllib.request.Request(f"{BASE}/api/wx/login", data=data,
                            headers={"Content-Type": "application/json"})
try:
    r = urllib.request.urlopen(req, timeout=10)
    print(f"Status: {r.status}")
    print(f"Headers: {dict(r.headers)}")
    body = r.read()
    print(f"Body bytes ({len(body)}): {body[:200]}")
    body_str = body.decode('utf-8')
    print(f"Body text: {body_str[:200]}")
    if body_str.strip():
        parsed = json.loads(body_str)
        print(f"Parsed: {json.dumps(parsed, ensure_ascii=False)[:200]}")
    else:
        print("EMPTY BODY — 登录端点没返回任何内容")
except Exception as e:
    print(f"Error: {e}")
