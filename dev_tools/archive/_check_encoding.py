# -*- coding: utf-8 -*-
import sys, os

sys.stdout.reconfigure(encoding='utf-8')
fp = r'D:\super_frontier_radar\heartbeat_orchestrator.py'
with open(fp, 'r', encoding='utf-8') as f:
    c = f.read()

# 检查文件中unicode转义的状态
# 先看是否有已被替换的内容
for i, ch in enumerate(c[1000:1100]):
    if ord(ch) > 127:
        print(f'pos {i}: U+{ord(ch):04X} = {ch}')
        break

print(f'文件长度: {len(c)}')

# 检查关键词
keywords = ['ADV', 'GRIM', 'HYPO', 'DECODE', '双脑', '压缩', '行为']
for kw in keywords:
    if kw in c:
        idx = c.index(kw)
        start = max(0, idx-10)
        end = min(len(c), idx+len(kw)+20)
        snippet = c[start:end]
        print(f'found "{kw}" at pos {idx}: ...{snippet}...')
