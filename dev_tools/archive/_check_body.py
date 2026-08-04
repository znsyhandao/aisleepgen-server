# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'D:\AISleepGen_Optimized\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('def _build_history_context')
body = content[idx:idx+5000]
count = body.count("summaries = profile.get('")
print(f'函数体内 summaries 赋值: {count} 处')

for i,l in enumerate(body.split('\n'), 1):
    if 'summaries' in l:
        real_line = content[:idx].count('\n') + i
        print(f'  L{real_line}: {l.strip()[:80]}')
