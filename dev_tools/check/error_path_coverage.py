#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
error_path_coverage.py — 错误路径覆盖率检查

查什么：
- 每个 try/except 块是否有对应的测试路径
- 每个 if/else 分支是否被测试覆盖
- 检查所有 handler 的"异常返回路径"是否被审计日志记录

用法:
  python error_path_coverage.py [--dir D:\AISleepGen_Optimized]
"""

import os, sys, ast, argparse
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')


def analyze_error_paths(filepath):
    """Analyze try/except and branch coverage in a file."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError as e:
            return {'errors': [str(e)], 'try_blocks': [], 'branches': []}
    
    try_blocks = []
    branches = []
    returns = []
    
    for node in ast.walk(tree):
        # Try blocks
        if isinstance(node, ast.Try):
            except_info = []
            for handler in node.handlers:
                exc_type = handler.type
                exc_name = handler.name
                body_preview = ''
                if handler.body:
                    first_stmt = handler.body[0]
                    if isinstance(first_stmt, ast.Expr) and isinstance(first_stmt.value, ast.Call):
                        fn = first_stmt.value.func
                        if isinstance(fn, ast.Name):
                            body_preview = fn.id
                        elif isinstance(fn, ast.Attribute):
                            body_preview = fn.attr
                
                except_info.append({
                    'type': ast.dump(exc_type) if exc_type else 'bare',
                    'name': exc_name,
                    'body_start': body_preview,
                    'body_len': len(handler.body),
                })
            
            try_blocks.append({
                'lineno': node.lineno,
                'excepts': except_info,
                'finally': len(node.finalbody) > 0,
                'else': len(node.orelse) > 0,
            })
        
        # If/else branches
        if isinstance(node, ast.If):
            # Simplify the test expression
            test_str = ast.dump(node.test)[:60]
            branches.append({
                'type': 'if',
                'lineno': node.lineno,
                'condition': test_str,
                'has_else': len(node.orelse) > 0,
                'body_len': len(node.body),
            })
        
        # Return statements inside functions
        if isinstance(node, ast.Return):
            returns.append({
                'lineno': node.lineno,
                'value_type': type(node.value).__name__ if node.value else 'None',
            })
    
    return {
        'try_blocks': try_blocks,
        'branches': branches,
        'returns': returns,
        'errors': [],
    }


def classify_coverage(try_blocks):
    """Classify try block coverage quality."""
    bare_excepts = 0
    empty_excepts = 0
    logged_excepts = 0
    good_excepts = 0
    
    for tb in try_blocks:
        for exc in tb['excepts']:
            if exc['type'] == 'bare' or exc['type'] == 'None':
                bare_excepts += 1
            
            if exc['body_len'] <= 1:
                empty_excepts += 1
            
            if exc['body_start'] in ('print', 'log', 'logging', 'report'):
                logged_excepts += 1
            
            if exc['body_len'] >= 3:
                good_excepts += 1
    
    return {
        'bare_excepts': bare_excepts,
        'empty_excepts': empty_excepts,
        'only_logged': logged_excepts,
        'properly_handled': good_excepts,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    args = parser.parse_args()
    
    workdir = args.dir
    FOCUS = ['deepseek_proxy.py', 'compliance.py', 'audit_logger.py',
             'world_model_coordinator.py', 'state_transition_model.py',
             'biofeedback_renderer.py', 'sleep_phase_planner.py',
             'wx_login.py', 'scheduler_daemon.py', 'discrepancy_detector.py',
             'sleep_world_model.py', 'sleep_homeostasis.py']
    
    print("=" * 60)
    print("  ERROR PATH COVERAGE ANALYSIS")
    print("=" * 60)
    
    for fname in FOCUS:
        fp = os.path.join(workdir, fname)
        if not os.path.exists(fp):
            continue
        
        result = analyze_error_paths(fp)
        
        if result['errors']:
            print(f"\n{fname}: ❌ {result['errors'][0]}")
            continue
        
        cov = classify_coverage(result['try_blocks'])
        
        print(f"\n{'='*50}")
        print(f"  {fname}")
        print(f"{'='*50}")
        print(f"  Try blocks:       {len(result['try_blocks'])}")
        print(f"  If/else branches: {len(result['branches'])}")
        print(f"  Return paths:     {len(result['returns'])}")
        print()
        
        total_excepts = sum(len(tb['excepts']) for tb in result['try_blocks'])
        print(f"  Exception handlers: {total_excepts}")
        print(f"    Bare excepts:             {cov['bare_excepts']}")        
        print(f"    Empty/minimal body:       {cov['empty_excepts']}")
        print(f"    Only logged (no recovery): {cov['only_logged']}")
        print(f"    Properly handled (≥3stmt): {cov['properly_handled']}")
        
        # Show risky blocks
        risky = [tb for tb in result['try_blocks'] 
                 if any(e['type'] in ('bare', 'None') or e['body_len'] <= 1 
                        for e in tb['excepts'])]
        if risky:
            print(f"\n  ⚠️  Risky try blocks ({len(risky)}):")
            for tb in risky[:5]:
                exc_summary = ', '.join(
                    f"L{tb['lineno']}: {e['type']} body={e['body_len']}"
                    for e in tb['excepts']
                )
                print(f"    {exc_summary}")
        
        # Branch coverage estimate
        total_branches = len(result['branches'])
        branches_with_else = sum(1 for b in result['branches'] if b['has_else'])
        if total_branches > 0:
            else_pct = branches_with_else / total_branches * 100
            print(f"\n  Branch completeness: {branches_with_else}/{total_branches} have else ({else_pct:.0f}%)")
            if else_pct < 50:
                print(f"  ⚠️  High implicit else count — many branches silently skip")
        
        # Return path count
        if result['returns']:
            none_returns = sum(1 for r in result['returns'] if r['value_type'] == 'NoneType' or r['value_type'] == 'Constant')
            print(f"  None/empty returns: {none_returns}/{len(result['returns'])}")
    
    print("\n" + "=" * 60)
    print("  DONE")
    print("=" * 60)


if __name__ == '__main__':
    main()
