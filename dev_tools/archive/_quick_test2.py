import urllib.request, json, sys
API = 'http://82.156.208.245:8090'

def post(path, data):
    body = json.dumps(data).encode()
    r = urllib.request.Request(API+path, data=body,
        headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(r, timeout=10).read())

sys.stdout = open(1, 'w', encoding='utf-8', errors='replace')

print('=== Cold user test123 ===')
r1 = post('/api/recommend-tier', {'openid': 'test123'})
for k, v in r1.items():
    v_str = str(v) if not isinstance(v, str) else v
    print(f'  {k}: {v_str}')

print()
print('=== Heavy user test_heavy ===')
r2 = post('/api/recommend-tier', {'openid': 'test_heavy'})
for k, v in r2.items():
    v_str = str(v) if not isinstance(v, str) else v
    print(f'  {k}: {v_str}')
