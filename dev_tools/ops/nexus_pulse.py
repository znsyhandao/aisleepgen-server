#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ops/nexus_pulse.py — Neural Nexus 脉冲注入入口（委托到 D:\shared_environment\nexus_pulse.py）"""
import sys, os
pulse = r'D:\shared_environment\nexus_pulse.py'
if not os.path.exists(pulse):
    print(f'[nexus] 错误: 找不到 {pulse}')
    sys.exit(1)
# 直接 exec 传递参数
with open(pulse, 'r', encoding='utf-8') as f:
    code = f.read()
exec(compile(code, pulse, 'exec'))
