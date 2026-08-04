"""
test_dev_user.py — 开发用户数据验证

模拟带 X-OpenID header 的微信小程序请求，
测试 update-profile + user-profile + chat 完整链路。
用法: python dev_tools/test/test_dev_user.py
"""
import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')

# 模拟小程序的请求——带 X-OpenID header
headers = {'Content-Type': 'application/json', 'X-OpenID': 'dev_e209266b333b1329'}
data = {
    'openid': 'dev_e209266b333b1329',
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

r = requests.post('http://localhost:8090/api/update-profile', json=data, headers=headers, timeout=10)
print('update-profile:', r.status_code, r.json())

# 读user_profile
r2 = requests.get('http://localhost:8090/api/user-profile?openid=dev_e209266b333b1329', timeout=10)
p = r2.json()
print(f'latest: {json.dumps(p.get("latest",{}), ensure_ascii=False, indent=2)}')

# 再发chat，模拟微信格式
r3 = requests.post('http://localhost:8090/api/chat', json={
    'message': '睡前放松方法',
    'history': [],
    'openid': 'dev_e209266b333b1329'
}, headers=headers, timeout=120)
reply = r3.json().get('reply', '')
print(f'\nChat:\n{reply[:500]}')
