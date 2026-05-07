# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'D:\AISleepGen_Optimized')

# Read the action trigger block from fixed file
with open('dp_router.py', 'rb') as f:
    c = f.read()

# Check the handle_wx_login is back
hwl = c.find(b'handle_wx_login')
print(f'handle_wx_login at: {hwl}')

# Check Chinese keywords in the action trigger block
i = c.find(b"_action_trigger = None")
block = c[i:i+3000].decode('utf-8')

# Check if the correct keywords are used
import re
chinese_kws = re.findall(r"'([^']*?[\\u4e00-\\u9fff][^']*?)'", block)
print(f'Keywords found: {chinese_kws[:15]}')

# Simulate
_action_trigger = None
_action_kw = ['做', '开始', '引导', '练习', '怎么', '教我', '带我做', '做一下',
              '扫描', '放松', '呼吸', '正念', '冥想', '肌肉', 'pmr',
              '带带我', '来一下', '来一个', '做做',
              '盒子', '盒式', '缩唇', '自律', '暗示', '沉重', '温暖',
              '安全岛', '安全', '云端', '漂浮', '声音浴', '颂钵', '大提琴',
              '担忧', '担心', '写下', '卸荷', '认知',
              '矛盾', '清醒', '努力', '睁眼',
              '刺激控制',
              '卫生', '检查', '清单', '环境', '习惯',
              '信念', '挑战', '想法', '灾难化', '重构']

message = '带我做个呼吸引导'
_is_action_req = any(kw in message for kw in _action_kw)

if _is_action_req:
    _action_trigger = '4-7-8'
    if '呼吸' in message or '正念' in message:
        _action_trigger = 'breathing'

print(f'\nInput: "{message}"')
print(f'_action_trigger: {_action_trigger}')

# Clean up temp files
import os
for f in os.listdir('.'):
    if f.startswith('_fix_') or f.startswith('_check_') or f.startswith('_verify_') or f.startswith('_deep_') or f.startswith('_health_') or f.startswith('_find_') or f.startswith('_test_e') or f.startswith('_api_debug'):
        os.remove(f)
        print(f'Cleaned: {f}')
