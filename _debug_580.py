# -*- coding: utf-8 -*-
with open(r'D:\AISleepGen_Optimized\dp_router.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(576, 585):
    if i < len(lines):
        indent = len(lines[i]) - len(lines[i].lstrip())
        print(f'{i+1}: indent={indent} |{lines[i].rstrip()[:80]}')
