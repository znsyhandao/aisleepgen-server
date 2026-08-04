# -*- coding: utf-8 -*-
"""分析_handle_chat结构"""
import sys, re
sys.stdout.reconfigure(encoding='utf-8')

content = open(r'D:\AISleepGen_Optimized\deepseek_proxy.py','r',encoding='utf-8').read()

idx = content.find('def _handle_chat(self, data):')
print(f'_handle_chat at: {idx}')

# 找下一个顶层def
rest = content[idx:]
next_def = re.search(r'\n(?!    )(?:async )?def ', rest[1:])
if next_def:
    end_pos = idx + 1 + next_def.start()
    func_body = content[idx:end_pos]
    print(f'函数体: {len(func_body)} chars')
    
    # 所有 send_json / wfile.write
    writes = list(re.finditer(r'(self\.wfile\.write|self\._send_json|_send_json)', func_body))
    for w in writes[-3:]:
        line_no = func_body[:w.start()].count('\n') + 1
        snippet = func_body[w.start():w.start()+120]
        print(f'\n  L{line_no}: {snippet}')
else:
    print('找不到下一个函数定义')
