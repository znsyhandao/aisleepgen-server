# -*- coding: utf-8 -*-
import json, os, sys
sys.stdout.reconfigure(encoding='utf-8')

fp = r'D:\super_frontier_radar\_pending_alerts.json'

# 过滤
with open(fp, 'r', encoding='utf-8') as f:
    d = json.load(f)
r = [x for x in d if x.get('key') and x.get('message')]
print(f'过滤前{len(d)}条, 过滤后{len(r)}条')
with open(fp, 'w', encoding='utf-8') as f:
    json.dump(r, f, ensure_ascii=False, indent=2)

# 确认
with open(fp, 'r', encoding='utf-8') as f:
    d2 = json.load(f)
for a in d2:
    s = a.get('severity', '?')
    k = a.get('key', '')
    m = a.get('message', '')[:60]
    print(f'  [{s}] {k}: {m}')
