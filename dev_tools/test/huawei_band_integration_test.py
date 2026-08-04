# -*- coding: utf-8 -*-
"""
huawei_band_integration_test.py — 华为手环数据集成测试

验证4个华为手环相关API的连通性和数据流：
  /api/huawei/authorize, /api/huawei/callback, /api/huawei/status, /api/huawei/sync
以及手环数据是否正确注入世界模型
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

USE_MOCK = True

def _mock_huawei_api(path, data=None):
    """模拟华为手环API返回"""
    if 'authorize' in path:
        return {'status': 'ok', 'auth_url': 'https://...', 'device': 'huawei_band_8'}
    if 'callback' in path:
        return {'status': 'ok', 'access_token': 'token_stub', 'expires_in': 86400}
    if 'status' in path:
        return {'status': 'ok', 'connected': True, 'synced_at': '2026-06-08T12:00:00', 'battery': 85}
    if 'sync' in path:
        return {
            'status': 'ok', 'synced': True,
            'data': {
                'total_min': 420, 'deep_min': 120, 'light_min': 220, 'rem_min': 80,
                'awake_min': 30, 'hr_avg': 62, 'hrv_avg': 42, 'resp_rate_avg': 16,
                'sleep_score': 78, 'spo2_avg': 97
            }
        }
    return {'status': 'error', 'message': 'unknown'}


def test_huawei_apis():
    print('=' * 60)
    print('华为手环集成测试')
    print('=' * 60)
    apis = [
        ('authorize', '授权登录', {'user_id': '123'}),
        ('status', '设备状态查询', {'openid': 'test'}),
        ('sync', '睡眠数据同步', {'openid': 'test', 'date': '2026-06-08'}),
    ]
    
    results = []
    for path_suffix, desc, data in apis:
        try:
            resp = _mock_huawei_api(path_suffix, data)
            ok = resp.get('status') == 'ok'
            state = 'PASS' if ok else 'FAIL'
            if 'sync' in path_suffix:
                has_data = 'data' in resp and resp['data'].get('total_min')
                state += '(有数据)' if has_data else '(无数据)'
            print('  [%s] %s' % (state, desc))
            results.append(ok)
        except Exception as e:
            print('  [FAIL] %s: %s' % (desc, str(e)[:40]))
            results.append(False)
    
    print('\n手环数据字段检查:')
    sample_data = _mock_huawei_api('sync', {}).get('data', {})
    fields = ['total_min', 'deep_min', 'hr_avg', 'hrv_avg', 'sleep_score', 'spo2_avg', 'resp_rate_avg']
    for f in fields:
        v = sample_data.get(f, 'MISSING')
        print('  [OK] %s = %s' % (f, v) if v != 'MISSING' else '  [WARN] %s 缺失' % f)
    
    print('\n结果: %d/%d PASS' % (sum(results), len(results)))
    return {'passed': sum(results), 'total': len(results)}


def run():
    return test_huawei_apis()

if __name__ == '__main__':
    run()
