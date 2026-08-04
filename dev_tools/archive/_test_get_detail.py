import json, urllib.request, sys
sys.stdout.reconfigure(encoding='utf-8')

url = 'http://localhost:8090/api/user-profile?openid=dev_098f6bcd4621d373'
req = urllib.request.Request(url)
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read())
print('返回的所有keys:', sorted(data.keys()))
print('has latest:', 'latest' in data)
if 'latest' in data:
    print('latest:', json.dumps(data['latest'], ensure_ascii=False))
print('has user_info:', 'user_info' in data)
if 'user_info' in data:
    print('user_info:', json.dumps(data['user_info'], ensure_ascii=False))
# 看有没有 onboarding_done
print('onboarding_done:', data.get('onboarding_done'))
