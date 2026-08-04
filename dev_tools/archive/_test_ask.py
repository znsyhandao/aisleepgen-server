import json, urllib.request, sys
sys.stdout.reconfigure(encoding='utf-8')

openid = 'dev_098f6bcd4621d373'

# 用户问：你知道我几点睡几点起吗？
body = json.dumps({
    'messages': [{'role':'user','content':'你知道我几点睡几点起吗？'}],
    'openid': openid
}).encode()

req = urllib.request.Request('http://localhost:8090/api/chat', data=body,
    headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req, timeout=120) as resp:
    data = json.loads(resp.read())

reply = data.get('reply', '')
print(reply)
