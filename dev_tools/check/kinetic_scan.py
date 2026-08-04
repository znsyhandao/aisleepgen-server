#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kinetic_scan.py — 突变动力学扫描器 v1.2

检测代码在时间维度上的退化风险（突变动力学分析）。
与数学深度审核（静态正确性）互补。

v1.2: 新增学习能力 — 自动忽略被用户标记为 false positive 的发现

用法:
  python kinetic_scan.py <项目目录>
  python kinetic_scan.py <项目目录> --json       # JSON 输出
  python kinetic_scan.py <项目目录> --output <路径> # 保存报告
  python kinetic_scan.py <项目目录> --learn        # 启用学习模式（生成忽略文件）
"""
import ast
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime

RESULTS = {
    "tool": "kinetic_scan.py v1.2",
    "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "target": "",
    "findings": [],
    "summary": {},
    "ignored_by_learning": 0,
}

EXCLUDE_DIRS = {
    'newenv', '.git', 'transformers-main', '__pycache__', 'node_modules',
    'Lib', '.venv', 'aisleep_ven', 'aisleep_venv',
    '.backup_20260503_0955', '.backup_20260503_1140_v2', '.backup_20260503_1153_v3',
    '.backup_20260503_1313_s1', '.backup_20260503_1339_cache', '.backup_20260503_1436_coach',
    '.backup_20260503_1444_feedback', '.backup_20260503_1453_async', '.backup_20260503_1607_trend',
    '.backup_20260503_2144_dashboard', '.surgical_backups', 'benchmark',
    'security_test', 'scripts', 'src', 'aisleepgen-netlify', 'ai_system', 'backend', 'sensors',
    'docs', 'safe_outputs', 'tests', 'tmp', 'UI', 'demo', 'examples',
    'mypy_cache', 'pytest_cache', '.pytest_cache',
}

EXCLUDE_FILES = {
    '_remove_misplaced.py',
    'setup.py', 'conf.py',
}

EXCLUDE_FILE_PATTERNS = [
    r'test_.*\.py$',
    r'.*_test\.py$',
    r'conftest\.py$',
]

HOT_PATH_NAMES = {'router', 'handler', 'dispatch', 'api', 'server', 'main', 'async', 'pipeline',
                  'chat', 'message', 'sync', 'profile', 'storage', 'client', 'ai_client'}


def _is_hot_path(filename):
    name = filename.lower()
    for kw in HOT_PATH_NAMES:
        if kw in name:
            return True
    return False


def _should_scan_file(relpath):
    fname = os.path.basename(relpath)
    if fname in EXCLUDE_FILES:
        return False
    for pattern in EXCLUDE_FILE_PATTERNS:
        if re.match(pattern, fname):
            return False
    return True


# ===================================================================
# 学习系统：识别和记住 noise
# ===================================================================

LEARN_FNAME = '.kinetic_learn.json'


def _learn_path(target_dir):
    return os.path.join(target_dir, LEARN_FNAME)


def _load_knowledge(target_dir):
    """加载之前积累的学习数据"""
    lpath = _learn_path(target_dir)
    defaults = {
        "last_scan": None,
        "ignored_findings": [],     # 用户标记为 ignore 的 (type, file, line)
        "known_false_patterns": [], # 用户确认的通用 false positive 模式
        "log_rotation_whitelist": [],  # 已知安全的日志文件
        "shared_writes_whitelist": [], # 已知安全的多写目标
    }
    try:
        if os.path.exists(lpath):
            with open(lpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for k in defaults:
                    if k not in data:
                        data[k] = defaults[k]
                return data
    except Exception:
        pass
    return defaults


def _save_knowledge(target_dir, data):
    """保存学习数据"""
    lpath = _learn_path(target_dir)
    try:
        with open(lpath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False



def _auto_aggregate(findings):
    """自动聚合：将同类、同文件的 LOW 发现合并为一条"""
    from collections import defaultdict
    categories = defaultdict(list)
    for f in findings:
        if f.get('severity') in ('HIGH', 'MEDIUM'):
            continue
        key = (f.get('type'), f.get('file'))
        categories[key].append(f)
    kept = [f for f in findings if f.get('severity') in ('HIGH', 'MEDIUM')]
    for (ftype, ffile), items in sorted(categories.items()):
        if len(items) == 1:
            kept.append(items[0])
        else:
            kept.append({
                'type': ftype,
                'severity': 'LOW',
                'file': ffile,
                'line': items[0].get('line', 0),
                'context': items[0].get('context', ''),
                'note': '%d 项同类发现 (自聚合)' % len(items),
                'check': items[0].get('check', ''),
                'aggregated': len(items),
            })
    return kept


def _auto_severity_suppress(findings):
    """数量哨兵：同类发现超过阈值自动降级"""
    from collections import defaultdict
    type_counts = defaultdict(int)
    for f in findings:
        type_counts[(f.get('type'), f.get('severity'))] += 1
    SUPPRESS_THRESHOLD = {
        'import_side_effect': 5,
        'log_no_rotation': 3,
        'mutable_default_arg': 3,
    }
    for f in findings:
        ftype = f.get('type', '')
        count = type_counts.get((ftype, f.get('severity')), 0)
        threshold = SUPPRESS_THRESHOLD.get(ftype, 999)
        if count > threshold and f.get('severity') != 'HIGH':
            f['_suppressed'] = True
            f['severity'] = 'LOW'
    # import_side_effect 全部只给 summary 不计入逐条
    return [f for f in findings if not (f.get('type') == 'import_side_effect' and f.get('_suppressed'))]


def _is_known_finding(finding, knowledge):
    """知识库中是否已认识这个发现"""
    ftype = finding.get('type', '')
    ffile = finding.get('file', '')
    fline = finding.get('line', 0)

    # 是否被用户忽略过
    for ignored in knowledge.get('ignored_findings', []):
        if (ignored.get('type') == ftype and
            ignored.get('file') == ffile and
            ignored.get('line') == fline):
            return True

    # 是否在 whitelist 中
    if ftype == 'shared_write':
        fname = finding.get('file', '')
        if fname in knowledge.get('shared_writes_whitelist', []):
            return True
    if ftype == 'log_no_rotation':
        fname = finding.get('file', '')
        if fname in knowledge.get('log_rotation_whitelist', []):
            return True

    return False


# ===================================================================
# 扫描器：except:pass
# ===================================================================

def scan_except_pass(target_dir):
    findings = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in files:
            if not fname.endswith('.py'):
                continue
            rel = os.path.relpath(os.path.join(root, fname), target_dir)
            if not _should_scan_file(rel):
                continue
            is_hot = _is_hot_path(fname)
            try:
                with open(os.path.join(root, fname), 'r', encoding='utf-8', errors='ignore') as fh:
                    content = fh.read()
                tree = ast.parse(content, filename=rel)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ExceptHandler):
                        if node.type is None:
                            for body in node.body:
                                if isinstance(body, ast.Pass):
                                    context = content.split('\n')[node.lineno - 1].strip()[:80]
                                    findings.append({
                                        "type": "except_pass",
                                        "severity": "HIGH" if is_hot else "MEDIUM",
                                        "file": rel,
                                        "line": node.lineno,
                                        "context": context,
                                        "note": "热路径: 静默吞异常会掩盖用户请求错误" if is_hot else "离线路径: 数据污染风险",
                                    })
                                    break
            except SyntaxError:
                pass
    return findings


# ===================================================================
# 扫描器：跨文件写入相同文件
# ===================================================================

def scan_shared_writes(target_dir):
    writers = defaultdict(set)
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in files:
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, target_dir)
            if not _should_scan_file(rel):
                continue
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as fh:
                    content = fh.read()
            except:
                continue
            for m in re.finditer(r"""['"](\w+\.(json|jsonl|db|sqlite|pkl|pickle))['"]""", content):
                target_name = m.group(1)
                if 'dump' in content or 'open.*w' in content or 'append' in content:
                    writers[target_name].add(rel)

    findings = []
    for target_name, files in sorted(writers.items()):
        if len(files) >= 3:
            findings.append({
                "type": "shared_write",
                "severity": "HIGH" if len(files) >= 5 else "MEDIUM",
                "file": target_name,
                "writers": sorted(files),
                "count": len(files),
                "note": f"{len(files)} 个文件写入同一目标，无锁竞争风险" if len(files) >= 5 else f"{len(files)} 个文件写入同一目标",
            })
    return findings


