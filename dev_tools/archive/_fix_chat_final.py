# -*- coding: utf-8 -*-
"""chat.js 一次性最终修复"""
with open('miniprogram/pages/chat/chat.js', 'r', encoding='utf-8') as f:
    c = f.read()

# 修复1: 那个多的 } 造成 =248
# 找到第1012行附近: 多余的 })
lines = c.split('\n')
# 检查函数最后5行
for i in range(len(lines)-5, len(lines)):
    print('L%d: %s' % (i+1, lines[i][:40]))

print('---')

# 实际上多余的 } 可能在 loadTimeline 函数末尾
# L949-952: 
for i in range(949, 955):
    if i < len(lines):
        print('L%d: %s' % (i+1, lines[i][:40]))
