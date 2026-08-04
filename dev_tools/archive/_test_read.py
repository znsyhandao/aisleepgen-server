import requests, json
openid = "dev_098f6bcd4621d373"

# 1. 读 GET 接口
r = requests.get(f'http://localhost:8090/api/user-profile?openid={openid}', timeout=10)
data = r.json()
print('GET /api/user-profile latest:', json.dumps(data.get('latest',{}), ensure_ascii=False))

# 2. 再发 chat
r2 = requests.post('http://localhost:8090/api/chat', json={
    'messages': [{'role':'user','content':'睡前放松方法'}],
    'openid': openid
}, timeout=120)
reply = r2.json().get('reply','')
print(f'\nchat回复:\n{reply[:800]}')