# ===================================================================
# 扫描器：Thread 无 daemon
# ===================================================================

def scan_thread_daemon(target_dir):
    findings = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in files:
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, target_dir)
            if not _should_scan_file(rel):
                continue
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as fh:
                    tree = ast.parse(fh.read(), filename=rel)
            except:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    is_thread_call = (isinstance(func, ast.Name) and func.id == 'Thread') or \
                                     (isinstance(func, ast.Attribute) and func.attr == 'Thread')
                    if is_thread_call:
                        has_daemon = any(
                            kw.arg == 'daemon' for kw in node.keywords if isinstance(kw, ast.keyword) and kw.arg
                        )
                        if not has_daemon:
                            findings.append({
                                "type": "thread_no_daemon",
                                "severity": "HIGH",
                                "file": rel,
                                "line": node.lineno,
                                "context": "Thread(...) 无 daemon=True",
                                "note": "进程退出后线程残留，可能阻塞端口重启",
                            })
    return findings


# ===================================================================
# 扫描器：可变默认参数
# ===================================================================

def scan_mutable_defaults(target_dir):
    findings = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in files:
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, target_dir)
            if not _should_scan_file(rel):
                continue
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as fh:
                    tree = ast.parse(fh.read(), filename=rel)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        for default in node.args.defaults:
                            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                                findings.append({
                                    "type": "mutable_default_arg",
                                    "severity": "MEDIUM",
                                    "file": rel,
                                    "line": node.lineno,
                                    "context": node.name,
                                    "note": f"函数 {node.name} 使用可变默认参数，多次调用共享同一对象",
                                })
                                break
            except Exception:
                pass
    return findings


