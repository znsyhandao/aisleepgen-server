import json, os, urllib.request, sys
sys.stdout.reconfigure(encoding='utf-8')

pf_path = 'D:\\AISleepGen_Optimized\\user_profile.json'
with open(pf_path, 'r', encoding='utf-8') as f:
    all_profiles = json.load(f)
print('文件中的用户数:', len(all_profiles))
for uid, p in all_profiles.items():
    lt = p.get('latest', {})
    print(f'  {uid[:16]}: latest keys={list(lt.keys())}')

# GET 接口
req = urllib.request.Request('http://localhost:8090/api/user-profile?openid=dev_098f6bcd4621d373')
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read())
print(f'GET返回 latest keys: {list(data.get("latest",{}).keys())}')
