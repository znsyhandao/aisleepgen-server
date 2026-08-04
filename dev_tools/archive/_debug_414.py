# -*- coding: utf-8 -*-
with open(r'D:\AISleepGen_Optimized\dp_router.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i in range(414, 425):
    if i < len(lines):
        print(f'{i+1}: {lines[i].rstrip()[:100]}')
