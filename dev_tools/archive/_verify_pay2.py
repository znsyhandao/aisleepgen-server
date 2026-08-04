import urllib.request, json, sys

API = 'http://82.156.208.245:8090'

# Test pricing
r = urllib.request.Request(f'{API}/api/pricing')
resp = json.loads(urllib.request.urlopen(r, timeout=5).read())
print('=== PRICING ===')
print('pricing keys:', list(resp.get('pricing', {}).keys()))
p = resp.get('pricing', {})
for k, v in p.items():
    print(f'  {k}: price={v.get("price")}, quarter={v.get("price_quarter")}, year={v.get("price_year")}')

# Test recommend
data = json.dumps({'openid': 'test123'}).encode()
r = urllib.request.Request(f'{API}/api/recommend-tier', data=data,
    headers={'Content-Type': 'application/json'})
resp = json.loads(urllib.request.urlopen(r, timeout=10).read())
print('\n=== RECOMMEND ===')
for k, v in resp.items():
    print(f'  {k}: {v}')

# Test create-order
data = json.dumps({'openid': 'test123', 'tier': 'pro', 'period': 'month'}).encode()
r = urllib.request.Request(f'{API}/api/create-order', data=data,
    headers={'Content-Type': 'application/json'})
resp = json.loads(urllib.request.urlopen(r, timeout=10).read())
print('\n=== CREATE ORDER ===')
for k, v in resp.items():
    print(f'  {k}: {v}')
