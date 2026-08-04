"""
verify_pay.py — 支付 API 远程验证

调远程服务器(82.156.208.245:8090)的 pricing + recommend-tier + create-order，
确认外网支付链路正常。
用法: python dev_tools/test/verify_pay.py
"""
import urllib.request, json

API = 'http://82.156.208.245:8090'

# Test pricing
r = urllib.request.Request(f'{API}/api/pricing')
resp = json.loads(urllib.request.urlopen(r, timeout=5).read())
print('=== PRICING ===')
print(json.dumps(resp, indent=2, ensure_ascii=False))

# Test recommend
data = json.dumps({'openid': 'test123'}).encode()
r = urllib.request.Request(f'{API}/api/recommend-tier', data=data,
    headers={'Content-Type': 'application/json'})
resp = json.loads(urllib.request.urlopen(r, timeout=10).read())
print('\n=== RECOMMEND ===')
print(json.dumps(resp, indent=2, ensure_ascii=False))

# Test create-order (will return no_payment since no merchant configured)
data = json.dumps({'openid': 'test123', 'tier': 'pro', 'period': 'month'}).encode()
r = urllib.request.Request(f'{API}/api/create-order', data=data,
    headers={'Content-Type': 'application/json'})
resp = json.loads(urllib.request.urlopen(r, timeout=10).read())
print('\n=== CREATE ORDER ===')
print(json.dumps(resp, indent=2, ensure_ascii=False))
