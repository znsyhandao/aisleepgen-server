# -*- coding: utf-8 -*-
"""扫描deepseek_proxy.py中所有错误返回"""
import sys, re
sys.stdout.reconfigure(encoding='utf-8')

with open(r'D:\AISleepGen_Optimized\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找所有 _send_json 调用中含 error 的
lines = content.split('\n')
for i, line in enumerate(lines, 1):
    s = line.strip()
    if '_send_json' in s and 'error' in s.lower():
        # 找前一行看是不是在 except 块里
        prev = lines[i-2].strip() if i >= 2 else ''
        context = 'EXCEPT' if 'except' in prev else 'OTHER'
        print(f'L{i} [{context}]: {s[:180]}')

print(f'\n--- 总行数: {len(lines)} ---')
