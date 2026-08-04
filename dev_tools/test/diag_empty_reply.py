#!/usr/bin/env python3
"""诊断：为什么回复是空的"""
import urllib.request, json

BASE = "http://localhost:8090"

# 直接打 world-step 看完整响应
data = json.dumps({
    "openid": "temp_user",
    "message": "昨晚没睡好，躺了一小时才睡着",
    "session_id": "diag_001"
}).encode()

req = urllib.request.Request(f"{BASE}/api/sleep/world-step", data=data,
                            headers={"Content-Type": "application/json"})
try:
    r = urllib.request.urlopen(req, timeout=60)
    resp = json.loads(r.read())
    print("完整响应键:", list(resp.keys()))
    for k, v in resp.items():
        if isinstance(v, str) and len(v) > 200:
            print(f"  {k}: ({len(v)}字) {v[:200]}...")
        elif isinstance(v, (int, float)):
            print(f"  {k}: {v}")
        elif isinstance(v, dict):
            print(f"  {k}: ({len(v)}项) {json.dumps(v, ensure_ascii=False)[:200]}")
        elif isinstance(v, list):
            print(f"  {k}: ({len(v)}项) {str(v)[:200]}")
        else:
            print(f"  {k}: {v}")
except Exception as e:
    print(f"Error: {e}")
    # 读原始body看看有没有什么告警线索
