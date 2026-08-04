# -*- coding: utf-8 -*-
"""扫描所有实验尸体：找可挖的失败模式"""

import json, os, sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\AISleepGen_Optimized'
EXPT_DIR = os.path.join(BASE, 'data', 'experiments')

expts = [f for f in os.listdir(EXPT_DIR) if f.endswith('.json') and not f.startswith('_')]

dead = []
alive = []

for fn in expts:
    fp = os.path.join(EXPT_DIR, fn)
    try:
        with open(fp, 'r', encoding='utf-8') as f:
            d = json.load(f)
        st = d.get('status', d.get('_status', '?'))
        name = d.get('name', '?')
        knob = d.get('knob_key', '?')
        old_v = d.get('old_value', None)
        new_v = d.get('new_value', None)
        
        if st in ('rolled_back', 'abandoned', 'finished_inconclusive'):
            dead.append({
                'fn': fn, 'name': name, 'status': st,
                'knob': knob, 'old_val': old_v, 'new_val': new_v,
                'created': d.get('created_at', d.get('started_at', '')),
                'reason': d.get('rollback_reason', d.get('reap_reason', '')),
            })
        elif st in ('running', 'suspended'):
            alive.append({
                'fn': fn, 'name': name, 'knob': knob,
                'old_val': old_v, 'new_val': new_v,
            })
    except:
        pass

print(f'死亡实验: {len(dead)}')
print(f'存活实验: {len(alive)}')
print()

# 按 knob_key 看哪些参数被杀死了多次
knob_counter = Counter(d['knob'] for d in dead if d['knob'] != '?')
print('=== 死亡参数维度排名 ===')
for knob, count in knob_counter.most_common():
    print(f'  {knob:45s} x{count} 次被rollback')

# 看最高频死亡参数的详细
if knob_counter:
    worst_knob = knob_counter.most_common(1)[0][0]
    print(f'\n=== 最高频死亡参数: {worst_knob} ===')
    for d in dead:
        if d['knob'] == worst_knob:
            print(f'  {d["name"]:30s} old={d["old_val"]} new={d["new_val"]} reason={d["reason"]}')
    
    # 看所有参数的范围
    print(f'\n=== 值得挖掘的死亡参数 ===')
    for d in dead:
        if d['old_val'] is not None and d['new_val'] is not None:
            direction = 'UP↑' if d['new_val'] > d['old_val'] else 'DOWN↓'
            print(f'  {d["name"]:30s} {direction} {d["old_val"]}→{d["new_val"]}  knob={d["knob"][:40]}')
