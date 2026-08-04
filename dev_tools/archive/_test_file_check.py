import json, sys, os
sys.stdout.reconfigure(encoding='utf-8')

# 直接读user_profile.json
with open('D:\\AISleepGen_Optimized\\user_profile.json', 'r', encoding='utf-8') as f:
    all_p = json.load(f)

uid = 'dev_098f6bcd4621d373'
p = all_p.get(uid, {})
print(f'文件中的profile keys: {sorted(p.keys())}')
print(f'latest: {json.dumps(p.get("latest",{}), ensure_ascii=False)}')
print(f'user_info: {json.dumps(p.get("user_info",{}), ensure_ascii=False)}')
print(f'history条数: {len(p.get("history",[]))}')
print(f'history内容: {json.dumps(p.get("history",[])[:2], ensure_ascii=False, indent=2)}')
