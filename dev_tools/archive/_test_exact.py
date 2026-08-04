import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')

# === 直接用和微信小程序完全相同的格式发请求 ===
openid = 'default'
message = '睡前放松方法'
history = []

# 先确保 default 有数据
update = {
    'openid': openid,
    'profile': {
        'latest': {
            'bedtime': '23:00',
            'wake_time': '07:00',
            'sleep_latency': 15,
            'awake_times': 2,
            'total_duration': 420,
        },
    }
}
r = requests.post('http://localhost:8090/api/update-profile', json=update, timeout=10)
print('update-profile:', r.status_code, r.json())

# 用wx格式：message 而不是 messages
payload = {
    'message': message,
    'history': [],
    'openid': openid,
}
r2 = requests.post('http://localhost:8090/api/chat', json=payload, timeout=120)
data = r2.json()
reply = data.get('reply', '')
print(f'\nChat回复:\n{reply[:500]}')

# 检查 user-profile GET 看看 latest
r3 = requests.get(f'http://localhost:8090/api/user-profile?openid={openid}', timeout=10)
p = r3.json()
print(f'\nGET latest: {json.dumps(p.get("latest",{}), ensure_ascii=False)}')
