import requests, json
openid = "dev_098f6bcd4621d373"

# 完全模拟survey.js的提交格式
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
        'last_survey': '2026-05-19T20:00:00.000Z',
    }
}

print("发送数据:")
print(json.dumps(test_data, ensure_ascii=False, indent=2))

r = requests.post('http://localhost:8090/api/update-profile', json=test_data, timeout=10)
print(f'\n响应: {r.status_code}')
print(r.text[:500])

# 读user_profile.json 查看实际写入
import os
pf_path = os.path.join('D:\\AISleepGen_Optimized', 'user_profile.json')
with open(pf_path, 'r', encoding='utf-8') as f:
    all_profiles = json.load(f)
my_pf = all_profiles.get(openid, {})
print(f'\n=== user_profile.json 中 {openid[:16]} 的latest ===')
print(json.dumps(my_pf.get('latest', {}), ensure_ascii=False, indent=2))
print(f'history: {len(my_pf.get("history",[]))}条')
