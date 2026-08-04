# -*- coding: utf-8 -*-
"""分析前端JS，找butler检查函数和quickReplies注入点"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'D:\AISleepGen_Optimized\miniprogram\pages\chat\chat.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 找 all functions/vars related to butler
targets = ['checkButler', 'butlerCheck', 'ButlerScheduler', 'butler_item', 'butler-bar', 'butlerAlert', 'quickReplies']
for t in targets:
    idx = content.find(t)
    print(f'{t}: {idx}')
    if idx >= 0:
        # Extract a safe snippet (ASCII only)
        snippet = content[idx:idx+300]
        ascii_snippet = ''.join(c if ord(c) < 128 else '?' for c in snippet)
        print(f'  -> {ascii_snippet[:250]}')
    print()

# Also find the onQuickQuestion handler
idx = content.find('onQuickQuestion')
print(f'onQuickQuestion: {idx}')
if idx >= 0:
    snippet = content[idx:idx+500]
    ascii_snippet = ''.join(c if ord(c) < 128 else '?' for c in snippet)
    print(f'  -> {ascii_snippet}')
