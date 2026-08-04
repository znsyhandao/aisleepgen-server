#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_data_flow.py — 数据流一致性探测器 v1.0

扫描 user_profile.json 中的所有用户，检查：
1. latest 结构是否统一（字段路径一致）
2. sleep_data 子对象是否存在（关键读路径）
3. history 中同一用户的 latest 覆盖次数（频繁覆盖 = 竞态风险）
4. 字段值类型一致性（如 bedtime 应是字符串而非 null）
5. 报告不一致项

用法:
  python dev_tools/check/check_data_flow.py
  python aisleepgen_tool.py check data-flow
"""

import json, os, sys, datetime
sys.stdout.reconfigure(encoding='utf-8')

ISSUES = []
STATS = {'total_users': 0, 'with_sleep_data': 0, 'without_sleep_data': 0,
         'mixed_latest_structure': 0, 'field_type_issues': 0}

def report(severity, category, msg):
    ISSUES.append({'severity': severity, 'category': category, 'msg': msg})
    print(f'  [{severity}] {category}: {msg}')

PROFILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'user_profile.json')

print(f'{"="*60}')
print(f'  数据流一致性探测器 v1.0')
print(f'  目标: {PROFILE_PATH}')
print(f'  时间: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print(f'{"="*60}')

if not os.path.exists(PROFILE_PATH):
    print('[FATAL] user_profile.json not found')
    sys.exit(1)

with open(PROFILE_PATH, 'r', encoding='utf-8') as f:
    all_p = json.load(f)

print(f'\n扫描 {len(all_p)} 个用户...\n')

# 检测 latest 结构是否统一
latest_schemas = {}

for uid, p in all_p.items():
    STATS['total_users'] += 1
    latest = p.get('latest', {})
    
    # 1. sleep_data 存在性
    sd = latest.get('sleep_data', None)
    if sd and isinstance(sd, dict) and len(sd) > 0:
        STATS['with_sleep_data'] += 1
    else:
        STATS['without_sleep_data'] += 1
        # 检查 latest 顶层是否有替代字段
        has_direct = bool(latest.get('bedtime') or latest.get('wake_time'))
        status = '有顶层字段(可回退)' if has_direct else '完全无睡眠数据'
        report('LOW', 'sleep_data缺失', f'{uid[:20]}: {status}')
    
    # 2. 字段类型一致性
    expected_str_fields = ['bedtime', 'wake_time']
    expected_int_fields = ['sleep_latency', 'awake_times', 'total_duration']
    
    check_source = sd if sd and isinstance(sd, dict) else latest
    for field in expected_str_fields:
        val = check_source.get(field)
        if val is not None and val != '' and not isinstance(val, str):
            report('MEDIUM', '类型异常', f'{uid[:20]}: {field}={val!r} (期望str, 实际{type(val).__name__})')
            STATS['field_type_issues'] += 1
    for field in expected_int_fields:
        val = check_source.get(field)
        if val is not None and val != '' and not isinstance(val, (int, float)):
            if isinstance(val, str) and val.replace('.','',1).isdigit():
                continue  # 数字字符串可接受
            report('MEDIUM', '类型异常', f'{uid[:20]}: {field}={val!r} (期望int, 实际{type(val).__name__})')
            STATS['field_type_issues'] += 1
    
    # 3. latest 结构指纹
    schema_keys = tuple(sorted(latest.keys()))
    if schema_keys not in latest_schemas:
        latest_schemas[schema_keys] = []
    latest_schemas[schema_keys].append(uid)
    
    # 4. history 中 latest 覆盖频率(如果有 history)
    history = p.get('history', [])
    if len(history) > 10:
        hist_dates = [h.get('date','')[:10] for h in history if h.get('date')]
        if len(hist_dates) > 1:
            report('INFO', '高频用户', f'{uid[:20]}: {len(hist_dates)}次记录, 日期范围{min(hist_dates)}~{max(hist_dates)}')

print(f'\n{"="*60}')
print(f'  结构多样性检查')
print(f'{"="*60}')

if len(latest_schemas) > 1:
    STATS['mixed_latest_structure'] = len(latest_schemas)
    report('HIGH', 'latest结构不统一', f'共 {len(latest_schemas)} 种不同key组合')
    for keys, users in sorted(latest_schemas.items(), key=lambda x: -len(x[1])):
        print(f'   [{len(users)}个用户] keys={list(keys)}')
        if len(users) <= 3:
            for u in users:
                print(f'      {u}')
else:
    print('  [OK] 所有用户 latest 结构一致')

print(f'\n{"="*60}')
print(f'  汇总报告')
print(f'{"="*60}')
print(f'  总用户数: {STATS["total_users"]}')
print(f'  有 sleep_data: {STATS["with_sleep_data"]}')
print(f'  缺 sleep_data: {STATS["without_sleep_data"]}')
print(f'  latest结构种数: {STATS["mixed_latest_structure"]}')
print(f'  字段类型异常: {STATS["field_type_issues"]}')
print(f'  总问题数: {len(ISSUES)}')
high = sum(1 for i in ISSUES if i['severity'] == 'HIGH')
med = sum(1 for i in ISSUES if i['severity'] == 'MEDIUM')
low = sum(1 for i in ISSUES if i['severity'] == 'LOW')
print(f'  HIGH={high} MEDIUM={med} LOW={low} INFO={len(ISSUES)-high-med-low}')
print(f'{"="*60}')
