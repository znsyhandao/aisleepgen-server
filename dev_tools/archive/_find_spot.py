# -*- coding: utf-8 -*-
with open(r'D:\AISleepGen_Optimized\deepseek_proxy.py', 'rb') as f:
    raw = f.read()
idx = raw.find(b"result['show_brief']")
print(f'result show_brief at: {idx}')
if idx >= 0:
    bol = raw.rfind(b'\n', 0, idx)
    eol = raw.find(b'\n', idx)
    print(f'Lines around bol={bol} eol={eol}')
    print(raw[bol:eol+200].decode('utf-8', errors='replace'))
