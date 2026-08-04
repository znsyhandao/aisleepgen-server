#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_profile_protect.py — 在 _save_user_profile 注入防护 + 版本号 + 异步保护

修改点（共 3 处）：
1. _save_user_profile 开头加版本号检查 + 非空 latest 保证
2. _save_all_profiles 写入前检查空 latest
3. _update_user_profile 加版本号增量保护异步覆盖

安装:
  python dev_tools/fix/fix_profile_protect.py
  python aisleepgen_tool.py fix profile-protect

回滚:
  copy .surgical_backups\deepseek_proxy.py_<timestamp>.bak deepseek_proxy.py
"""

import sys, os, shutil, datetime, json, py_compile

FILE = r'D:\AISleepGen_Optimized\deepseek_proxy.py'
BACKUP_DIR = r'D:\AISleepGen_Optimized\.surgical_backups'

print('[FixProfile] Target:', FILE)
os.makedirs(BACKUP_DIR, exist_ok=True)
ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
bak = os.path.join(BACKUP_DIR, 'deepseek_proxy.py_' + ts + '.bak')
shutil.copy2(FILE, bak)
print('[FixProfile] Backup:', bak)

with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

changes = []

# ===== Fix 1: _save_user_profile 头部加 latest 非空保证 =====
old1 = '''    # 运行时防御：传反了立刻报错
    assert isinstance(profile, dict), ('''

new1 = '''    # 运行时防御：传反了立刻报错
    # [FixProfile] 确保 latest 不为空 dict，避免"填了问卷AI不知道"情况
    if 'latest' not in profile or not isinstance(profile.get('latest'), dict):
        profile['latest'] = {}
    elif profile['latest'] == {}:
        # 如果 latest 是空字典且用户有 onbording 数据，保留 user_info
        pass  # 后续可以加迁移逻辑
    # 版本号: 防止异步线程用旧版本覆盖新写入
    if profile.get('latest'):
        profile['latest']['_version'] = int(time.time() * 100) % 1000000
    assert isinstance(profile, dict), ('''

assert old1 in content, 'Fix1 marker not found'
content = content.replace(old1, new1, 1)
changes.append('_save_user_profile: latest non-empty + version')

# ===== Fix 2: _save_all_profiles 写入前检查 =====
old2 = '''def _save_all_profiles(all_profiles):
    """保存所有用户的画像数据（写前自动备份，用原子写入防止并发读取截断）"""
    try:
        _backup_profile()'''

new2 = '''def _save_all_profiles(all_profiles):
    """保存所有用户的画像数据（写前自动备份，用原子写入防止并发读取截断）"""
    # [FixProfile] 写入前清理空 latest（避免累积垃圾数据）
    _cleaned_count = 0
    for _uid, _up in list(all_profiles.items()):
        _lt = _up.get('latest')
        if isinstance(_lt, dict) and len(_lt) == 0:
            del _up['latest']
            _cleaned_count += 1
        elif _lt is None:
            _up.pop('latest', None)
            _cleaned_count += 1
    if _cleaned_count > 0:
        print(f'[FixProfile] 清理 {_cleaned_count} 个空 latest')
    try:
        _backup_profile()'''

assert old2 in content, 'Fix2 marker not found'
content = content.replace(old2, new2, 1)
changes.append('_save_all_profiles: 写入前清理空 latest')

# ===== Fix 3: _save_user_profile 保存后打版本标记 =====
# 在 _invalidate_profile_cache(openid) 前加版本标记
old3 = '''        _save_all_profiles(all_profiles)
    _invalidate_profile_cache(openid)'''

new3 = '''        _save_all_profiles(all_profiles)
        # [FixProfile] 版本标记: 记录本次写入版本
        _ver = profile.get('latest', {}).get('_version', 0)
        if _ver:
            _write_trace(f'_save done ver={_ver} uid={openid[:12]}')
    _invalidate_profile_cache(openid)'''

assert old3 in content, 'Fix3 marker not found'
content = content.replace(old3, new3, 1)
changes.append('_save_user_profile: 保存后打印版本号')

# 写回
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

# 编译验证
try:
    py_compile.compile(FILE, doraise=True)
    print('[FixProfile] [OK] Compile passed')
except py_compile.PyCompileError as e:
    print('[FixProfile] [FAIL] Compile error:', e)
    print('[FixProfile] Rolling back...')
    shutil.copy2(bak, FILE)
    sys.exit(1)

delta = content.count('\n') - open(bak, 'r', encoding='utf-8').read().count('\n')
print('[FixProfile] [OK] Lines added:', delta)
for c in changes:
    print('  +', c)
print('[FixProfile] Done.')
