import urllib.request, json, time

API = 'http://82.156.208.245:8090'

time.sleep(3)  # wait for server restart

# Health
r = urllib.request.Request(f'{API}/health')
resp = json.loads(urllib.request.urlopen(r, timeout=10).read())
print('Health:', resp.get('status'))

# Recommend
data = json.dumps({'openid': 'test123'}).encode()
r = urllib.request.Request(f'{API}/api/recommend-tier', data=data,
    headers={'Content-Type': 'application/json'})
resp = json.loads(urllib.request.urlopen(r, timeout=10).read())
print()
print('=== RECOMMENDATION ===')
for k, v in resp.items():
    print(f'  {k}: {v}')
print()
print('ALL OK')
