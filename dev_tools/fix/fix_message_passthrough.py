#!/usr/bin/env python3
"""更新 world_model_coordinator.py: message 传给 comprehensive_analysis"""
import sys

path = r'D:\AISleepGen_Optimized\world_model_coordinator.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 替换 feeling: 'auto' 为 feeling: message if message else 'auto'
old = "'feeling': 'auto'"
new = "'feeling': message if message else 'auto'"
count = content.count(old)
if count == 1:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"OK: feeling updated ({old} -> {new})")
else:
    print(f"FAIL: found {count} occurrences of {old}")
    idx = content.find(old)
    if idx >= 0:
        print(content[max(0,idx-50):idx+100])
