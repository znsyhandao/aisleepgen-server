import json, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\AISleepGen_Optimized\\user_profile.json', 'r', encoding='utf-8') as f:
    all_p = json.load(f)

for uid, p in all_p.items():
    is_test = uid.startswith('test_') or uid == 'nonexistent_user'
    meta = p.get('meta_params', {})
    history = p.get('history', [])
    latest = p.get('latest', {})
    ui = p.get('user_info', {})
    
    if is_test:
        continue
    
    has_history = len(history) > 0
    has_onsurvey = meta.get('_initial_questionnaire', False)
    has_latest = bool(latest and 
        (latest.get('bedtime') or latest.get('sleep_data', {}).get('bedtime')))
    
    # 看 user_info 里的睡眠核心字段
    mi = ui.get('main_issue', '')
    st = ui.get('sleep_type', '')
    sl = ui.get('stress_level', '')
    
    lt_bed = ''
    if latest.get('bedtime'):
        lt_bed = latest['bedtime']
    elif latest.get('sleep_data', {}).get('bedtime'):
        lt_bed = latest['sleep_data']['bedtime']
    
    print(f'{uid[:20]:20} 问卷={has_onsurvey} | history={has_history} | latest={has_latest} | 主诉={mi} 类型={st} 压力={sl} | bedtime={lt_bed}')
