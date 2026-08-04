# -*- coding: utf-8 -*-
"""Test with actual function from huawei_health_kit"""
import sys; sys.path.insert(0, r'D:\AISleepGen_Optimized')
from huawei_health_kit import fetch_sleep_data, get_valid_token, HEALTH_API_BASE

token = get_valid_token()
print(f'Token valid: {token[:20]}...')
print(f'HEALTH_API_BASE: {HEALTH_API_BASE}')

# Try the exact fetch_sleep_data function
result = fetch_sleep_data(token, '20260515')
print(f'\nResult: {result}')
print(f'Available: {result.get("available")}')
if result.get('raw'):
    print(f'Raw (keys): {list(result["raw"].keys())[:10]}')
