#!/usr/bin/env python3
"""更新 _build_actionable_takeaway 调用处传 data"""
path = r'D:\AISleepGen_Optimized\sleep_world_model.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = "'primary_focus': self._build_actionable_takeaway(round2, all_findings, all_risks),"
new = "'primary_focus': self._build_actionable_takeaway(round2, all_findings, all_risks, sleep_data=data),"

count = content.count(old)
print(f"Found {count} occurrence(s)")
if count == 1:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("OK")
else:
    print("FAIL")
    idx = content.find(old[:30])
    if idx >= 0:
        print(content[idx:idx+200])
