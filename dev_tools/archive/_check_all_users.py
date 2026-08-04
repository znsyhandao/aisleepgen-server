import json, sys
sys.stdout.reconfigure(encoding='utf-8')

# 看所有非 test_ 用户的数据
with open('D:\\AISleepGen_Optimized\\user_profile.json', 'r', encoding='utf-8') as f:
    all_p = json.load(f)

for uid, p in all_p.items():
    if uid.startswith('test_') or uid == 'nonexistent_user':
        continue
    lt = p.get('latest', {})
    meta = p.get('meta_params', {})
    history = p.get('history', [])
    ui = p.get('user_info', {})
    
    print(f'\n=== {uid} ===')
    print(f'meta._initial_questionnaire: {meta.get("_initial_questionnaire", False)}')
    print(f'user_info: {json.dumps(ui, ensure_ascii=False)}')
    print(f'latest: {json.dumps(lt, ensure_ascii=False, indent=2)}')
    
    sd = lt.get('sleep_data', {})
    if sd:
        print(f'latest.sleep_data: {json.dumps(sd, ensure_ascii=False)}')
    
    if history:
        print(f'history[{len(history)}] last: {json.dumps(history[-1], ensure_ascii=False)[:300]}')
    else:
        print('history: []')
