# -*- coding: utf-8 -*-
"""Test Huawei Health Kit API"""
import sys; sys.path.insert(0, r'D:\AISleepGen_Optimized')
from huawei_health_kit import TokenManager
import requests, json

mgr = TokenManager()
saved = mgr.load()
if not saved:
    print('No token saved')
    sys.exit(1)

token = saved['access_token']
print(f'Token: {token[:30]}...')
print(f'Token expires: {saved.get("expires_at", 0)}')
print()

headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
params = {'startTime': '20260515000000', 'endTime': '20260515235959'}

tests = [
    'https://health-api.cloud.huawei.com/healthkit/v1/sleep/record',
    'https://health-api.cloud.huawei.com/healthkit/v1/sleep/detail',
    'https://health-api.cloud.huawei.com/healthkit/v1/sleepSummary',
]

for url in tests:
    print(f'Trying: {url}')
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        print(f'  Status: {r.status_code}')
        if r.status_code == 200:
            data = r.json()
            print(f'  Success! Keys: {list(data.keys())[:15]}')
            print(f'  Data: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}')
        elif r.status_code == 401:
            print('  Token expired or scope issue')
        else:
            print(f'  Body: {r.text[:200]}')
    except Exception as e:
        print(f'  Error: {e}')
    print()
