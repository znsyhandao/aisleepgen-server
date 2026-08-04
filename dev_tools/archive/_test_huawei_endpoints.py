# -*- coding: utf-8 -*-
"""Try multiple Huawei Health API endpoint patterns"""
import json, requests

tok = json.load(open(r'D:\AISleepGen_Optimized\data\huawei_token.json'))['access_token']
h = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}
p = {'startTime': '20260515000000', 'endTime': '20260515235959'}

endpoints = [
    'https://health-api.cloud.huawei.com/healthkit/v1/sleep/record',
    'https://health-api.cloud.huawei.com/healthkit/v1/sleep/records',
    'https://health-api.cloud.huawei.com/healthkit/v2/sleep/record',
    'https://health-api.cloud.huawei.com/health/v1.0/sleep/day',
    'https://health-api.cloud.huawei.com/healthkit/v1/activityRecord/sleep',
    'https://health-api.cloud.huawei.com/health/v1.0/healthkit/sleep',
    'https://health-api.cloud.huawei.com/healthkit/v1/daily/sleep',
    'https://health-api.cloud.huawei.com/health/v1.0/sleep',
    'https://health-api.cloud.huawei.com/healthkit/rest/v1/sleep',
]

for url in endpoints:
    try:
        r = requests.get(url, headers=h, params=p, timeout=5)
        name = url.rstrip('/').split('/')[-1]
        print(f'{r.status_code} {name}: {r.text[:100]}')
    except Exception as e:
        print(f'ERR {url.split("/")[-1]}: {e}')
