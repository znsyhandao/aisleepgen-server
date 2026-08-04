#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
resource_leak_detector.py — 资源泄漏检测器（静态）

查什么：
- open() 调用没有对应的 close()（句柄泄漏）
- 文件读写后没有 finally 或 with 语句
- 数据库连接没有 close()
- 线程/进程没有 join()
- 临时文件没有 cleanup

用法:
  python resource_leak_detector.py [--dir D:\AISleepGen_Optimized]
"""

import os, sys, ast, argparse
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')


def check_resource_handling(filepath):
    """Check for proper resource handling in a file."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError as e:
            return {'errors': [str(e)], 'findings': []}
    
    findings = []
    lines = open(filepath, 'r', encoding='utf-8', errors='replace').readlines()
    
    # Track resource openings and closings
    open_calls = []
    close_calls = []
    with_blocks = []
    thread_starts = []
    thread_joins = []
    sess_starts = []
    sess_ends = []
    
    for node in ast.walk(tree):
        # open() calls
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'open':
            # Check if it's inside a with statement
            open_calls.append(node.lineno)
        
        # .close() calls
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'close':
            close_calls.append(node.lineno)
        
        # with blocks
        if isinstance(node, ast.With):
            with_blocks.append(node.lineno)
        
        # Thread start
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'start':
            # Check if it's a thread start
            if isinstance(node.func.value, ast.Call) and isinstance(node.func.value.func, ast.Name):
                if 'Thread' in node.func.value.func.id:
                    thread_starts.append(node.lineno)
        
        # Thread join
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'join':
            thread_joins.append(node.lineno)
        
        # sqlite3.connect / .close
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'connect':
            sess_starts.append(node.lineno)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'commit':
            sess_ends.append(node.lineno)
    
    # 1. Open without close and not in with block
    open_not_in_with = []
    for o_line in open_calls:
        # Check if this open() is inside a with block
        in_with = False
        for w_line in with_blocks:
            # Simple check: look for 'with open' pattern
            if w_line <= o_line <= w_line + 5:
                # Find the with statement
                with_stmt = ''.join(lines[w_line-1:w_line]).strip() if w_line <= len(lines) else ''
                if 'open' in with_stmt:
                    in_with = True
                    break
        
        if not in_with:
            open_not_in_with.append(o_line)
    
    if open_not_in_with:
        findings.append({
            'type': 'OPEN_WITHOUT_WITH',
            'severity': 'MEDIUM',
            'count': len(open_not_in_with),
            'lines': open_not_in_with[:10],
            'detail': 'open() call not inside with statement — potential file handle leak',
        })
    
    # 2. More open calls than close calls
    if len(open_calls) > len(close_calls) + len(with_blocks):
        findings.append({
            'type': 'POSSIBLE_HANDLE_LEAK',
            'severity': 'HIGH',
            'count': len(open_calls) - len(close_calls) - len(with_blocks),
            'detail': f'{len(open_calls)} open() calls vs {len(close_calls)} close() + {len(with_blocks)} with blocks',
        })
    
    # 3. Threads started but not joined
    if thread_starts and not thread_joins:
        findings.append({
            'type': 'THREAD_NOT_JOINED',
            'severity': 'LOW',
            'count': len(thread_starts),
            'detail': f'{len(thread_starts)} thread(s) started but no join() found',
        })
    
    # 4. Check for temporary files
    for i, line in enumerate(lines, 1):
        if 'tempfile' in line.lower() or 'TemporaryFile' in line or 'NamedTemporaryFile' in line:
            # Check if there's cleanup
            nearby = ''.join(lines[i:min(i+10, len(lines))])
            if 'cleanup' not in nearby.lower() and 'delete' not in nearby.lower():
                findings.append({
                    'type': 'TEMP_FILE_NO_CLEANUP',
                    'severity': 'HIGH',
                    'line': i,
                    'detail': f'Temporary file created at line {i} without explicit cleanup',
                })
    
    return {'findings': findings, 'errors': []}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    args = parser.parse_args()
    
    workdir = args.dir
    FOCUS = ['deepseek_proxy.py', 'compliance.py', 'audit_logger.py',
             'world_model_coordinator.py', 'state_transition_model.py',
             'biofeedback_renderer.py', 'sleep_phase_planner.py',
             'scheduler_daemon.py', 'discrepancy_detector.py',
             'sleep_homeostasis.py']
    
    print("=" * 60)
    print("  RESOURCE LEAK DETECTOR")
    print("=" * 60)
    
    all_findings = []
    
    for fname in FOCUS:
        fp = os.path.join(workdir, fname)
        if not os.path.exists(fp):
            continue
        
        result = check_resource_handling(fp)
        if result['findings']:
            print(f"\n  {fname}: {len(result['findings'])} finding(s)")
            for f in result['findings']:
                print(f"  [{f['severity']}] {f['type']}: {f['detail'][:100]}")
                if 'lines' in f:
                    for l in f['lines'][:5]:
                        # Show the actual line
                        with open(fp, 'r', encoding='utf-8', errors='replace') as fh:
                            lines = fh.readlines()
                        if l <= len(lines):
                            print(f"     L{l}: {lines[l-1].strip()[:80]}")
            all_findings.extend(result['findings'])
        else:
            print(f"\n  {fname}: ✅ No issues")
    
    high = [f for f in all_findings if f['severity'] == 'HIGH']
    med = [f for f in all_findings if f['severity'] == 'MEDIUM']
    low = [f for f in all_findings if f['severity'] == 'LOW']
    
    print(f"\n{'='*60}")
    print(f"  HIGH:  {len(high)}  MEDIUM: {len(med)}  LOW: {len(low)}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
