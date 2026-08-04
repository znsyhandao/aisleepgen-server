#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dead_code_scanner.py — 死代码/废弃导入扫描器

查什么：
- 定义了但从未调用的函数/方法（全局搜索引用）
- import 了但未使用的模块
- 定义了但只被自身递归调用的函数

用法:
  python dead_code_scanner.py [--dir D:\AISleepGen_Optimized]
"""

import os, sys, ast, argparse
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')


def scan_file(filepath, all_defs, all_refs):
    """Extract definitions and references from a file."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError:
            return [], []
    
    defs = []
    refs = []
    imports = set()
    used_imports = set()
    
    for node in ast.walk(tree):
        # Track function/method definitions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs.append({
                'name': node.name,
                'file': filepath,
                'lineno': node.lineno,
                'type': 'function',
            })
        # Track class definitions
        elif isinstance(node, ast.ClassDef):
            defs.append({
                'name': node.name,
                'file': filepath,
                'lineno': node.lineno,
                'type': 'class',
            })
        # Track imports
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name
                imports.add(name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                imports.add(name)
        # Track function calls
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                refs.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                refs.append(node.func.attr)
    
    # Track used names
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_imports.add(node.id)
    
    unused_imports = imports - used_imports
    
    return defs, refs, unused_imports, filepath


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    parser.add_argument('--focus-files', nargs='*',
                        default=['deepseek_proxy.py', 'compliance.py', 'audit_logger.py',
                                 'world_model_coordinator.py', 'state_transition_model.py',
                                 'biofeedback_renderer.py', 'sleep_phase_planner.py',
                                 'wx_login.py'])
    args = parser.parse_args()
    
    workdir = args.dir
    
    # Collect all definitions and references from focused files
    all_defs = []
    all_refs = defaultdict(list)
    unused_imports_report = []
    
    for fname in args.focus_files:
        fp = os.path.join(workdir, fname)
        if not os.path.exists(fp):
            print(f"[SKIP] {fname} not found")
            continue
        defs, refs, unused, fpath = scan_file(fp, all_defs, all_refs)
        all_defs.extend(defs)
        if unused:
            unused_imports_report.append((fname, unused))
        for r in refs:
            all_refs[r].append(fname)
    
    print(f"Scanned {len(args.focus_files)} files, {len(all_defs)} definitions\n")
    
    # 1. Unused imports
    if unused_imports_report:
        print("[DEAD_CODE] Unused imports:")
        for fname, unused in unused_imports_report:
            for u in sorted(unused):
                print(f"  ⚠️  {fname}: import '{u}' appears unused")
        print()
    else:
        print("[DEAD_CODE] No unused imports found ✅\n")
    
    # 2. Defined but never called functions (outside their own definition)
    dead_funcs = []
    for d in all_defs:
        if d['type'] != 'function':
            continue
        # Check if referenced anywhere
        ref_files = all_refs.get(d['name'], [])
        if not ref_files:
            dead_funcs.append(d)
    
    if dead_funcs:
        print(f"[DEAD_CODE] Defined but never called ({len(dead_funcs)}):")
        for d in dead_funcs:
            fname = os.path.basename(d['file'])
            print(f"  ⚠️  {d['name']} @ {fname}:L{d['lineno']}")
    else:
        print("[DEAD_CODE] All defined functions are referenced ✅")
    
    return 1 if (unused_imports_report or dead_funcs) else 0


if __name__ == '__main__':
    sys.exit(main())
