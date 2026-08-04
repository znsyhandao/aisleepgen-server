import json, urllib.request, sys
sys.stdout.reconfigure(encoding='utf-8')

# === 1. 写入 default 用户的扁平 latest 数据 ===
update = json.dumps({
    'openid': 'default',
    'profile': {
        'latest': {
            'bedtime': '23:00',
            'wake_time': '07:00',
            'sleep_latency': 15,
            'awake_times': 2,
            'total_duration': 420,
        },
        'last_survey': '2026-05-19T20:00:00.000Z',
    }
}).encode()
req = urllib.request.Request('http://localhost:8090/api/update-profile', data=update,
    headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req, timeout=10) as resp:
    print('update-profile:', resp.status)

# === 2. 读 GET 接口确认 latest ===
req = urllib.request.Request('http://localhost:8090/api/user-profile?openid=default')
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read())
print(f'GET latest: {data.get("latest", {})}')

# === 3. 问"你知道我几点睡几点起吗？" ===
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
print(f'\nChat reply:\n{reply[:600]}')
