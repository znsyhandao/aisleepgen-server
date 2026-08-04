#!/usr/bin/env python3
import json, os
os.chdir('/opt/aisleepgen')

with open('user_profile.json', 'r') as f:
    p = json.load(f)

d = p.get('dev_test_check', {})
print('onboarding_done:', d.get('onboarding_done'))
print('score:', d.get('latest', {}).get('score'))
sd = d.get('latest', {}).get('sleep_data', {}) or d.get('latest', {})
print('bedtime:', sd.get('bedtime', '?'))
