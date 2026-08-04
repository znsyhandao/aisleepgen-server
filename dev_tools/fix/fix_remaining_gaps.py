#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_remaining_gaps.py — 一次修完3个剩余盲区"""

import sys, os, shutil, datetime, py_compile
sys.stdout.reconfigure(encoding='utf-8')

FILE = r'D:\AISleepGen_Optimized\deepseek_proxy.py'
BACKUP_DIR = r'D:\AISleepGen_Optimized\.surgical_backups'

print('[FixGaps] Target:', FILE)
os.makedirs(BACKUP_DIR, exist_ok=True)
ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
bak = os.path.join(BACKUP_DIR, 'deepseek_proxy.py_' + ts + '.bak')
shutil.copy2(FILE, bak)
print('[FixGaps] Backup:', bak)

with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

changes = []

# ===== Fix S1: 问卷path的history append后加limit =====
old_s1 = '''                for entry in updates['history']:
                    profile['history'].append(entry)
            if 'last_survey' in updates:'''

new_s1 = '''                for entry in updates['history']:
                    profile['history'].append(entry)
                if len(profile['history']) > 30:
                    profile['history'] = profile['history'][-30:]
            if 'last_survey' in updates:'''

assert old_s1 in content, 'S1 marker not found'
content = content.replace(old_s1, new_s1, 1)
changes.append('S1: survey-path history limit')

# ===== Fix H6: correction路径加trace =====
old_h6 = '''    # 更新最新画像--如果是纠正，数据来源标注为"用户修正"
    _old_latest = profile.get('latest', {})'''

new_h6 = '''    # [H6] correction trace
    _write_trace('[h6] correction=' + str(is_correction) + ' type=' + session_entry.get('type','?') + ' uid=' + openid[:8])
    
    # 更新最新画像--如果是纠正，数据来源标注为"用户修正"
    _old_latest = profile.get('latest', {})'''

assert old_h6 in content, 'H6 marker not found'
content = content.replace(old_h6, new_h6, 1)
changes.append('H6: correction path trace')

# ===== Fix F2: body字段入参校验 =====
old_f2 = '''        # 获取用户标识（微信openid）
        openid = self._get_openid(data)

        # [Trace] 数据流追踪'''

new_f2 = '''        # [F2] body字段迁移检测
        if data:
            _f2_keys = list(data.keys())
            if 'text' in _f2_keys and 'message' not in _f2_keys:
                _write_trace('[f2] body-field-migration: text found but message missing keys=' + str(_f2_keys))
            if 'messages' in _f2_keys and 'history' not in _f2_keys:
                _write_trace('[f2] body-field-migration: messages found but history missing keys=' + str(_f2_keys))
        
        # 获取用户标识（微信openid）
        openid = self._get_openid(data)

        # [Trace] 数据流追踪'''

assert old_f2 in content, 'F2 marker not found'
content = content.replace(old_f2, new_f2, 1)
changes.append('F2: body field migration guard')

# 写回
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

# 编译验证
try:
    py_compile.compile(FILE, doraise=True)
    print('[FixGaps] Compile OK')
except py_compile.PyCompileError as e:
    print('[FixGaps] Compile FAIL:', str(e))
    shutil.copy2(bak, FILE)
    sys.exit(1)

print('[FixGaps] All done. Changes:')
for c in changes:
    print('  +', c)
print('[FixGaps] Rollback: copy ' + bak + ' ' + FILE)
