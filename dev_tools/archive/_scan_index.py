# -*- coding: utf-8 -*-
"""分析首页结构"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'D:\AISleepGen_Optimized\miniprogram\pages\index\index.wxml', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f'总行数: {len(lines)}')
# 找到所有包含 quick/chat/绑定/唤醒 关键字的行
for i, l in enumerate(lines, 1):
    for kw in ['quick', 'grid', 'chat', '绑定', '唤醒', '手环', '扫描']:
        if kw in l:
            print(f'L{i}: {l.rstrip()[:120]}')
            break
