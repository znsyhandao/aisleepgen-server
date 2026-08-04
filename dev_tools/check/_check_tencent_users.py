#!/usr/bin/env python3
import json, sys, os
os.chdir('/opt/aisleepgen')
sys.stdout.reconfigure(encoding='utf-8')

with open('user_profile.json', 'r') as f:
    p = json.load(f)

users = [k for k in p.keys() if k.startswith('dev_') or k == 'default']
print(f'Total users: {len(p)}, dev users: {len(users)}')

for uid in sorted(users)[:5]:
    up = p[uid]
    latest = up.get('latest', {})
    sd = latest.get('sleep_data', {}) or latest
    has_sleep = bool(sd.get('bedtime') or sd.get('total_duration'))
    history = up.get('history', [])
    score = latest.get('score', '?')
    done = up.get('onboarding_done', False)
    print(f'  {uid}: onboarding={done} has_sleep_data={has_sleep} history={len(history)} score={score}')
    if sd:
        bt = sd.get('bedtime','')
        wt = sd.get('wake_time','')
        td = sd.get('total_duration','')
        print(f'    sleep: {bt}->{wt} dur={td}')

# 看看最新填过问卷的用户
print(f'\nLatest updated:')
entries = sorted(p.items(), key=lambda x: x[1].get('latest',{}).get('_version',''), reverse=True)[:3]
for uid, up in entries:
    ver = up.get('latest',{}).get('_version','N/A')
    done = up.get('onboarding_done', False)
    # 只显示真正有上传数据的用户
    if done or 'sleep_data' in str(up.get('latest',{})):
        print(f'  {uid}: ver={ver} onboarding={done}')
