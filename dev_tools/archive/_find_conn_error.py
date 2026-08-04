# -*- coding: utf-8 -*-
"""所有"连接好像不太稳定"出现位置分析"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'D:\AISleepGen_Optimized\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 所有出现
all_pos = []
pos = 0
while True:
    p = content.find('连接好像不太稳定', pos)
    if p < 0: break
    all_pos.append(p)
    pos = p + 1

print(f'出现 {len(all_pos)} 次:')
for p in all_pos:
    line = content[:p].count('\n') + 1
    # 前面的except行
    before = content[max(0,p-300):p]
    exc_idx = before.rfind('except ')
    exc_line_no = content[:p-300+exc_idx].count('\n') + 1 if exc_idx >= 0 else -1
    # 提取except附近的for/def/with上下文
    context_before = content[max(0,p-400):p]
    def_idx = context_before.rfind('def do_')
    func_area = context_before[def_idx:] if def_idx >= 0 else context_before[-200:]
    print(f'\n  L{line} (except在L{exc_line_no if exc_line_no>0 else "?"})')
    print(f'  上下文: {func_area[-150:].strip()[:120]}')
