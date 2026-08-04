# -*- coding: utf-8 -*-
"""修复_build_history_context中summaries UnboundLocalError"""
import sys, py_compile
sys.stdout.reconfigure(encoding='utf-8')

fp = r'D:\AISleepGen_Optimized\deepseek_proxy.py'

with open(fp, 'rb') as f:
    raw = f.read()

# 定位到 lines = [] 那行, 然后在其之后的空行和 "今天的情况" 之间插入
marker_before = b'    lines = []\r\n'
marker_after = b'\r\n    # \xe4\xbb\x8a\xe5\xa4\xa9\xe7\x9a\x84\xe6\x83\x85\xe5\x86\xb5'  # "今天的情况" utf-8

idx_before = raw.find(marker_before)
idx_after = raw.find(marker_after, idx_before)

print(f'lines = [] at {idx_before}')
print(f'今天的情况 at {idx_after}')

if idx_before >= 0 and idx_after >= 0:
    insert = b'\r\n    # \xe7\xa1\xae\xe4\xbf\x9d summaries \xe5\x9c\xa8\xe6\x95\xb4\xe4\xb8\xaa\xe4\xbd\x9c\xe7\x94\xa8\xe5\x9f\x9f\xe5\x8f\xaf\xe7\x94\xa8\r\n    summaries = profile.get(\'conversation_summaries\', [])\r\n'
    # 在idx_after之前插入
    new_raw = raw[:idx_after] + insert + raw[idx_after:]
    
    with open(fp, 'wb') as f:
        f.write(new_raw)
    
    print(f'插入完成: +{len(insert)} 字节')
else:
    print('未找到标记')

try:
    py_compile.compile(fp, doraise=True)
    print('编译通过')
except py_compile.PyCompileError as e:
    print(f'编译失败: {e}')
