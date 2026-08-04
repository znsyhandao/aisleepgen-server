import json, sys
sys.stdout.reconfigure(encoding='utf-8')
with open('D:\\AISleepGen_Optimized\\user_profile.json', 'r', encoding='utf-8') as f:
    all_p = json.load(f)

print('用户总数:', len(all_p))
for uid, p in all_p.items():
    lt = p.get('latest', {})
    ui = p.get('user_info', {})
    has_latest = bool(lt)
    has_history = bool(p.get('history'))
    has_meta = bool(p.get('meta_params', {}).get('_initial_questionnaire'))
    nick = ui.get('nickname', '')
    short = uid[:12] if uid != 'default' else uid
    print(f'  {short:12} latest={has_latest} history={has_history} meta={has_meta} nick={nick}')
