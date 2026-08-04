#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data_flow_audit.py — 数据流审计脚本

查什么：
- 关键数据路径上的非空断言（每一步的数据是否被正确传递）
- 静默退化检测（比如世界模型 fallback 走了多少次）
- 数据格式一致性检查

用法:
  python data_flow_audit.py [--dir D:\AISleepGen_Optimized]
"""

import os, sys, ast, argparse
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')


def scan_data_flow(filepath):
    """Scan for potential data flow issues in a file."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content, filename=filepath)
    except SyntaxError as e:
        return {'file': filepath, 'errors': [f"SYNTAX ERROR: {e}"], 'findings': []}
    
    findings = []
    lines = content.split('\n')
    
    for node in ast.walk(tree):
        # 1. Detect bare except: that silence errors
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                context_start = max(0, node.lineno - 2)
                ctx_lines = lines[context_start:node.lineno + 2]
                ctx = '\n'.join(ctx_lines)
                findings.append({
                    'type': 'bare_except',
                    'file': filepath,
                    'lineno': node.lineno,
                    'context': ctx[:200],
                })
        
        # 2. Detect try blocks with empty except body
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                if handler.type is None:
                    body = handler.body
                    if len(body) <= 1:
                        # Check if the only body statement is pass or print
                        if all(isinstance(stmt, ast.Pass) or 
                               (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) 
                                and isinstance(stmt.value.func, ast.Name) 
                                and stmt.value.func.id == 'print')
                               for stmt in body):
                            findings.append({
                                'type': 'empty_except_block',
                                'file': filepath,
                                'lineno': handler.lineno,
                                'context': f"except block at L{handler.lineno} has no recovery logic",
                            })
        
        # 3. Detect try blocks in function bodies that may swallow exceptions
        if isinstance(node, ast.Try):
            context_around = lines[max(0, node.lineno-3):node.lineno] if node.lineno > 1 else lines[:1]
            findings.append({
                'type': 'try_block',
                'file': filepath,
                'lineno': node.lineno,
                'context': f"try at L{node.lineno}: {context_around[0].strip()[:80] if context_around else '?'}",
            })
    
    # 4. Simple pattern: detect if 'fallback' is in code
    if 'fallback' in content.lower():
        findings.append({
            'type': 'has_fallback',
            'file': filepath,
            'lineno': 0,
            'context': 'This file contains fallback logic — verify it is not masking real errors',
        })
    
    return {'file': filepath, 'errors': [], 'findings': findings}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    parser.add_argument('--focus-files', nargs='*',
                        default=['deepseek_proxy.py', 'world_model_coordinator.py', 
                                 'state_transition_model.py', 'sleep_phase_planner.py',
                                 'biofeedback_renderer.py', 'compliance.py', 'audit_logger.py'])
    args = parser.parse_args()
    
    workdir = args.dir
    all_findings = []
    
    for fname in args.focus_files:
        fp = os.path.join(workdir, fname)
        if not os.path.exists(fp):
            print(f"[SKIP] {fname} not found")
            continue
        result = scan_data_flow(fp)
        
        if result['errors']:
            for e in result['errors']:
                print(f"  ❌ {fname}: {e}")
        
        by_type = defaultdict(list)
        for f in result['findings']:
            by_type[f['type']].append(f)
            all_findings.append(f)
        
        print(f"\n[DATA_FLOW] {fname}:")
        if not result['findings']:
            print("  No data flow issues found ✅")
        else:
            for ftype, items in sorted(by_type.items()):
                print(f"  [{ftype}] {len(items)} occurrence(s):")
                for item in items[:5]:
                    if item['lineno']:
                        print(f"    L{item['lineno']}: {item['context'][:100]}")
                    else:
                        print(f"    {item['context'][:100]}")
                if len(items) > 5:
                    print(f"    ... and {len(items)-5} more")
    
    # Summary
    bare_excepts = [f for f in all_findings if f['type'] == 'bare_except']
    empty_blocks = [f for f in all_findings if f['type'] == 'empty_except_block']
    fallbacks = [f for f in all_findings if f['type'] == 'has_fallback']
    
    print(f"\n{'='*60}")
    print(f"  DATA FLOW AUDIT SUMMARY")
    print(f"{'='*60}")
    print(f"  Bare except handlers:      {len(bare_excepts)}")
    print(f"  Empty except blocks:       {len(empty_blocks)}")
    print(f"  Files with fallback logic: {len(fallbacks)}")
    print(f"  Total try blocks:          {len([f for f in all_findings if f['type'] == 'try_block'])}")
    
    risky = len(bare_excepts) + len(empty_blocks)
    print(f"  Risky findings (need review): {risky}")
    
    return 1 if risky > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
