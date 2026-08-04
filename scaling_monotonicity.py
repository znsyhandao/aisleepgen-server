#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scaling_monotonicity.py — Scaling Monotonicity监控 (v7.5+)
原理: Anthropic Scaling Monotonicity — 检查效果是否随数据/算力递增而单调提升
落地: 自动检测 AISleepGen 各专家的"数据量->评分准确性"的单调性
"""


def check_monotonicity(records, min_window=3):
    """检查评分是否随数据量单调提升"""
    if not records or len(records) < min_window * 2:
        return {'monotonic': None, 'note': '数据不足(%d条)' % len(records), 'samples': len(records)}

    confidences = []
    for rec in records:
        if isinstance(rec, dict):
            c = rec.get('confidence') or rec.get('wm_score')
            if c is not None:
                try:
                    confidences.append(float(c))
                except (ValueError, TypeError):
                    pass

    if len(confidences) < min_window * 2:
        return {'monotonic': None, 'note': '置信度数据不足', 'samples': len(confidences)}

    mid = len(confidences) // 2
    before = confidences[:mid]
    after = confidences[mid:]
    before_avg = sum(before) / len(before) if before else 0
    after_avg = sum(after) / len(after) if after else 0
    delta = round(after_avg - before_avg, 3)

    return {
        'monotonic': delta >= -0.01,
        'before_avg': round(before_avg, 3),
        'after_avg': round(after_avg, 3),
        'delta': delta,
        'samples': len(confidences),
    }


def get_monotonicity_report(history_records):
    """完整的单调性报告"""
    report = check_monotonicity(history_records)
    if report.get('monotonic') is None:
        return report
    status = 'OK' if report['monotonic'] else 'WARN'
    return {
        'status': status,
        'before_avg': report['before_avg'],
        'after_avg': report['after_avg'],
        'delta': report['delta'],
        'samples': report['samples'],
        'summary': '%s: %.2f -> %.2f (delta=%+.2f)' % (
            status, report['before_avg'], report['after_avg'], report['delta']
        ),
    }


# ===== 自测 =====
if __name__ == '__main__':
    print('=== Scaling Monotonicity Test ===\n')

    # Test 1: monotonic increase
    r = get_monotonicity_report([{'confidence': i * 2 + 50} for i in range(10)])
    print('Test 1 (increase): status=%s, delta=%.2f' % (r.get('status'), r.get('delta', 0)))
    assert r['status'] == 'OK'

    # Test 2: monotonic decrease
    r2 = get_monotonicity_report([{'confidence': 90 - i * 5} for i in range(10)])
    print('Test 2 (decrease): status=%s, delta=%.2f' % (r2.get('status'), r2.get('delta', 0)))
    assert r2['status'] == 'WARN'

    # Test 3: insufficient data
    r3 = get_monotonicity_report([{'confidence': 50}])
    print('Test 3 (short): note=%s' % r3.get('note', ''))
    assert r3['monotonic'] is None

    print('\nAll tests passed!')
