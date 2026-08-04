# -*- coding: utf-8 -*-
"""
版本号一致性检查器
在 ClawHub 提交前/每次新版本发布前统一检查所有文件的版本号。

用法:
  python version_sync.py                   # 检查所有文件版本号
  python version_sync.py --fix             # 一键统一版本号
  python version_sync.py --bump minor      # 升级小版本号 (major/minor/patch)
  python version_sync.py --bump patch      # 升级补丁号
  
返回码: 0=一致  1=有不一致  2=出错
"""
import os, re, sys, json, hashlib

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(PROJECT_DIR) if not os.path.exists(os.path.join(PROJECT_DIR, 'skill.py')) and os.path.exists(os.path.join(os.path.dirname(PROJECT_DIR), 'skill.py')) else PROJECT_DIR

# 需要在哪儿查找版本号
SCAN_PATTERNS = {
    '.py': [
        (r"""__version__\s*=\s*['"]([^'"]+)['"]""", '__version__ ='),
        (r"""VERSION\s*=\s*['"]([^'"]+)['"]""", 'VERSION ='),
        (r"""version\s*=\s*['"]([^'"]+)['"]""", 'version ='),
    ],
    '.md': [
        (r"""Version:\s*(\S+)""", 'Version: '),
        (r"""version:\s*(\S+)""", 'version: '),
        (r"""v(\d+\.\d+\.\d+)""", 'v'),
    ],
    '.json': [
        (r"""['"]version['"]\s*:\s*['"]([^'"]+)['"]""", '"version": "'),
    ],
    '.js': [
        (r"""version\s*[:=]\s*['"]([^'"]+)['"]""", 'version = '),
    ],
}

# 忽略目录
IGNORE_DIRS = {'__pycache__', '.git', 'venv', 'node_modules', '.surgical_backups', '.topology_backup', 'memory', 'sleep_edf_validate'}
IGNORE_FILES = {'install_hooks.py', 'pre_op.py', 'preflight.py', 'pyrun.py', 'memwatch.py', 'deploy_check.py', 'version_sync.py'}

def banner(msg):
    print(f'\n{"="*55}')
    print(f'  {msg}')
    print(f'{"="*55}')

def scan_files():
    """扫描所有文件提取版本号"""
    results = []
    for root, dirs, files in os.walk(SKILL_DIR):
        # 跳过忽略目录
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        rel = os.path.relpath(root, SKILL_DIR)
        if rel == '.':
            rel = ''
        
        for fname in files:
            if fname in IGNORE_FILES:
                continue
            ext = os.path.splitext(fname)[1]
            if ext not in SCAN_PATTERNS:
                continue
            
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except:
                continue
            
            for pattern, label in SCAN_PATTERNS[ext]:
                for m in re.finditer(pattern, content):
                    line_num = content[:m.start()].count('\n') + 1
                    results.append({
                        'file': os.path.join(rel, fname) if rel else fname,
                        'version': m.group(1),
                        'line': line_num,
                        'label': label,
                    })
    
    return results

def parse_version(v_str):
    """解析版本号为可比较的元组"""
    m = re.match(r'(\d+)\.(\d+)\.(\d+)', v_str.strip('vV').replace('-', '.'))
    if not m:
        # 尝试语义化版本号
        m2 = re.match(r'(\d+)\.(\d+)', v_str.strip('vV'))
        if m2:
            return (int(m2.group(1)), int(m2.group(2)), 0)
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))

def get_dominant_version(versions_list):
    """找出出现频率最高的版本号作为基准"""
    from collections import Counter
    counts = Counter()
    for v in versions_list:
        parsed = parse_version(v)
        if parsed:
            counts[parsed] += 1
    if not counts:
        return None, False
    dominant, count = counts.most_common(1)[0]
    total = sum(counts.values())
    is_majority = count >= total * 0.5
    return dominant, is_majority

