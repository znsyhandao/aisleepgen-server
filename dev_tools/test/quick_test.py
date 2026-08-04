"""
quick_test.py — 快速测试

向 localhost:8090 发 chat 请求测试 AI 对话正常。
用法: python dev_tools/test/quick_test.py (需服务运行)
"""
import urllib.request, json
API = 'http://82.156.208.245:8090'

def post(path, data):
    body = json.dumps(data).encode()
    r = urllib.request.Request(API+path, data=body,
        headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(r, timeout=10).read())

print('=== Cold user test123 ===')
r1 = post('/api/recommend-tier', {'openid': 'test123'})
for k, v in r1.items():
    print(f'  {k}: {v}')

print()
print('=== Heavy user test_heavy ===')
r2 = post('/api/recommend-tier', {'openid': 'test_heavy'})
for k, v in r2.items():
    print(f'  {k}: {v}')
