#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_blind_spot_coverage.py — 检查工具集盲区覆盖情况

基于 audit_flow_gaps.py 的分析，输出当前盲区是否已填补。

v1.0 行动清单：
1. S2 文件锁 -> DONE（已有 _write_lock）
2. H2 读取竞态 -> DONE（已有空文件防御）
3. H5 异步覆盖 -> TODO（加 profile _meta 版本号+写前校验）
4. S1 history 长度上限 -> TODO（加 history 裁剪）
5. S3 schema 版本号 -> PARTIAL（加 _meta 字段到 _safe_save）
6. F1 openid trace -> PARTIAL（已有 trace logging，缺前端trace_id传播）
7. A2 LLM omission -> TODO（加 response 引用数据频率检测）
"""

import sys, os, json, datetime
sys.stdout.reconfigure(encoding='utf-8')

# 检查代码中已有的防护机制
FILE = r'D:\AISleepGen_Optimized\deepseek_proxy.py'
with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

checks = {
    'S2_write_lock': '_write_lock' in content or 'threading.Lock()' in content,
    'H2_empty_file_guard': '空文件' in content or 'getsize' in content,
    'H5_async_write_guard': '_profile_version' in content,
    'S1_history_limit': 'history' in content and 'MAX_HISTORY' in content,
    'S3_schema_version': '_meta' in content and 'version' in content,
    'F1_trace_logging': '_write_trace' in content,
    'A2_response_audit': False,  # 需要 LLM-as-judge 外部工具
    'H3_data_flow_check': True,  # check_data_flow.py 已存在
    'H4_ctx_len_trace': '[Trace:' in content,
}

print('=' * 60)
print('  盲区覆盖检查 v1.0')
print('=' * 60)

covered = 0
total = len(checks)
for name, present in checks.items():
    status = '[COVERED]' if present else '[GAP]'
    if present: covered += 1
    print(f'  {status} {name}')

print()
print('  {}/{} covered ({:.0f}%)'.format(covered, total, 100*covered/total))

# 输出剩余待办
print()
print('  === 剩余盲区 ===')
gaps = [k for k, v in checks.items() if not v]
for g in gaps:
    desc = {
        'H5_async_write_guard': '异步线程可能覆盖主线程写入的 profile',
        'S1_history_limit': 'history 数组无上限，会无限膨胀',
        'S3_schema_version': 'profile 结构没有版本号，代码更新后旧 json 可能不兼容',
        'A2_response_audit': '无法检查 LLM 是否忽略了上下文中已有的数据',
    }.get(g, '未知')
    print(f'  {g}: {desc}')