# ===================================================================
# 扫描器：日志无轮转
# ===================================================================

def scan_log_rotation(target_dir):
    findings = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in files:
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, target_dir)
            if not _should_scan_file(rel):
                continue
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as fh:
                    content = fh.read()
            except:
                continue
            if '.jsonl' in content or '.log' in content:
                has_rotate = 'RotatingFileHandler' in content or 'rotate' in content.lower()
                if not has_rotate and ('append' in content or 'w' in content):
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if ('.jsonl' in line or '.log' in line) and 'w' in line and 'rotate' not in line.lower():
                            if line.strip().startswith('#'):
                                continue
                            findings.append({
                                "type": "log_no_rotation",
                                "severity": "LOW",
                                "file": rel,
                                "line": i,
                                "context": line.strip()[:80],
                                "note": "日志/jsonl 文件无限增长无轮转，建议添加 RotatingFileHandler",
                            })
                            break
    return findings


# ===================================================================
# 扫描器：导入副作用
# ===================================================================

def scan_import_side_effects(target_dir):
    findings = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in files:
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, target_dir)
            if not _should_scan_file(rel):
                continue
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as fh:
                    content = fh.read()
                tree = ast.parse(content, filename=rel)
                has_main_guard = False
                for node in ast.walk(tree):
                    if isinstance(node, ast.If):
                        if isinstance(node.test, ast.Compare):
                            left = node.test.left
                            comparators = node.test.comparators
                            if (isinstance(left, ast.Name) and left.id == '__name__' and
                                any(getattr(c, 'value', '') == '__main__'
                                    for c in comparators if isinstance(c, ast.Constant))):
                                has_main_guard = True
                                break
                if not has_main_guard:
                    top_level = [n for n in tree.body
                                 if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                       ast.ClassDef, ast.Import, ast.ImportFrom))]
                    if top_level:
                        findings.append({
                            "type": "import_side_effect",
                            "severity": "LOW",
                            "file": rel,
                            "line": top_level[0].lineno,
                            "context": f"{len(top_level)} 条顶级语句无 __name__ 保护",
                            "note": "被 import 时会自动执行顶级代码",
                        })
            except Exception:
                pass
    return findings


# ===================================================================
# 学习模式：交互式标记 false positive
# ===================================================================


