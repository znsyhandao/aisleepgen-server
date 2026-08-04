# -*- coding: utf-8 -*-
"""读懂feedback数据模式：确定feedback_short_circuit的参数阈值"""

import json, os, time
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\AISleepGen_Optimized'

# 读feedback
fb_path = os.path.join(BASE, 'data', 'feedback.json')
with open(fb_path, 'r', encoding='utf-8') as f:
    fbs = json.load(f)

print(f'总反馈: {len(fbs)}')
print(f'非reg_test: {sum(1 for f in fbs if f.get("openid","") != "reg_test")}')
print(f'非test: {sum(1 for f in fbs if f.get("openid","") not in ("reg_test","test"))}')

# 提取数字型反馈维度的分布
fields_of_interest = ['rating', 'pain', 'mood', 'anxiety', 'energy', 'sleep_score',
                      'satisfaction', 'wakeup_mood', 'efficiency', 'awake',
                      'recovering', 'depth', 'latency', 'stress_level']

for field in fields_of_interest:
    vals = [f[field] for f in fbs if field in f and f[field] is not None]
    if not vals:
        continue
    minv, maxv = min(vals), max(vals)
    # 只看非reg_test
    real_vals = [f[field] for f in fbs if field in f and f[field] is not None and f.get('openid','') not in ('reg_test','test')]
    print(f'  {field:20s} n={len(vals):3d} 范围={minv}~{maxv}  (real: {len(real_vals)})')

# 看rating分布
ratings = [f.get('rating') for f in fbs if f.get('rating') is not None]
from collections import Counter
r_counts = Counter(ratings)
print(f'\n评分分布:')
for r, c in sorted(r_counts.items()):
    print(f'  {r}: {c}条')

# 看是否有时序模式（按时间顺序的rating）
ts_ratings = sorted([(f.get('time',''), f.get('rating')) for f in fbs if f.get('rating') is not None and f.get('time')])
print(f'\n最后10个评分(按时间):')
for t, r in ts_ratings[-10:]:
    print(f'  {t[:16]:16s} → {r}')
