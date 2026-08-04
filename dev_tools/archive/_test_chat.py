import requests, json

openid = "dev_098f6bcd4621d373"

# 1. 查看当前profile有啥
r = requests.get(f'http://localhost:8090/api/user-profile?openid={openid}', timeout=10)
prof = r.json()
# 只看latest和user_info和history的前3条
latest = prof.get('latest', {})
user_info = prof.get('user_info', {})
history = prof.get('history', [])[:3]
print("=== latest ===")
print(json.dumps(latest, ensure_ascii=False, indent=2))
print("\n=== user_info ===")
print(json.dumps(user_info, ensure_ascii=False, indent=2))
print("\n=== history(前3) ===")
print(json.dumps(history, ensure_ascii=False, indent=2))

# 2. 发一个chat请求，看回复
print("\n\n=== chat请求 ===")
r2 = requests.post('http://localhost:8090/api/chat', json={
    'messages': [{'role':'user','content':'睡前放松方法'}],
    'openid': openid
}, timeout=120)
data = r2.json()
print("回复:", data.get('reply','')[:500])
