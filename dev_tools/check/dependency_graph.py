#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dependency_graph.py — 依赖图生成器

生成什么：
- 跨文件的 import 依赖关系图（文本树）
- 检测循环依赖
- 检测 import 了但不存在于文件系统的模块
- 检测 __init__.py 缺失

用法:
  python dependency_graph.py [--dir D:\AISleepGen_Optimized]
"""

import os, sys, ast, argparse
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')


def get_imports(filepath):
    """Extract all imports from a file."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError:
            return [], []
    
    stdlib_imports = []
    local_imports = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name.startswith('_') or '.' in name:
                    local_imports.append(name)
                else:
                    stdlib_imports.append(name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            names = [alias.name for alias in node.names]
            for n in names:
                full = f"{module}.{n}" if module else n
                if module and (module.startswith('_') or '.' in module):
                    local_imports.append(full)
                else:
                    stdlib_imports.append(full)
    
    return stdlib_imports, local_imports


def find_files(workdir, focus_files=None):
    """Find Python files to scan."""
    if focus_files:
        return [os.path.join(workdir, f) for f in focus_files if os.path.exists(os.path.join(workdir, f))]
    
    files = []
    for f in os.listdir(workdir):
        if f.endswith('.py') and not f.startswith('_') and f != 'aisleepgen_tool.py':
            files.append(os.path.join(workdir, f))
    return files


def check_circular_deps(graph):
    """Simple circular dependency check (depth-limited DFS)."""
    cycles = []
    for node in graph:
        visited = set()
        stack = [(node, [node])]
        while stack:
            current, path = stack.pop()
            if current in visited and len(path) > 1:
                continue
            visited.add(current)
            for neighbor in graph.get(current, []):
                if neighbor == node:
                    cycles.append(path + [neighbor])
                elif neighbor not in visited and len(path) < 10:
                    stack.append((neighbor, path + [neighbor]))
    return cycles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    parser.add_argument('--focus-files', nargs='*',
                        default=['deepseek_proxy.py', 'world_model_coordinator.py',
                                 'state_transition_model.py', 'sleep_phase_planner.py',
                                 'biofeedback_renderer.py', 'compliance.py', 'audit_logger.py',
                                 'wx_login.py', 'sleep_world_model.py', 'sleep_homeostasis.py',
                                 'discrepancy_detector.py', 'scheduler_daemon.py',
                                 'dp_router.py'])
    args = parser.parse_args()
    
    workdir = args.dir
    files = find_files(workdir, args.focus_files)
    
    print(f"=== DEPENDENCY GRAPH ===\n")
    print(f"Scanning {len(files)} files in {workdir}\n")
    
    # Check __init__.py
    init_path = os.path.join(workdir, '__init__.py')
    init_exists = os.path.exists(init_path)
    if not init_exists:
        print(f"⚠️  IMPORTANT: __init__.py missing in {workdir}")
        print(f"   This may cause 'from utils import something' to fail silently\n")
    
    # Build graph
    graph = defaultdict(list)
    missing_imports = []
    all_local = set()
    
    for fp in files:
        fname = os.path.basename(fp)
        stdlib, local = get_imports(fp)
        graph[fname] = []
        all_local.add(fname)
        
        for imp in local:
            # Guess which file this import resolves to
            parts = imp.split('.')
            possible_targets = []
            
            # Check if the last part matches a .py file
            for f in all_local:
                base = f.replace('.py', '')
                if base in parts or parts[-1] == base:
                    possible_targets.append(f)
            
            if not possible_targets:
                # Check if it might be a direct module file
                for fname2 in os.listdir(workdir):
                    if fname2.endswith('.py') and parts[-1] in fname2:
                        possible_targets.append(fname2)
                # Check in subdirectories
                for root, dirs, _ in os.walk(workdir):
                    if 'dev_tools' in root: continue
                    for f in os.listdir(root):
                        if f == f"{parts[-1]}.py":
                            rel = os.path.relpath(os.path.join(root, f), workdir)
                            possible_targets.append(rel)
            
            if possible_targets:
                for pt in possible_targets[:2]:
                    graph[fname].append(pt)
            else:
                missing_imports.append((fname, imp))
    
    # Print dependency tree
    for fname in sorted(graph.keys()):
        deps = graph.get(fname, [])
        if deps:
            print(f"  {fname:40s} → {', '.join(deps[:5])}")
            if len(deps) > 5:
                print(f"  {'':40s}   ... +{len(deps)-5} more")
        else:
            print(f"  {fname:40s} → (no local dependencies)")
    
    # Check for missing imports
    if missing_imports:
        print(f"\n[DEPENDENCY] Possibly missing imports ({len(missing_imports)}):")
        for fname, imp in sorted(missing_imports):
            print(f"  ⚠️  {fname} imports '{imp}' — could not resolve to a local file")
    
    # Check for circular deps
    print(f"\n[DEPENDENCY] Circular dependency check...")
    # Simple cycle detection
    found_cycle = False
    for fname in graph:
        deps = graph.get(fname, [])
        for d in deps:
            if fname in graph.get(d, []):
                print(f"  ⚠️  POTENTIAL CYCLE: {fname} ↔ {d}")
                found_cycle = True
    if not found_cycle:
        print("  No direct circular dependencies detected ✅")
    
    # Check for unused files (in focus list but not imported by any other)
    imported_set = set()
    for deps in graph.values():
        imported_set.update(deps)
    unused = [f for f in files if os.path.basename(f) not in imported_set]
    if unused:
        print(f"\n[DEPENDENCY] Files not imported by any other scanned file:")
        for f in unused:
            print(f"  ℹ️  {os.path.basename(f)}")
    
    return 1 if missing_imports else 0


if __name__ == '__main__':
    sys.exit(main())
