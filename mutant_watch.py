#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mutant_watch.py — 运行时突变探测器 v1.2

与 kinetic_scan.py（静态扫描）互补。
监控真实运行时数据在时间上的退化。

检测项:
  1. 数据完整性漂移 — 关键 JSON 文件校验和变化
  2. 文件增长趋势 — data/ 下文件大小
  3. 孤立写入检测 — 只写不读的数据文件
  4. API 契约退化 — 路由 handler 返回结构基线漂移
"""

import ast
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta

WATCH_FILE = '.mutant_watch_history.json'
API_CONTRACT_FILE = '.api_contract_baseline.json'

CRITICAL_FILES = [
    'user_profile.json', 'token_usage.jsonl', 'model_tiers.json',
    'deepseek_cache.json', 'intervention_log.jsonl',
]

EXTS_TO_WATCH = {'.json', '.jsonl', '.log', '.db', '.sqlite', '.pkl'}

EXCLUDE_DIRS = {
    'newenv', '.git', '__pycache__', 'node_modules', 'Lib', 'transformers-main',
    '.backup_20260503_0955', '.backup_20260503_1140_v2', '.backup_20260503_1153_v3',
    '.backup_20260503_1313_s1', '.backup_20260503_1339_cache', '.backup_20260503_1436_coach',
    '.backup_20260503_1444_feedback', '.backup_20260503_1453_async', '.backup_20260503_1607_trend',
    '.backup_20260503_2144_dashboard', '.surgical_backups', 'benchmark',
    'security_test', 'scripts', 'src', 'aisleepgen-netlify', 'ai_system', 'backend', 'sensors',
    'docs', 'safe_outputs', 'tests', 'tmp', 'UI', 'demo', 'examples',
    'mypy_cache', 'pytest_cache', '.pytest_cache',
}


# ===================================================================
# 1. 数据完整性漂移
# ===================================================================

def _compute_checksum(fpath):
    try:
        stat = os.stat(fpath)
        if stat.st_size == 0:
            return 'empty:{:.0f}'.format(stat.st_mtime)
        with open(fpath, 'rb') as f:
            head = f.read(65536)
        h = hashlib.sha256(head).hexdigest()[:16]
        return '{}:{}:{:.0f}'.format(h, stat.st_size, stat.st_mtime)
    except Exception:
        return None


def scan_integrity(data_dir):
    history = {}
    hp = os.path.join(data_dir, WATCH_FILE)
    if os.path.exists(hp):
        try:
            with open(hp, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception:
            history = {}

    findings = []
    current = {}
    for fname in CRITICAL_FILES:
        fpath = os.path.join(data_dir, fname)
        if not os.path.exists(fpath):
            continue
        cs = _compute_checksum(fpath)
        if cs is None:
            continue
        current[fname] = cs
        if fname in history and history[fname] != cs:
            old = history[fname].split(':')
            now = cs.split(':')
            delta = int(now[1]) - int(old[1])
            if abs(delta) < 200 and old[0] != now[0]:
                findings.append({'type': 'data_corruption_risk', 'severity': 'HIGH', 'file': fname,
                                'detail': '内容变但大小几乎不变 ({}B)'.format(delta)})
            elif delta < 0:
                findings.append({'type': 'data_loss', 'severity': 'HIGH', 'file': fname,
                                'detail': '缩小 {}B'.format(abs(delta))})
            elif delta > 102400:
                findings.append({'type': 'rapid_growth', 'severity': 'MEDIUM', 'file': fname,
                                'detail': '单次增长 {}B'.format(delta)})

    try:
        with open(hp, 'w', encoding='utf-8') as f:
            json.dump(current, f, indent=2)
    except Exception:
        pass
    return findings


# ===================================================================
# 2. 文件增长趋势
# ===================================================================

def scan_growth(data_dir, days=7):
    findings = []
    dp = os.path.join(data_dir, 'data')
    if not os.path.isdir(dp):
        return findings

    cutoff = time.time() - (days * 86400)
    stats = []
    for root, dirs, files in os.walk(dp):
        if os.path.basename(root).startswith('.'):
            continue
        for fname in files:
            if os.path.splitext(fname)[1].lower() not in EXTS_TO_WATCH:
                continue
            try:
                s = os.stat(os.path.join(root, fname))
                if s.st_mtime > cutoff:
                    stats.append((os.path.relpath(os.path.join(root, fname), data_dir), s.st_size))
            except Exception:
                continue

    stats.sort(key=lambda x: x[1], reverse=True)
    for rel, sz in stats[:8]:
        mb = sz / (1024 * 1024)
        if mb > 50:
            findings.append({'type': 'file_too_large', 'severity': 'HIGH', 'file': rel,
                            'detail': '{:.1f}MB'.format(mb)})
        elif mb > 10:
            findings.append({'type': 'file_large', 'severity': 'MEDIUM', 'file': rel,
                            'detail': '{:.1f}MB'.format(mb)})
    return findings


# ===================================================================
# 3. 孤立写入检测
# ===================================================================

def _has_write_ops(content):
    return bool(re.search(r'''(?:open|dump|write|save_to|store)\s*\(''', content, re.IGNORECASE))


def scan_orphan_writes(data_dir):
    orphan_counts = defaultdict(int)
    first_writer = {}
    readers = set()

    total = 0
    for root, dirs, files in os.walk(data_dir):
        parts = root.replace(os.sep, '/').split('/')
        skip = False
        for part in parts:
            if part in EXCLUDE_DIRS or (part.startswith('.') and part not in ('.', '..')):
                skip = True
                break
        if skip:
            continue
        total += sum(1 for f in files if f.endswith('.py'))
    print('  ({} .py files to scan)'.format(total), end=' ')

    for root, dirs, files in os.walk(data_dir):
        parts = root.replace(os.sep, '/').split('/')
        skip = False
        for part in parts:
            if part in EXCLUDE_DIRS or (part.startswith('.') and part not in ('.', '..')):
                skip = True
                break
        if skip:
            continue
        for fname in files:
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                continue
            rel = os.path.relpath(fpath, data_dir)
            is_writer = _has_write_ops(content)
            for m in re.finditer(r'''['"]([\w.-]+\.(json|jsonl))['"]''', content):
                target = m.group(1)
                if is_writer:
                    orphan_counts[target] += 1
                    if target not in first_writer:
                        first_writer[target] = rel
                else:
                    readers.add(target)

    findings = []
    for target, count in sorted(orphan_counts.items()):
        if target not in readers:
            findings.append({
                'type': 'orphan_write', 'severity': 'LOW', 'file': target,
                'detail': '{} files write to it, none read'.format(count),
                'first_writer': first_writer.get(target, '?'),
            })
    return findings


# ===================================================================
# 4. API 契约退化检测
# ===================================================================

def _extract_return_dict_keys(node):
    """从 AST 节点中提取 dict literal 的 keys"""
    if not isinstance(node, ast.Dict):
        return None
    keys = []
    for k in node.keys:
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            keys.append(k.value)
        elif isinstance(k, ast.Str) and hasattr(k, 's'):
            keys.append(k.s)
        else:
            keys.append('?dynamic_key')
    return keys


def _extract_api_routes(fpath, rel):
    """AST 分析，提取 route handler 的返回结构"""
    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    tree = ast.parse(content, filename=rel)

    # 第一步：收集 route decorators → handler 映射，同时收集 handler 的 AST 节点
    route_handlers = {}  # handler_name -> (route_path, ast_node)
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            path = None
            # @app.route('/path')
            if isinstance(dec.func, ast.Attribute) and 'route' in dec.func.attr:
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    path = dec.args[0].value
            # @route('/path') (自定义)
            if isinstance(dec.func, ast.Name) and dec.func.id in ('route', '_route'):
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    path = dec.args[0].value
            if path:
                route_handlers[node.name] = (path, node)
                break

    if not route_handlers:
        return []

    # 第二步：直接在每个 handler 的 AST 节点内找 return dict
    routes = []
    for fname, (route_path, func_node) in route_handlers.items():
        found_keys = None
        for body_node in ast.walk(func_node):
            if not isinstance(body_node, ast.Return) or body_node.value is None:
                continue
            val = body_node.value
            dict_node = None
            if isinstance(val, ast.Dict):
                dict_node = val
            elif isinstance(val, ast.Call):
                fn = val.func
                fn_name = (isinstance(fn, ast.Name) and fn.id) or (isinstance(fn, ast.Attribute) and fn.attr) or ''
                if fn_name == 'jsonify' and val.args and isinstance(val.args[0], ast.Dict):
                    dict_node = val.args[0]
            if dict_node is not None:
                keys = []
                for k in dict_node.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        keys.append(k.value)
                    else:
                        keys.append('?dynamic')
                if keys:
                    found_keys = keys
                    break
        if found_keys:
            routes.append({
                'route': route_path,
                'handler': fname,
                'file': rel,
                'keys': found_keys,
            })

    return routes


def scan_api_contract(project_dir):
    """检测 API handler 返回结构的基线变化"""
    baseline_path = os.path.join(project_dir, API_CONTRACT_FILE)

    # 扫描当前所有 route handler 的返回结构
    current_routes = []
    for root, dirs, files in os.walk(project_dir):
        parts = root.replace(os.sep, '/').split('/')
        skip = False
        for part in parts:
            if part in EXCLUDE_DIRS or (part.startswith('.') and part not in ('.', '..')):
                skip = True
                break
        if skip:
            continue
        for fname in files:
            if not fname.endswith('.py'):
                continue
            if fname in ('kinetic_scan.py', 'mutant_watch.py', '_quick_scan.py', '_remove_misplaced.py'):
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, project_dir)
            try:
                routes = _extract_api_routes(fpath, rel)
                current_routes.extend(routes)
            except (SyntaxError, Exception):
                continue

    # 按 route 路径索引
    current_map = {}
    for r in current_routes:
        current_map[r['route']] = r

    findings = []

    # 检查 baseline 是否存在
    if not os.path.exists(baseline_path):
        # 首次运行，保存 baseline
        try:
            with open(baseline_path, 'w', encoding='utf-8') as f:
                json.dump(current_map, f, indent=2, ensure_ascii=False)
            print('  (新基线已保存: {} 个 route)'.format(len(current_map)), end=' ')
        except Exception:
            pass
        return findings

    # 加载旧 baseline
    try:
        with open(baseline_path, 'r', encoding='utf-8') as f:
            old_map = json.load(f)
    except Exception:
        old_map = {}

    if not old_map or not isinstance(old_map, dict):
        return findings
    
    if not current_map:
        return findings

    # 比较：旧有 routes 的返回键集是否变化
    for route_path, old_r in old_map.items():
        new_r = current_map.get(route_path)
        if new_r is None:
            findings.append({
                'type': 'api_route_deleted', 'severity': 'HIGH',
                'file': old_r.get('file', '?'),
                'detail': 'Route "{}" (handler: {}) 已不存在 — 可能被删除或改名'.format(
                    route_path, old_r.get('handler', '?')),
            })
            continue

        old_keys = set(old_r.get('keys', []))
        new_keys = set(new_r.get('keys', []))
        if old_keys != new_keys:
            added = new_keys - old_keys
            removed = old_keys - new_keys
            changes = []
            if added:
                changes.append('新增: {}'.format(', '.join(sorted(added))))
            if removed:
                changes.append('移除: {}'.format(', '.join(sorted(removed))))
            findings.append({
                'type': 'api_return_keys_changed', 'severity': 'HIGH' if removed else 'MEDIUM',
                'file': new_r.get('file', '?'),
                'detail': 'Route "{}" 返回键变化 — {}'.format(route_path, '; '.join(changes)),
            })

    # 新增 route（低优先，但记录一下）
    for route_path in set(current_map.keys()) - set(old_map.keys()):
        r = current_map[route_path]
        findings.append({
            'type': 'api_route_added', 'severity': 'LOW',
            'file': r.get('file', '?'),
            'detail': '新增 Route "{}"  (handler: {}, keys: {})'.format(
                route_path, r.get('handler', '?'), ', '.join(r.get('keys', []))),
        })

    # 更新 baseline
    try:
        with open(baseline_path, 'w', encoding='utf-8') as f:
            json.dump(current_map, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return findings


# ===================================================================
# 主入口
# ===================================================================

def run_watch(project_dir):
    project_dir = os.path.abspath(project_dir)
    print('\n' + '=' * 60)
    print('  运行时突变探测器 v1.2')
    print('  目标: {}'.format(project_dir))
    print('  时间: {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    print('=' * 60 + '\n')

    results = []
    checks = [
        ('数据完整性漂移', lambda: scan_integrity(project_dir)),
        ('文件增长趋势', lambda: scan_growth(project_dir)),
        ('孤立写入检测', lambda: scan_orphan_writes(project_dir)),
        ('API 契约退化', lambda: scan_api_contract(project_dir)),
    ]
    for name, func in checks:
        print('[检测] {} ...'.format(name), end=' ', flush=True)
        t0 = time.time()
        r = func()
        print('{} 项 ({:.2f}s)'.format(len(r), time.time() - t0))
        results.extend(r)

    sevs = defaultdict(int)
    for f in results:
        sevs[f.get('severity', '?')] += 1

    print('\n' + '=' * 60)
    print('  完成: {} 项'.format(len(results)))
    print('  HIGH: {}  MEDIUM: {}  LOW: {}'.format(
        sevs.get('HIGH', 0), sevs.get('MEDIUM', 0), sevs.get('LOW', 0)))
    print('=' * 60 + '\n')
    for f in results:
        if f.get('severity') in ('HIGH', 'MEDIUM'):
            print('  {} [{}] {}'.format(f['severity'], f['type'], f['file']))
            print('    {}'.format(f.get('detail', '')))

    return results


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('project_dir')
    args = parser.parse_args()
    run_watch(args.project_dir)
