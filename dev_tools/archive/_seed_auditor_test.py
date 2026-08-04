#!/usr/bin/env python3
"""注入模拟数据验证 decision_auditor.py 的完整链路"""
import json, os
from datetime import datetime, timedelta

BASE = r'D:\AISleepGen_Optimized\data'
TRACE_PATH = os.path.join(BASE, 'decision_traces.jsonl')
HOC_PATH = os.path.join(BASE, 'decision_hoc.jsonl')
CAL_PATH = os.path.join(BASE, 'decision_calibration.json')

test_user = 'test_user_harness'

# ===== 生成模拟 trace（8条，5-8天前的决策）=====
traces = []
for i in range(8):
    days_ago = 5 + i
    dt = datetime.now() - timedelta(days=days_ago)
    tid = f'sim_{int(dt.timestamp())}_{i}'

    types = ['push_morning', 'sleep_consolidation', 'anomaly_alert',
             'weekly_integration', 'push_evening', 'silence_care',
             'push_morning', 'anomaly_alert']
    confs = [0.85, 0.65, 0.90, 0.50, 0.75, 0.30, 0.80, 0.95]
    preds = [0.50, 0.30, -0.20, 0.10, 0.40, -0.10, 0.45, -0.30]

    # 前6条是实际决策（3天后会评估），后2条还未到期
    actuals = [0.42, 0.18, -0.15, -0.05, 0.35, -0.08, None, None]
    doc_done = True if actuals[i] is not None else False
    doc_ts = (dt + timedelta(days=3)).isoformat(timespec='seconds') if doc_done else None

    traces.append({
        'trace_id': tid,
        'openid': test_user,
        'timestamp': dt.isoformat(timespec='seconds'),
        'type': types[i],
        'context': {'simulated': True, 'day': i},
        'pred_impact': preds[i],
        'confidence': confs[i],
        'actual_impact': actuals[i],
        'hoc_filled': doc_done,
        'hoc_timestamp': doc_ts,
    })

with open(TRACE_PATH, 'w', encoding='utf-8') as f:
    for t in traces:
        f.write(json.dumps(t, ensure_ascii=False) + '\n')
print('traces:', len(traces), 'lines')

# ===== 生成模拟 hoc 队列（前6条已完成，后2条待处理）=====
hoc_entries = []
for i in range(8):
    days_ago = 5 + i
    dt = datetime.now() - timedelta(days=days_ago)
    due = (dt + timedelta(days=3)).strftime('%Y-%m-%d')

    types = ['push_morning', 'sleep_consolidation', 'anomaly_alert',
             'weekly_integration', 'push_evening', 'silence_care',
             'push_morning', 'anomaly_alert']
    confs = [0.85, 0.65, 0.90, 0.50, 0.75, 0.30, 0.80, 0.95]
    preds = [0.50, 0.30, -0.20, 0.10, 0.40, -0.10, 0.45, -0.30]

    filled = i < 6  # 前6条已回填

    hoc_entries.append({
        'trace_id': f'sim_{int(dt.timestamp())}_{i}',
        'openid': test_user,
        'decision_type': types[i],
        'timestamp': dt.isoformat(timespec='seconds'),
        'predicted_impact': preds[i],
        'confidence': confs[i],
        'hoc_window_days': 3,
        'due_date': due,
        'hoc_filled': filled,
        'actual_impact': traces[i]['actual_impact'],
        'hoc_timestamp': traces[i]['hoc_timestamp'],
    })

with open(HOC_PATH, 'w', encoding='utf-8') as f:
    for e in hoc_entries:
        f.write(json.dumps(e, ensure_ascii=False) + '\n')
print('hoc queue:', len(hoc_entries), 'entries')

print()
print('=== 数据注入完成 ===')
print(f'  - 6条已完成 post-hoc（actual_impact 已填）')
print(f'  - 2条待 post-hoc（due_date 未到）')
print()
print('现在运行:')
print('  python decision_auditor.py dashboard')
print('  python decision_auditor.py hoc')
print('  python decision_auditor.py calibrate')
