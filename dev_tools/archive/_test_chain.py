import requests, json
openid = "dev_098f6bcd4621d373"

# 手动写入测试数据
test_data = {
    'openid': openid,
    'profile': {
        'latest': {
            'bedtime': '23:00',
            'wake_time': '07:00',
            'sleep_latency': 15,
            'awake_times': 2,
            'total_duration': 420,
        },
        'last_survey': '2026-05-19T20:00:00Z',
        'user_info': {
            'nickname': '睡眠探索者',
            'main_issue': '入睡困难',
            'sleep_type': '夜猫型',
        }
    }
}

r = requests.post('http://localhost:8090/api/update-profile', json=test_data, timeout=10)
print(f'update-profile: {r.status_code}')
print(r.text[:300])

# 再读
r2 = requests.get(f'http://localhost:8090/api/user-profile?openid={openid}', timeout=10)
data = r2.json()
print(f'\nuser-profile latest: {json.dumps(data.get("latest",{}), ensure_ascii=False)}')
print(f'history长度: {len(data.get("history",[]))}')

# 现在发chat
r3 = requests.post('http://localhost:8090/api/chat', json={
    'messages': [{'role':'user','content':'睡前放松方法'}],
    'openid': openid
}, timeout=120)
reply = r3.json().get('reply','')
print(f'\nchat回复:\n{reply[:600]}')
