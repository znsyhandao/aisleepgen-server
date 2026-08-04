import json, sys
sys.stdout.reconfigure(encoding='utf-8')
with open('D:\\AISleepGen_Optimized\\user_profile.json', 'r', encoding='utf-8') as f:
    all_p = json.load(f)

for uid in ['default', 'dev_098f6bcd4621d373']:
    p = all_p.get(uid, {})
    print(f'\n=== {uid[:20]} ===')
    print('latest:', json.dumps(p.get('latest', {}), ensure_ascii=False, indent=2))
    print('user_info:', json.dumps(p.get('user_info', {}), ensure_ascii=False, indent=2))
    print('meta _initial_questionnaire:', p.get('meta_params', {}).get('_initial_questionnaire', False))
    print('history:', len(p.get('history', [])))
    h = p.get('history', [])
    if h:
        print('  last entry type:', h[-1].get('type', ''))
        print('  last entry keys:', list(h[-1].keys()))
        print('  last extracted:', json.dumps(h[-1].get('extracted', {}), ensure_ascii=False))