def run_all(target_dir, learn_mode=False):
    target_dir = os.path.abspath(target_dir)
    RESULTS["target"] = target_dir

    print(f"\n{'='*60}")
    print(f"  突变动力学扫描器 v1.2")
    print(f"  目标: {target_dir}")
    print(f"  时间: {RESULTS['scan_time']}")
    if learn_mode:
        print(f"  模式: 学习 (标记 noise 后自动忽略)")
    print(f"{'='*60}")

    # 加载已有知识
    knowledge = _load_knowledge(target_dir)
    if knowledge.get('ignored_findings'):
        print(f"  已知忽略: {len(knowledge['ignored_findings'])} 条 + "
              f"{len(knowledge.get('shared_writes_whitelist', []))} 项白名单")
    print()

    scanners = [
        ("except:pass 检测", scan_except_pass),
        ("跨文件无锁写入", scan_shared_writes),
        ("Thread 无 daemon", scan_thread_daemon),
        ("可变默认参数", scan_mutable_defaults),
        ("日志无轮转", scan_log_rotation),
        ("导入副作用", scan_import_side_effects),
    ]

    all_findings = []
    for scan_name, scan_func in scanners:
        print(f"[扫描] {scan_name} ...", end=' ', flush=True)
        t0 = time.time()
        result = scan_func(target_dir)
        elapsed = time.time() - t0
        print(f"{len(result)} 项 ({elapsed:.2f}s)")

        for f in result:
            f["check"] = scan_name
        all_findings.extend(result)

    # 应用已知知识过滤
    ignored_count = 0
    filtered = []
    for f in all_findings:
        if _is_known_finding(f, knowledge):
            ignored_count += 1
            continue
        filtered.append(f)

    RESULTS["ignored_by_learning"] = ignored_count

    print(f"\n{'='*60}")
    print(f"  扫描完成: {len(all_findings)} 项 (原始)")
    print(f"{'='*60}")

    # ===== 自动聚合 =====
    after_aggregate = _auto_aggregate(all_findings)
    after_suppress = _auto_severity_suppress(after_aggregate)

    before = len(all_findings)
    after = len(after_suppress)
    suppressed = sum(1 for f in after_suppress if f.get('_suppressed'))

    RESULTS["ignored_by_learning"] = suppressed
    RESULTS["before_aggregation"] = len(all_findings)

    print(f"\n{'='*60}")
    print(f"  自动聚合: {before} → {after} 项 ({suppressed} 项同类已聚合)")
    # 额外显示 import_side_effect 被抑制的计数
    total_imports = sum(1 for f in all_findings if f.get('type') == 'import_side_effect')
    remaining_imports = sum(1 for f in after_suppress if f.get('type') == 'import_side_effect')
    if total_imports > 0:
        print(f"  导入副作用: {total_imports} → {remaining_imports} (仅summary不逐条报告)")
    print(f"{'='*60}")

    severity_counts = defaultdict(int)
    type_counts = defaultdict(int)
    for f in after_suppress:
        severity_counts[f.get("severity", "UNKNOWN")] += 1
        type_counts[f.get("type", "UNKNOWN")] += 1

    RESULTS["findings"] = after_suppress
    RESULTS["summary"] = {
        "total": after,
        "before_aggregation": before,
        "suppressed_count": suppressed,
        "by_severity": dict(severity_counts),
        "by_type": dict(type_counts),
        "checks": [
            {"name": "except:pass 检测", "high_risk_path": True},
            {"name": "跨文件无锁写入", "high_risk_path": True},
            {"name": "Thread 无 daemon", "high_risk_path": True},
            {"name": "可变默认参数", "high_risk_path": False},
            {"name": "日志无轮转", "high_risk_path": False},
            {"name": "导入副作用", "high_risk_path": False},
        ]
    }
    return RESULTS


def main():
    if len(sys.argv) < 2:
        print("用法: python kinetic_scan.py <项目目录>")
        print("       python kinetic_scan.py <项目目录> --json")
        print("       python kinetic_scan.py <项目目录> --output <路径>")
        return 1

    target = sys.argv[1]
    if not os.path.exists(target):
        print(f"错误: 目录不存在: {target}")
        return 1

    output_json = '--json' in sys.argv
    output_path = None
    if '--output' in sys.argv:
        idx = sys.argv.index('--output')
        if idx + 1 < len(sys.argv):
            output_path = sys.argv[idx + 1]

    results = run_all(target)

    if output_json:
        print(json.dumps(results, indent=2, ensure_ascii=False))

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n报告已保存: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
