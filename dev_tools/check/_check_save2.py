#!/usr/bin/env python3
import json, os
os.chdir('/opt/aisleepgen')

with open('user_profile.json', 'r') as f:
    p = json.load(f)

# 找最新写入的用户
for uid in ['default', 'dev_phone_test', 'dev_test_check']:
    if uid in p:
        d = p[uid]
        lt = d.get('latest', {})
        print(f'{uid}:')
        print(f'  onboarding_done: {d.get("onboarding_done")}')
        print(f'  _initial_questionnaire: {d.get("meta_params",{}).get("_initial_questionnaire")}')
        print(f'  latest keys: {list(lt.keys())[:5]}')
        sd = lt.get('sleep_data', {}) or lt
        print(f'  bedtime: {sd.get("bedtime","?")}')
        print(f'  score: {lt.get("score","?")}')
    else:
        print(f'{uid}: NOT FOUND')
