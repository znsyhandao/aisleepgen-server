import json, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\AISleepGen_Optimized\\user_profile.json', 'r', encoding='utf-8') as f:
    all_p = json.load(f)

uid = 'dev_e209266b333b1329'
p = all_p.get(uid, {})
print(f'=== {uid} ===')
print(f'keys: {sorted(p.keys())}')
lt = p.get('latest', {})
print(f'latest: {json.dumps(lt, ensure_ascii=False, indent=2)}')
ui = p.get('user_info', {})
print(f'user_info: {json.dumps(ui, ensure_ascii=False, indent=2)}')
meta = p.get('meta_params', {})
print(f'meta._initial_questionnaire: {meta.get("_initial_questionnaire", False)}')
h = p.get('history', [])
print(f'history: {len(h)}条')
if h:
    print(f'  最新一条: {json.dumps(h[-1], ensure_ascii=False)[:400]}')
