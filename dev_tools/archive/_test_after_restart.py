import json, urllib.request, sys
sys.stdout.reconfigure(encoding='utf-8')

req1 = urllib.request.Request('http://localhost:8090/api/user-profile?openid=dev_098f6bcd4621d373')
with urllib.request.urlopen(req1, timeout=10) as resp:
    data = json.loads(resp.read())
print('GET返回 latest keys:', list(data.get('latest',{}).keys()))

req2 = urllib.request.Request('http://localhost:8090/api/chat',
    data=json.dumps({'messages':[{'role':'user','content':'睡前放松方法'}],'openid':'dev_098f6bcd4621d373'}).encode(),
    headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req2, timeout=120) as resp:
    data = json.loads(resp.read())
reply = data.get('reply','')
print(f'chat回复:\n{reply[:800]}')
