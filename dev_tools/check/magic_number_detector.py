#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
magic_number_detector.py — 硬编码 Magic Number 检测器

查什么：
- 代码中裸数字常量（if awake_times >= 3、if latency > 30 等）
- 排除了 0/1/-1、字典/列表索引、常见数学常量
- 报告位置和上下文供人工判断

用法:
  python magic_number_detector.py [--dir D:\AISleepGen_Optimized]
"""

import os, sys, ast, argparse
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

# Numeric constants that are generally OK
SAFE_NUMBERS = {0, 1, -1, 0.0, 1.0, -1.0, 0.5, 100.0, 100, 60, 24, 7, 365, 
                3.14159, 3.14, 2.718, 1.414, 0.618, 0.001, 0.01, 0.1, 10, 1000}


def is_safe_number(n):
    """Check if a number is a common safe constant."""
    if n in SAFE_NUMBERS:
        return True
    # Common safe ranges: 2-5 (loop indices), 8 (bits), 16 (hex), 32/64/128/256 (bits/sizes)
    if n in {2, 3, 4, 5, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192}:
        return True
    return False


def scan_file_for_magic_numbers(filepath):
    """Scan a single file for magic numbers in comparisons."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content, filename=filepath)
    except SyntaxError:
        return []
    
    lines = content.split('\n')
    findings = []
    
    for node in ast.walk(tree):
        # Find comparisons: if x >= 3, while x < 30, etc.
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                if i < len(node.comparators):
                    comparator = node.comparators[i]
                    if isinstance(comparator, ast.Constant) and isinstance(comparator.value, (int, float)):
                        n = comparator.value
                        if not is_safe_number(n):
                            ctx = lines[node.lineno-1].strip() if node.lineno <= len(lines) else ''
                            findings.append({
                                'file': filepath,
                                'lineno': node.lineno,
                                'number': n,
                                'context': ctx[:120],
                            })
        
        # Find function calls with numeric constants
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, (int, float)):
                    n = kw.value.value
                    if not is_safe_number(n) and abs(n) > 5:
                        ctx = lines[node.lineno-1].strip() if node.lineno <= len(lines) else ''
                        findings.append({
                            'file': filepath,
                            'lineno': node.lineno,
                            'number': n,
                            'context': f"kwarg {kw.arg}={n}: {ctx[:120]}",
                        })
    
    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    parser.add_argument('--min-magnitude', type=float, default=2.0,
                       help='Minimum magnitude to report (default: 2.0, excludes 0/1/2)')
    parser.add_argument('--focus-files', nargs='*',
                        default=None)
    args = parser.parse_args()
    
    workdir = args.dir
    
    if args.focus_files:
        py_files = [os.path.join(workdir, f) for f in args.focus_files if os.path.exists(os.path.join(workdir, f))]
    else:
        py_files = []
        for root, dirs, files in os.walk(workdir):
            if 'dev_tools' in root or '__pycache__' in root or 'node_modules' in root:
                continue
            for f in files:
                if f.endswith('.py') and not f.startswith('_'):
                    py_files.append(os.path.join(root, f))
    
    all_findings = []
    for fp in py_files:
        findings = scan_file_for_magic_numbers(fp)
        all_findings.extend(findings)
    
    # Filter by magnitude
    filtered = [f for f in all_findings if abs(f['number']) >= args.min_magnitude]
    
    print(f"Scanned {len(py_files)} files, found {len(filtered)} magic numbers (≥ |{args.min_magnitude}|)\n")
    
    if filtered:
        print("[MAGIC_NUMBER] Suspicious hardcoded numeric constants (please review):")
        by_file = defaultdict(list)
        for f in filtered:
            by_file[os.path.basename(f['file'])].append(f)
        
        for fname in sorted(by_file.keys()):
            print(f"\n  {fname}:")
            for f in by_file[fname]:
                print(f"    L{f['lineno']:>5}  value={f['number']:>8}  |  {f['context'][:90]}")
    else:
        print("[MAGIC_NUMBER] No suspicious magic numbers found ✅")
    
    return 1 if filtered else 0


if __name__ == '__main__':
    sys.exit(main())
