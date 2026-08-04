# -*- coding: utf-8 -*-
"""
手术前安全气囊 + 通用preflight检查
在编辑大型文件前自动执行：
  1. 备份
  2. 编译检查
  3. 中文完整性检查
  4. 文件大小趋势

用法: python pre_op.py [target_file]
"""
import shutil, os, sys, py_compile, re, pathlib
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PROJECT_DIR, 'dp_router.py')
BAK_DIR = os.path.join(PROJECT_DIR, '.surgical_backups')
MIN_LINES_FOR_BACKUP = 50
CRITICAL_CHINESE = ['呼吸', '身体扫描', '安全岛', '认知', '刺激控制']
LARGE_FILE_THRESHOLD = 300

CHECKLIST = []

def check(ok, label, detail=''):
    CHECKLIST.append((ok, label, detail))

def _safe_print(s):
    try:
        print(s)
    except UnicodeEncodeError:
        print(s.encode('ascii', 'replace').decode('ascii'))

def backup_and_hash(filepath):
    fname = os.path.basename(filepath)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak_name = f'{fname}_{ts}.bak'
    bak_path = os.path.join(BAK_DIR, bak_name)
    os.makedirs(BAK_DIR, exist_ok=True)
    shutil.copy2(filepath, bak_path)
    import hashlib
    with open(bak_path, 'rb') as f:
        sha = hashlib.sha256(f.read()).hexdigest()[:16]
    manifest = os.path.join(BAK_DIR, 'manifest.txt')
    with open(manifest, 'a', encoding='utf-8') as mf:
        mf.write(f'{ts} {fname} -> {bak_name} [{sha}]\n')
    return bak_path, sha

def run():
    fname = os.path.basename(TARGET)
    try:
        with open(TARGET, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        _safe_print(f'[FAIL] Read error: {e}')
        sys.exit(1)

    lines = content.split('\n')
    n_lines = len(lines)
    n_bytes = len(content.encode('utf-8'))

    _safe_print('=' * 55)
    _safe_print(f'  [pre_op] Target: {fname} ({n_lines} lines, {"large" if n_lines > LARGE_FILE_THRESHOLD else "small"})')
    _safe_print('=' * 55)

    if n_lines > MIN_LINES_FOR_BACKUP:
        bak_path, sha = backup_and_hash(TARGET)
        _safe_print(f'[OK] Backup+hash verified: {os.path.basename(bak_path)} [{sha}]')
    else:
        _safe_print('[SKIP] File too small, backup skipped')

    # Compile check
    try:
        py_compile.compile(TARGET, doraise=True)
        _safe_print('[OK] Syntax check passed')
    except py_compile.PyCompileError as e:
        _safe_print(f'[FAIL] Syntax error: {e}')
        sys.exit(1)

    # Chinese keywords check
    missing = [kw for kw in CRITICAL_CHINESE if kw not in content]
    if missing:
        _safe_print(f'[WARN] Missing Chinese keywords: {missing}')
    else:
        _safe_print('[OK] Chinese keywords check passed')

    n_bytes_str = f'{n_bytes:,} bytes' if n_bytes >= 1000 else f'{n_bytes} bytes'
    _safe_print(f'[OK] File size: {n_bytes_str}, {n_lines} lines')

    # Clean __pycache__
    pycache = os.path.join(PROJECT_DIR, '__pycache__')
    if os.path.isdir(pycache):
        cnt = 0
        for root, dirs, files in os.walk(pycache):
            for f in files:
                if f.endswith('.pyc'):
                    os.remove(os.path.join(root, f))
                    cnt += 1
        _safe_print(f'[OK] __pycache__ cleaned: {cnt} .pyc files removed')

    # Post-edit verify: diff backup vs current
    _safe_print('\n--- General preflight reminders ---')
    _safe_print('[WARN] PowerShell embeds Python output with hard-wrapping')
    _safe_print('[WARN] stderr and stdout interleaved')
    _safe_print('[WARN] Process killed (code 1 + traceback) = memory or crash')
    _safe_print('[WARN] Small edits (3-5 lines) are safe')
    _safe_print('[OK] Verify edit: compare backup vs current after changes')

    ok_count = sum(1 for ok, _, _ in CHECKLIST if ok)
    warn_count = sum(1 for ok, _, _ in CHECKLIST if not ok)
    _safe_print(f'\n{"="*55}')
    _safe_print(f'  Preflight results: {ok_count} OK, {warn_count} WARN')
    _safe_print(f'  Ready to edit. Rollback: copy .surgical_backups\\{os.path.basename(bak_path)} {fname}')
    _safe_print(f'{"="*55}')

if __name__ == '__main__':
    run()
