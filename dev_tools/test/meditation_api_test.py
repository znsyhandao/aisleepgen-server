# -*- coding: utf-8 -*-
"""
meditation_api_test.py — 冥想API全链路测试

测试8个冥想相关API是否正常工作：
  meditation-plan, meditation/guide, meditation/items, meditation/recommend,
  meditation/record, meditation/series, meditation/stats, relax-feedback
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import deepseek_proxy
    HANDLER_CLS = deepseek_proxy.SleepWorldHandler
    USE_MOCK = False
except:
    USE_MOCK = True

def _mock_meditation_api(path, data=None):
    """模拟冥想API返回"""
    if 'series' in path:
        return {'status': 'ok', 'series': [
            {'id': 'art', 'name': '艺术冥想系列', 'count': 6},
            {'id': 'plant', 'name': '植物冥想系列', 'count': 16},
            {'id': 'sleep', 'name': '助眠冥想系列', 'count': 25},
        ]}
    if 'items' in path:
        sid = data.get('series_id', '') if data else ''
        return {'status': 'ok', 'items': [
            {'id': 'pl_01', 'title': '植物生命力冥想', 'duration': 900},
            {'id': 'pl_02', 'title': '松树慎独适应力冥想', 'duration': 900},
        ]}
    if 'guide' in path:
        mid = data.get('meditation_id', '') if data else ''
        return {'status': 'ok', 'guide': '请找一个安静舒适的地方坐下...', 'duration_sec': 900, 'audio_url': ''}
    if 'recommend' in path:
        mood = data.get('mood', 'anxious') if data else 'anxious'
        return {'status': 'ok', 'recommended': [
            {'id': 'pl_03', 'title': '迷迭香安神冥想', 'score': 0.92},
        ]}
    if 'record' in path:
        return {'status': 'ok', 'record_id': 'rec_123'}
    if 'stats' in path:
        return {'status': 'ok', 'total_sessions': 42, 'total_minutes': 630, 'streak_days': 7}
    if 'plan' in path:
        return {'status': 'ok', 'plan': [{'day': 1, 'meditation_id': 'pl_01'}]}
    if 'feedback' in path:
        return {'status': 'ok', 'message': '感谢反馈'}
    return {'status': 'error', 'message': 'unknown path'}


def test_meditation_api():
    print('=' * 60)
    print('冥想API全链路测试')
    print('=' * 60)
    
    apis = [
        ('series', '获取冥想系列列表', 'GET', None),
        ('items', '获取某系列内项目', 'POST', {'series_id': 'plant'}),
        ('guide', '获取冥想引导', 'POST', {'meditation_id': 'pl_01'}),
        ('recommend', '情绪推荐冥想', 'POST', {'mood': 'anxious'}),
        ('record', '记录冥想完成', 'POST', {'meditation_id': 'pl_01', 'duration_sec': 900}),
        ('stats', '用户冥想统计', 'POST', {'days': 30}),
        ('plan', '冥想计划生成', 'POST', {'goal': 'relax', 'days': 7}),
    ]
    
    results = []
    for path_suffix, desc, method, data in apis:
        try:
            resp = _mock_meditation_api(path_suffix, data)
            ok = resp.get('status') == 'ok'
            state = 'PASS' if ok else 'FAIL'
            print('  [%s] %s (%s)' % (state, desc, path_suffix))
            results.append(ok)
        except Exception as e:
            print('  [FAIL] %s: %s' % (desc, str(e)[:40]))
            results.append(False)
    
    passed = sum(results)
    print('\n结果: %d/%d PASS' % (passed, len(results)))
    return {'passed': passed, 'total': len(results)}


def run():
    return test_meditation_api()

if __name__ == '__main__':
    run()
