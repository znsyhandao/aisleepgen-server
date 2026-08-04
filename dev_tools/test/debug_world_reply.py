#!/usr/bin/env python3
"""DEBUG：消息解析后世界模型的回复"""
import urllib.request, json, time

BASE = "http://localhost:8090"

# 带消息发请求
data = json.dumps({
    'openid': 'temp_user',
    'message': '翻来覆去睡不着，2点才睡着，6点多就醒了',
    'session_id': 'debug_msg'
}).encode()
req = urllib.request.Request(f"{BASE}/api/sleep/world-step", data=data,
                            headers={'Content-Type': 'application/json'})
r = urllib.request.urlopen(req, timeout=60)
resp = json.loads(r.read())

print(f"reply({len(resp.get('reply',''))}字): {resp['reply'][:100]}")
print(f"sleep_score: {resp.get('sleep_score')}")

# 打印维度详情
dims = resp.get('analysis', {}).get('dimensions', [])
for d in dims:
    name = d.get('name', '')
    score = d.get('score', 0)
    conf = d.get('confidense', 0)
    findings = d.get('findings', [])
    narrative = d.get('narrative', '')[:80]
    specialty = d.get('specialty', '')
    print(f"\n[{name}] score={score} conf={conf} specialty={specialty}")
    if findings:
        for f in findings[:2]:
            print(f"  find: {f[:80]}")
    if narrative:
        print(f"  narr: {narrative}")
