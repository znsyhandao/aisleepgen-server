import json, urllib.request, sys
sys.stdout.reconfigure(encoding='utf-8')

# 用 default openid 模拟微信小程序的 chat 请求
body = json.dumps({
    'message': '你知道我几点睡几点起吗？',
    'history': [],
    'openid': 'default'
}).encode()

req = urllib.request.Request('http://localhost:8090/api/chat', data=body,
    headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req, timeout=120) as resp:
    data = json.loads(resp.read())
reply = data.get('reply', '')
print(reply[:500])
