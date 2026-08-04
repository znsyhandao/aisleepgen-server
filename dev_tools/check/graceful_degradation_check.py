#!/usr/bin/env python3
"""graceful_degradation_check.py — 优雅降级审计

检查：handler 失败时是否返回友好消息而非500
"""
import os, sys, re, ast, argparse
sys.stdout.reconfigure(encoding='utf-8')

def scan_degradation(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
        lines = content.split('\n')
    
    issues = []
    
    # Find all handler methods
    for i, line in enumerate(lines, 1):
        if 'def _handle_' in line or 'def do_' in line:
            # Check if there's a try within next 20 lines
            nearby = ''.join(lines[i:min(i+20, len(lines))])
            if 'try' not in nearby and 'except' not in nearby:
                func_name = line.strip()[:60]
                issues.append({
                    'lineno': i,
                    'handler': func_name,
                    'issue': 'No try/except in handler — any exception returns 500',
                })
    
    # Check for raw 500 strings
    if '500' in content and 'Internal Server Error' in content:
        # Find locations
        for i, line in enumerate(lines, 1):
            if '500' in line and ('error' in line.lower() or 'Internal' in line):
                issues.append({
                    'lineno': i,
                    'handler': 'global',
                    'issue': 'Hardcoded 500 response — user sees raw error',
                })
    
    return issues

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    args = parser.parse_args()
    workdir = args.dir
    
    fp = os.path.join(workdir, 'deepseek_proxy.py')
    if not os.path.exists(fp):
        print('deepseek_proxy.py not found')
        return
    
    print('='*60)
    print('  GRACEFUL DEGRADATION AUDIT')
    print('='*60)
    
    issues = scan_degradation(fp)
    if issues:
        print(f'\n  Found {len(issues)} degradation issue(s):')
        for i in issues[:15]:
            print(f"  L{i['lineno']:>5}: [{i['handler']}] {i['issue'][:80]}")
    else:
        print('  ✅ All handlers have error protection')

if __name__ == '__main__':
    main()
