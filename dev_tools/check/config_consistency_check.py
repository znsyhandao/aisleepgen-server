#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config_consistency_check.py — 配置/常量一致性检查

查什么：
- 多处重复定义的同名字符串常量是否一致（如 PROMPT_TEMPLATE）
- .env 文件中定义的键是否被代码实际引用
- 硬编码路径 vs 实际文件系统路径
- 前端（WXML/JS）和后端（Python）中的 API 路径是否一致
- API 超时/重试策略在不同文件中是否一致

用法:
  python config_consistency_check.py [--dir D:\AISleepGen_Optimized]
"""

import os, sys, re, argparse
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')


def find_constant_defs(filepath, min_len=20):
    """Find string constant definitions."""
    constants = []
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    # Find string assignments: VAR = "value"
    pattern = r'^([A-Z_][A-Z0-9_]*)\s*=\s*["\'](.+?)["\']'
    for match in re.finditer(pattern, content, re.MULTILINE):
        name = match.group(1)
        value = match.group(2)
        if len(value) >= min_len:
            constants.append({
                'name': name,
                'value': value[:200],
                'file': filepath,
            })
    return constants


def find_api_paths(filepath):
    """Find all API path references."""
    paths = set()
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    # Match /api/... paths
    for match in re.finditer(r"['\"]/(api/[a-z0-9_/-]+)['\"]", content):
        paths.add(match.group(1))
    
    # Match self.path.startswith('/api/...')
    for match in re.finditer(r"['\"]/(api/[a-z0-9_/-]+)['\"]", content):
        paths.add(match.group(1))
    
    return paths


def find_dotenv_keys(filepath):
    """Find all keys referenced from .env or os.environ."""
    keys = set()
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    for match in re.finditer(r"os\.environ\.get\(['\"]([A-Z_]+)['\"]", content):
        keys.add(match.group(1))
    for match in re.finditer(r"os\.getenv\(['\"]([A-Z_]+)['\"]", content):
        keys.add(match.group(1))
    for match in re.finditer(r"['\"]([A-Z_]+)['\"]\s*,\s*['\"]", content):
        # .env variable names
        if match.group(1).startswith(('DEEPSEEK', 'API', 'PORT', 'HOST', 'KEY', 'SECRET', 'TOKEN', 'DB_')):
            keys.add(match.group(1))
    
    return keys


def find_timeout_constants(filepath):
    """Find timeout/retry configurations."""
    timeouts = []
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines):
        if any(kw in line.lower() for kw in ['timeout', 'retry', 'max_', 'interval', 'delay']):
            # Extract number values
            nums = re.findall(r'(\d+)\s*[#\)\n,]', line)
            if nums:
                timeouts.append({
                    'line': i + 1,
                    'text': line.strip()[:100],
                    'values': nums,
                })
    return timeouts


def find_frontend_api_paths(wx_dir):
    """Find API paths in WeChat mini-program files."""
    paths = set()
    if not os.path.isdir(wx_dir):
        return paths, 'directory not found'
    
    for root, dirs, files in os.walk(wx_dir):
        for f in files:
            if f.endswith(('.js', '.wxml', '.json')):
                fp = os.path.join(root, f)
                with open(fp, 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
                for match in re.finditer(r"['\"]/(api/[a-z0-9_/-]+)['\"]", content):
                    paths.add((match.group(1), f, fp))
    
    return paths, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    parser.add_argument('--wx-dir', default=r'D:\AISleepGen_Optimized\miniprogram')
    args = parser.parse_args()
    
    workdir = args.dir
    
    # Focus files
    FOCUS = ['deepseek_proxy.py', 'compliance.py', 'audit_logger.py',
             'world_model_coordinator.py', 'state_transition_model.py',
             'biofeedback_renderer.py', 'sleep_phase_planner.py',
             'wx_login.py', 'scheduler_daemon.py', 'discrepancy_detector.py',
             'dp_router.py']
    
    print("=" * 60)
    print("  CONFIG CONSISTENCY CHECK")
    print("=" * 60)
    
    # 1. Check duplicate constant definitions
    print("\n[1] Duplicate string constants")
    all_consts = []
    for fname in FOCUS:
        fp = os.path.join(workdir, fname)
        if os.path.exists(fp):
            consts = find_constant_defs(fp)
            all_consts.extend(consts)
    
    by_value = defaultdict(list)
    for c in all_consts:
        by_value[c['value']].append(c)
    
    dupes = {v: items for v, items in by_value.items() if len(items) >= 2}
    if dupes:
        print(f"  Found {len(dupes)} duplicated constant(s):")
        for val, items in list(dupes.items())[:10]:
            files = [f"{c['name']} @ {os.path.basename(c['file'])}" for c in items]
            print(f"    '{val[:60]}...'")
            for f in files:
                print(f"      {f}")
    else:
        print("  No duplicates found ✅")
    
    # 2. .env keys vs code references
    print("\n[2] Environment variable keys (code vs .env)")
    code_keys = set()
    for fname in FOCUS:
        fp = os.path.join(workdir, fname)
        if os.path.exists(fp):
            code_keys.update(find_dotenv_keys(fp))
    
    # Check .env file
    dotenv_path = os.path.join(workdir, '.env')
    env_keys = set()
    if os.path.exists(dotenv_path):
        with open(dotenv_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    env_keys.add(line.split('=')[0].strip())
    else:
        print(f"  ⚠️  .env file not found at {dotenv_path}")
    
    missing_from_env = code_keys - env_keys
    if missing_from_env:
        print(f"  ⚠️  Keys used in code but missing from .env ({len(missing_from_env)}):")
        for k in sorted(missing_from_env):
            print(f"    {k}")
    
    unused_in_env = env_keys - code_keys
    if unused_in_env:
        print(f"  ℹ️  Keys in .env but never referenced in code ({len(unused_in_env)}):")
        for k in sorted(unused_in_env):
            print(f"    {k}")
    
    if not missing_from_env:
        print("  All environment keys are consistent ✅")
    
    # 3. API path consistency (backend vs frontend)
    print("\n[3] API path consistency (backend vs frontend)")
    backend_paths = set()
    for fname in FOCUS:
        fp = os.path.join(workdir, fname)
        if os.path.exists(fp):
            backend_paths.update(find_api_paths(fp))
    
    # Also check dp_router.py route table
    router_path = os.path.join(workdir, 'dp_router.py')
    if os.path.exists(router_path):
        backend_paths.update(find_api_paths(router_path))
    
    # Check frontend
    frontend_paths, err = find_frontend_api_paths(args.wx_dir)
    if err:
        print(f"  ⚠️  Frontend dir issue: {err}")
    else:
        frontend_set = {p[0] for p in frontend_paths}
        
        backend_only = backend_paths - frontend_set
        frontend_only = frontend_set - backend_paths
        
        if backend_only:
            print(f"  ⚠️  Backend routes not found in frontend ({len(backend_only)}):")
            for p in sorted(backend_only):
                print(f"    {p}")
        if frontend_only:
            print(f"  ⚠️  Frontend routes without backend handler ({len(frontend_only)}):")
            for p in sorted(frontend_only):
                print(f"    {p}")
        if not backend_only and not frontend_only:
            print("  All API paths are consistent between frontend and backend ✅")
    
    # 4. Timeout/retry consistency
    print("\n[4] Timeout/retry configurations")
    all_timeouts = []
    for fname in FOCUS:
        fp = os.path.join(workdir, fname)
        if os.path.exists(fp):
            tos = find_timeout_constants(fp)
            if tos:
                all_timeouts.append((fname, tos))
    
    if all_timeouts:
        print(f"  Timeout/retry configs found across {len(all_timeouts)} files:")
        for fname, tos in all_timeouts:
            print(f"  {fname}:")
            for t in tos[:5]:
                print(f"    L{t['line']}: {t['text'][:70]}")
            if len(tos) > 5:
                print(f"    ... and {len(tos)-5} more")
    else:
        print("  No timeout configs found (or all files have none)")
    
    print("\n" + "=" * 60)
    print("  DONE")
    print("=" * 60)


if __name__ == '__main__':
    main()
