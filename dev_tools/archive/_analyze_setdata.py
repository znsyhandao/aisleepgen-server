# -*- coding: utf-8 -*-
"""精确定位butlerCheck中的setData注入点"""
import sys, json
sys.stdout.reconfigure(encoding='utf-8')

with open(r'D:\AISleepGen_Optimized\miniprogram\pages\chat\chat.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 找butlerCheck().then
idx = content.find('butlerCheck().then')
if idx < 0:
    print('找不到 butlerCheck().then')
    exit()

# 从这个位置往后找第一个 setData({
setdata_idx = content.find('setData({', idx)
if setdata_idx < 0:
    print('找不到 setData')
    exit()

# 提取setData的内容到对应的}
depth = 0
start = setdata_idx + len('setData({')
for i in range(start, len(content)):
    if content[i] == '{': depth += 1
    if content[i] == '}': 
        if depth == 0:
            print(f'setData 内容 ({start} -> {i}):')
            safe = content[start:i]
            ascii_safe = ''.join(c if ord(c) < 128 else '?' for c in safe)
            print(ascii_safe[:600])
            break
        depth -= 1

print(f'\n---\n活跃语句索引: setData开头={setdata_idx}')
