# -*- coding: utf-8 -*-
"""验证后端编译"""
import py_compile

files = [
    r'D:\AISleepGen_Optimized\deepseek_proxy.py',
    r'D:\AISleepGen_Optimized\himiko_heart.py',
    r'D:\super_frontier_radar\heartbeat_orchestrator.py',
]

for fp in files:
    try:
        py_compile.compile(fp, doraise=True)
        print(f'  PASS: {fp.split(chr(92))[-1]}')
    except py_compile.PyCompileError as e:
        print(f'  FAIL: {fp.split(chr(92))[-1]}: {e}')
