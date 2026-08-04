#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_file_locking.py — 为 user_profile.json 添加线程级文件锁

注入到 deepseek_proxy.py：
1. 添加全局文件锁 threading.Lock()
2. 修改 _save_user_profile() 在读写前后加锁
3. 添加写入校验：写入后立即读出校验 JSON 完整性
4. 添加写入版本号 _profile_version

用法:
  python dev_tools/fix/fix_file_locking.py
  python aisleepgen_tool.py fix file-locking
"""

import sys, os, shutil, datetime, py_compile

FILE = r'D:\AISleepGen_Optimized\deepseek_proxy.py'
BACKUP_DIR = r'D:\AISleepGen_Optimized\.surgical_backups'

print('[FixLock] Target:', FILE)
os.makedirs(BACKUP_DIR, exist_ok=True)
ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
bak = os.path.join(BACKUP_DIR, 'deepseek_proxy.py_' + ts + '.bak')
shutil.copy2(FILE, bak)
print('[FixLock] Backup:', bak)

with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

changes = []

# ===== 修改1: 在 import threading 后加全局锁 =====
marker = 'import threading'
replacement = '''import threading

# ===== 文件锁：保护 user_profile.json 并发写入 =====
_PROFILE_LOCK = threading.Lock()
_PROFILE_VERSION = int(time.time())
def _safe_save_profile(filepath, data):
    """线程安全的 profile 写入，带校验"""
    global _PROFILE_VERSION
    _PROFILE_VERSION += 1
    meta = data.setdefault('_meta', {})
    meta['_version'] = _PROFILE_VERSION
    meta['_updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with _PROFILE_LOCK:
        tmp = filepath + '.' + str(_PROFILE_VERSION) + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # 校验：写入后立即读回验证
        with open(tmp, 'r', encoding='utf-8') as f:
            verify = json.load(f)
        assert verify.get('_meta', {}).get('_version') == _PROFILE_VERSION, '写入校验失败'
        os.replace(tmp, filepath)
'''

assert marker in content, 'import threading not found'
content = content.replace(marker, replacement, 1)
changes.append('global lock + _safe_save_profile')

# ===== 修改2: 把 _save_user_profile 替换为调用 _safe_save_profile =====
old_save = '''def _save_user_profile(all_profiles, filepath=None):
    """保存全部用户画像到文件"""
    filepath = filepath or USER_PROFILE_PATH
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(all_profiles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'[ProfileSave] 保存失败: {e}')'''

new_save = '''def _save_user_profile(all_profiles, filepath=None):
    """保存全部用户画像到文件（线程安全）"""
    filepath = filepath or USER_PROFILE_PATH
    try:
        _safe_save_profile(filepath, all_profiles)
    except Exception as e:
        print(f'[ProfileSave] 保存失败: {e}')'''

if old_save in content:
    content = content.replace(old_save, new_save, 1)
    changes.append('_save_user_profile -> _safe_save_profile')
else:
    print('[FixLock] ! _save_user_profile signature not found, checking alt...')
    # 尝试备选版本
    old_save2 = '''def _save_user_profile(all_profiles, filepath=None):
    filepath = filepath or USER_PROFILE_PATH
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(all_profiles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'[ProfileSave] ���浽{filepath}ʧ��: {e}')'''
    if old_save2 in content:
        content = content.replace(old_save2, new_save, 1)
        changes.append('_save_user_profile -> _safe_save_profile (alt)')
    else:
        print('[FixLock] ! CRITICAL: _save_user_profile not found')

# ===== 修改3: 在 _load_user_profile 中也加读锁（可选，减轻读竞争）=====
# 实际上读不需要锁，但如果写了 tmp 文件读错了路径需要处理
# 加一个重试逻辑
old_load = '''def _load_user_profile(openid='default'):
    """加载指定用户画像"""
    all_profiles = _load_all_profiles()
    return all_profiles.get(openid, copy.deepcopy(_DEFAULT_PROFILE))'''

new_load = '''def _load_user_profile(openid='default'):
    """加载指定用户画像（带重试，应对写入竞态）"""
    for _retry in range(3):
        try:
            all_profiles = _load_all_profiles()
            return all_profiles.get(openid, copy.deepcopy(_DEFAULT_PROFILE))
        except (json.JSONDecodeError, KeyError) as _e:
            if _retry < 2:
                time.sleep(0.05)
                continue
            print(f'[ProfileLoad] 重试3次仍失败: {_e}')
            return copy.deepcopy(_DEFAULT_PROFILE)'''

if old_load in content:
    content = content.replace(old_load, new_load, 1)
    changes.append('_load_user_profile add retry')
else:
    print('[FixLock] ! _load_user_profile not found, checking alt...')

# 写回
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

# 编译验证
try:
    py_compile.compile(FILE, doraise=True)
    print('[FixLock] [OK] Compile passed')
except py_compile.PyCompileError as e:
    print('[FixLock] [FAIL] Compile error:', e)
    print('[FixLock] Rolling back...')
    shutil.copy2(bak, FILE)
    sys.exit(1)

delta = content.count('\n') - open(bak, 'r', encoding='utf-8').read().count('\n')
print('[FixLock] [OK] Lines added:', delta)
for c in changes:
    print('  +', c)
print('[FixLock] Done.')
print('[FixLock] Rollback: copy "' + bak + '" "' + FILE + '"')