def check():
    """检查版本号一致性"""
    banner('版本号一致性检查')
    results = scan_files()
    if not results:
        check(False, '没有找到任何版本号')
        return False
    
    versions = [r['version'] for r in results]
    dominant_parsed, is_majority = get_dominant_version(versions)
    
    if dominant_parsed is None:
        check(False, '无法解析版本号')
        return False
    
    dominant_str = f'v{dominant_parsed[0]}.{dominant_parsed[1]}.{dominant_parsed[2]}'
    
    print(f'  找到 {len(results)} 处版本号声明')
    print(f'  基准版本: {dominant_str} (占 {sum(1 for v in versions if parse_version(v)==dominant_parsed)}/{len(versions)})')
    print()
    
    # 按文件分组显示
    by_file = {}
    for r in results:
        fn = r['file']
        if fn not in by_file:
            by_file[fn] = []
        by_file[fn].append(r)
    
    all_ok = True
    for fname, vers in sorted(by_file.items()):
        for v in vers:
            parsed = parse_version(v['version'])
            ok = parsed == dominant_parsed if dominant_parsed else False
            if not ok:
                all_ok = False
            icon = '[OK]' if ok else '[FAIL]'
            print(f'  {icon} {fname}:{v["line"]}  {v["version"]} {"(不一致!)" if not ok else ""}')
    
    if all_ok:
        print(f'\n  ✅ 所有版本号一致 ({dominant_str})')
        return True
    else:
        print(f'\n  ❌ 版本号不一致，基准: {dominant_str}')
        return False

def fix():
    """一键统一版本号"""
    results = scan_files()
    dominant_parsed, _ = get_dominant_version([r['version'] for r in results])
    if dominant_parsed is None:
        print('无法确定基准版本号')
        return False
    
    dominant_str = f'{dominant_parsed[0]}.{dominant_parsed[1]}.{dominant_parsed[2]}'
    
    banner(f'统一版本号 -> v{dominant_str}')
    
    changes = 0
    for r in results:
        parsed = parse_version(r['version'])
        if parsed == dominant_parsed:
            continue
        
        fpath = os.path.join(SKILL_DIR, r['file'])
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            line_idx = r['line'] - 1
            old_line = lines[line_idx]
            old_ver = r['version']
            new_ver = f'v{dominant_str}' if old_ver.startswith('v') else dominant_str
            if '-' in old_ver:
                suffix = '-' + old_ver.split('-', 1)[1]
                new_ver += suffix
            lines[line_idx] = old_line.replace(old_ver, new_ver, 1)
            
            with open(fpath, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            changes += 1
            print(f'  [FIX] {r["file"]}:{r["line"]}  {r["version"]} -> {new_ver}')
        except Exception as e:
            print(f'  [ERR] {r["file"]}: {e}')
    
    print(f'\n  已修复 {changes} 处版本号')
    return True

def bump(level='patch'):
    """升级版本号"""
    results = scan_files()
    dominant_parsed, _ = get_dominant_version([r['version'] for r in results])
    if dominant_parsed is None:
        print('无法确定基准版本号')
        return False
    
    major, minor, patch = dominant_parsed
    if level == 'major':
        new_ver = (major + 1, 0, 0)
    elif level == 'minor':
        new_ver = (major, minor + 1, 0)
    else:  # patch
        new_ver = (major, minor, patch + 1)
    
    dominant_str = f'{dominant_parsed[0]}.{dominant_parsed[1]}.{dominant_parsed[2]}'
    new_str = f'{new_ver[0]}.{new_ver[1]}.{new_ver[2]}'
    
    banner(f'升级版本号: v{dominant_str} -> v{new_str} ({level})')
    
    changes = 0
    for r in results:
        fpath = os.path.join(SKILL_DIR, r['file'])
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            line_idx = r['line'] - 1
            lines[line_idx] = lines[line_idx].replace(r['version'], new_str, 1)
            
            with open(fpath, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            changes += 1
            print(f'  [BUMP] {r["file"]}:{r["line"]}  {r["version"]} -> {new_str}')
        except Exception as e:
            print(f'  [ERR] {r["file"]}: {e}')
    
    print(f'\n  已升级 {changes} 处版本号 ({levels}={level})')
    return True

if __name__ == '__main__':
    if '--fix' in sys.argv:
        fix()
        check()
    elif '--bump' in sys.argv:
        idx = sys.argv.index('--bump')
        level = sys.argv[idx+1] if idx+1 < len(sys.argv) else 'patch'
        bump(level)
    else:
        ok = check()
        sys.exit(0 if ok else 1)
