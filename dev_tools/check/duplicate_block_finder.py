#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
duplicate_block_finder.py — 重复代码块模式匹配扫描器

查什么：
- 文件内重复的函数/方法（MD5 比较）
- 跨文件相似代码块（文本相似度 > 0.85）
- 复制粘贴后忘记改参数名的模式

用法:
  python duplicate_block_finder.py [--dir D:\AISleepGen_Optimized] [--threshold 0.85]
"""

import os, sys, ast, hashlib, textwrap, argparse

sys.stdout.reconfigure(encoding='utf-8')

def get_function_bodies(filepath):
    """Extract function/method AST nodes with their source code."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError as e:
            return [], [(0, 0, f"SYNTAX ERROR: {e}")]
    
    bodies = []
    errors = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Get the source lines for this function
            if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f2:
                    lines = f2.readlines()
                src = ''.join(lines[node.lineno-1:node.end_lineno])
                # Normalize: strip comments, normalize whitespace
                normalized = normalize_source(src)
                md5 = hashlib.md5(normalized.encode('utf-8')).hexdigest()
                bodies.append({
                    'name': node.name,
                    'lineno': node.lineno,
                    'end_lineno': node.end_lineno,
                    'md5': md5,
                    'normalized': normalized,
                    'file': filepath,
                    'raw': src[:200],
                })
    
    return bodies, errors


def normalize_source(src):
    """Normalize source for comparison: strip comments, normalize whitespace."""
    import re
    # Remove comments
    src = re.sub(r'#.*$', '', src, flags=re.MULTILINE)
    # Normalize whitespace
    src = re.sub(r'\s+', ' ', src)
    # Strip empty lines
    src = src.strip()
    return src


def find_duplicate_blocks(functions):
    """Find functions with identical MD5."""
    by_md5 = {}
    for f in functions:
        by_md5.setdefault(f['md5'], []).append(f)
    
    results = []
    for md5, funcs in by_md5.items():
        if len(funcs) >= 2:
            # Check it's not just an empty body
            if len(funcs[0]['normalized']) > 20:
                results.append({
                    'type': 'EXACT_DUPLICATE',
                    'count': len(funcs),
                    'instances': [f"{f['name']} @ {f['file']}:L{f['lineno']}" 
                                 for f in funcs],
                    'preview': funcs[0]['raw'][:150],
                })
    
    return results


def find_similar_blocks(functions, threshold=0.85):
    """Find functions with similar but not identical bodies."""
    from difflib import SequenceMatcher
    results = []
    checked = set()
    
    for i, a in enumerate(functions):
        for j, b in enumerate(functions):
            if i >= j: continue
            key = (i, j)
            if key in checked: continue
            checked.add(key)
            
            ratio = SequenceMatcher(None, a['normalized'], b['normalized']).ratio()
            if threshold <= ratio < 1.0:
                results.append({
                    'type': 'SIMILAR',
                    'similarity': round(ratio, 3),
                    'a': f"{a['name']} @ {a['file']}:L{a['lineno']}",
                    'b': f"{b['name']} @ {b['file']}:L{b['lineno']}",
                })
    
    # Sort by similarity descending, keep top 20
    results.sort(key=lambda x: -x['similarity'])
    return results[:20]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    parser.add_argument('--threshold', type=float, default=0.85)
    parser.add_argument('--files', nargs='*', help='Specific files to scan')
    args = parser.parse_args()
    
    workdir = args.dir
    if args.files:
        py_files = [f if os.path.isabs(f) else os.path.join(workdir, f) for f in args.files]
    else:
        py_files = []
        for root, dirs, files in os.walk(workdir):
            # Skip dev_tools, node_modules, __pycache__
            if 'dev_tools' in root or '__pycache__' in root or 'node_modules' in root:
                continue
            for f in files:
                if f.endswith('.py'):
                    py_files.append(os.path.join(root, f))
    
    all_functions = []
    all_errors = []
    
    for fp in py_files:
        bodies, errors = get_function_bodies(fp)
        all_functions.extend(bodies)
        all_errors.extend(errors)
    
    print(f"Scanned {len(py_files)} files, {len(all_functions)} functions\n")
    
    # 1. Exact duplicates
    exact = find_duplicate_blocks(all_functions)
    if exact:
        print(f"[DUPLICATE_BLOCK] Found {len(exact)} exact duplicate group(s):")
        for dup in exact:
            print(f"  ⚠️  {dup['type']}: {dup['count']} instances")
            for inst in dup['instances']:
                print(f"      {inst}")
            print(f"     Preview: {dup['preview'][:100]}")
            print()
    else:
        print("[DUPLICATE_BLOCK] No exact duplicates found ✅")
    
    # 2. Similar blocks
    similar = find_similar_blocks(all_functions, args.threshold)
    if similar:
        print(f"\n[DUPLICATE_BLOCK] Found {len(similar)} similar function pairs (threshold={args.threshold}):")
        for s in similar:
            print(f"  🔍 {s['similarity']:.1%} similar:")
            print(f"     A: {s['a']}")
            print(f"     B: {s['b']}")
    else:
        print(f"\n[DUPLICATE_BLOCK] No similar functions above {args.threshold} ✅")
    
    # 3. Errors
    for err in all_errors:
        print(f"  ❌ {err}")
    
    return 1 if exact else 0


if __name__ == '__main__':
    sys.exit(main())
