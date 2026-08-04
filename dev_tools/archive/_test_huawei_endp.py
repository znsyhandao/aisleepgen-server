# -*- coding: utf-8 -*-
"""Test endpoints one at a time"""
import json, requests
import sys

tok = json.load(open(r'D:\AISleepGen_Optimized\data\huawei_token.json'))['access_token']
h = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}
p = {'startTime': '20260515000000', 'endTime': '20260515235959'}

for i, url in enumerate(sys.argv[1:3] if len(sys.argv) > 1 else []):
    try:
        r = requests.get(url, headers=h, params=p, timeout=10)
        name = url.rstrip('/').split('/')[-1]
        print(f'{i} {r.status_code} {name}: {r.text[:200]}')
    except Exception as e:
        print(f'{i} ERR: {e}')
