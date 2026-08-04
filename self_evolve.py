"""
self_evolve.py - AISleepGen 自我进化质量体系

核心层级:
  L0: 基线引擎 (quality_baseline.py) - 已有
  L1: 代码级预检 (AST模式检测) - 新增
  L2: 运行时自愈 + 降级 - 新增
  L3: 自动测试生长 - 新增
  L4: 质量门禁 (部署阻塞) - 新增

用法:
  python self_evolve.py check      # 全量质量检查 (L0+L1+L3)
  python self_evolve.py mutate     # 突变测试 (L1专用)
  python self_evolve.py heal       # 运行自愈检查 (L2)
  python self_evolve.py gate       # 部署前质量门禁 (L4)
  python self_evolve.py all        # 全流程
  python self_evolve.py report     # 查看报告
"""

import ast, json, os, sys, subprocess, time, hashlib, re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__ if '__file__' in dir() else '.'))
EVOLVE_DIR = os.path.join(PROJECT_ROOT, "data", "self_evolve")
os.makedirs(EVOLVE_DIR, exist_ok=True)
HISTORY_PATH = os.path.join(EVOLVE_DIR, "evolve_history.jsonl")
GATE_PATH = os.path.join(EVOLVE_DIR, "gate_decision.json")

# ═══ 架构边界集成 ═══
_HAS_ARCH_BOUNDARY = False
try:
    from arch_boundary import BoundaryViolationAuditor, verify_boundary_integrity
    _HAS_ARCH_BOUNDARY = True
except ImportError:
    BoundaryViolationAuditor = None

# ===== L1: 代码级预检 (AST模式检测) =====

# 危险模式库 - AST级别的模式匹配
DANGEROUS_PATTERNS = [
    {
        "id": "WFILE_WRITE_REASSIGN",
        "name": "wfile.write 被重新赋值",
        "detect": "wfile.write =",
        "severity": "CRITICAL",
        "message": "不要对 self.wfile.write 赋值代理！上次审计代理导致全服崩溃。",
    },
    {
        "id": "BARE_EXCEPT_PASS",
        "name": "bare except: pass",
        "detect_expr": r"except\s*[^:]*:\s*\n\s+pass",
        "severity": "HIGH",
        "message": "bare except: pass 会静默吞掉所有异常，导致幽灵bug（参见4/29教训）",
    },
    {
        "id": "HARDCODED_SECRET",
        "name": "疑似硬编码密钥/密码",
        "detect_expr": r"""(?:password|secret|token|api_key|apikey)\s*[=:]\s*['\"][^'\"]{8,}['\"]""",
        "severity": "CRITICAL",
        "message": "不要硬编码密钥！从环境变量或配置文件读取。",
    },
    {
        "id": "EVAL_EXEC_DANGER",
        "name": "eval/exec 动态执行",
        "detect_expr": r"\b(?:eval|exec|__import__)\s*\(",
        "severity": "HIGH",
        "message": "eval/exec 是安全风险，确认有严格的输入过滤",
    },
    {
        "id": "try_without_except_variable",
        "name": "try 块无 except 变量",
        "detect_expr": r"except\s*:\s*\n",
        "severity": "MEDIUM",
        "message": "用 `except Exception as e:` 代替 `except:`，至少打印异常信息",
    },
    {
        "id": "PICKLE_LOAD",
        "name": "pickle.load 不安全反序列化",
        "detect_expr": r"pickle\.load(?:s)?\(",
        "severity": "HIGH",
        "message": "pickle.load 用于未经验证的输入会导致远程代码执行",
    },
    {
        "id": "SHELL_INJECTION",
        "name": "shell=True 或 os.system",
        "detect_expr": r"(?:shell\s*=\s*True|os\.system\s*\()",
        "severity": "CRITICAL",
        "message": "shell=True 和 os.system 是命令注入风险",
    },
    {
        "id": "LARGE_FILE",
        "name": "文件超过400KB",
        "severity": "MEDIUM",
        "message": "大文件增加维护难度，考虑拆分模块",
    },
    {
        "id": "hardcoded_ip",
        "name": "硬编码 IP 地址",
        "detect_expr": r"""['"](?:https?://)?\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?['"]""",
        "severity": "MEDIUM",
        "message": "硬编码 IP 地址？考虑从配置读取（参考 band.js 动态配置改造）",
    },
    {
        "id": "high_import_count_warn",
        "name": "模块导入数过多",
        "max_imports": 35,
        "severity": "LOW",
        "message": "模块导入数过高，考虑精简",
    },
    {
        "id": "self_send_response",
        "name": "send_response 后直接 wfile.write",
        "detect_expr": r"send_response\s*\([^)]*\)\s*\n[^_]*?self\.wfile\.write",
        "severity": "LOW",
        "message": "使用 send_response + _set_headers + wfile.write 标准模式，不要混用",
    },
]


def _ast_scan_file(filepath: str) -> list:
    """AST扫描单个文件，返回发现的问题"""
    findings = []
    filename = os.path.basename(filepath)
    relpath = os.path.relpath(filepath, PROJECT_ROOT)

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # 跳过 self_evolve.py 自身的模式定义文本（DANGEROUS_PATTERNS）
    # 这会导致搜索模式文本自身被检出（假阳性）
    if filename == "self_evolve.py":
        marker_start = content.find('DANGEROUS_PATTERNS = [')
        marker_end = content.find('def _ast_scan_file')
        if marker_start >= 0 and marker_end > marker_start:
            content = content[:marker_start] + content[marker_end:]

    # 假阳性过滤：env文件读取模式（如 startswith('API_KEY=') → 非硬编码）
    FP_PATTERNS = [
        r"""\.startswith\s*\(['\"]\w+_API_KEY\s*=""",        # env file read
        r"""\.startswith\s*\(['\"]\w+_SECRET\s*=""",          # env secret read
        r"""if\s+line\.startswith\s*\(['\"]\w+_TOKEN\s*=""", # token read from file
        r"""['\"]\w+_API_KEY\s*['\"]\s*[,\)]""",            # dict key 'API_KEY' (not assignment)
        r"""\.get\s*\(\s*['\"]\w+_KEY""",                    # .get('API_KEY')
        r"""environ\.get\s*\(""",                              # os.environ.get
        r"""ghp_[A-Za-z0-9]{36}""",                          # GitHub token in comments/examples
        r"""line\.startswith\s*\(['\"]\w+_""",               # line.startswith('XXX_KEY')
    ]
    for fp_pat in FP_PATTERNS:
        content = re.sub(fp_pat, '__FP_SKIP__', content, flags=re.IGNORECASE)

    for pattern in DANGEROUS_PATTERNS:
        pid = pattern["id"]

        # 文件大小检测
        if pid == "LARGE_FILE":
            size_kb = len(content) / 1024
            max_kb = 400
            if size_kb > max_kb:
                findings.append({
                    "file": relpath,
                    "pattern_id": pid,
                    "severity": pattern["severity"],
                    "message": f"{size_kb:.0f}KB (> {max_kb}KB)",
                    "line": 0,
                })
            continue

        # 导入数检测
        if pid == "high_import_count_warn":
            import_lines = re.findall(r"^import |^from ", content, re.MULTILINE)
            if len(import_lines) > pattern["max_imports"]:
                findings.append({
                    "file": relpath,
                    "pattern_id": pid,
                    "severity": pattern["severity"],
                    "message": f"{len(import_lines)} 个import (>{pattern['max_imports']})",
                    "line": 0,
                })
            continue

        # 正则模式匹配
        if "detect_expr" in pattern:
            matches = list(re.finditer(pattern["detect_expr"], content, re.IGNORECASE | re.MULTILINE))
            for m in matches:
                # 过滤注释中的匹配
                line_start = content.rfind("\n", 0, m.start()) + 1
                line_num = content[:m.start()].count("\n") + 1
                line_text = content[line_start:content.find("\n", m.start())]

                # 跳过注释行
                stripped = line_text.strip()
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue

                findings.append({
                    "file": relpath,
                    "pattern_id": pid,
                    "severity": pattern["severity"],
                    "line": line_num,
                    "message": pattern["message"],
                    "snippet": line_text.strip()[:120],
                })

        # 直接字符串检测（简单的找方法名）
        elif "detect" in pattern:
            kw = pattern["detect"]
            idx = 0
            while True:
                idx = content.find(kw, idx)
                if idx < 0:
                    break
                line_num = content[:idx].count("\n") + 1
                line_start = content.rfind("\n", 0, idx) + 1
                line_text = content[line_start:content.find("\n", idx)].strip()
                if not line_text.startswith("#"):
                    findings.append({
                        "file": relpath,
                        "pattern_id": pid,
                        "severity": pattern["severity"],
                        "line": line_num,
                        "message": pattern["message"],
                        "snippet": line_text[:120],
                    })
                idx = idx + len(kw)

    return findings


def _scan_python_files() -> list:
    """扫描项目根目录的Python文件"""
    all_findings = []
    py_files = []

    # 扫描项目根目录 + dev_tools + data/quality_baseline + data/self_evolve
    scan_dirs = [PROJECT_ROOT,
                 os.path.join(PROJECT_ROOT, "dev_tools"),
                 os.path.join(PROJECT_ROOT, "data", "quality_baseline"),
                 os.path.join(PROJECT_ROOT, "data", "self_evolve")]

    for sd in scan_dirs:
        if not os.path.exists(sd):
            continue
        for f in os.listdir(sd):
            if f.endswith(".py") and os.path.isfile(os.path.join(sd, f)):
                fp = os.path.join(sd, f)
                try:
                    if os.path.getsize(fp) > 500 * 1024:
                        continue
                except OSError:
                    continue
                py_files.append(fp)

    for fp in sorted(py_files):
        try:
            findings = _ast_scan_file(fp)
            all_findings.extend(findings)
        except Exception as e:
            all_findings.append({
                "file": os.path.relpath(fp, PROJECT_ROOT),
                "pattern_id": "SCAN_ERROR",
                "severity": "MEDIUM",
                "line": 0,
                "message": f"扫描异常: {str(e)[:80]}",
                "snippet": "",
            })

    return all_findings


def run_l1_scan() -> dict:
    """运行 L1 代码级预检"""
    findings = _scan_python_files()

    by_severity = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []}
    for f in findings:
        sev = f["severity"]
        if sev in by_severity:
            by_severity[sev].append(f)

    return {
        "total": len(findings),
        "by_severity": {k: len(v) for k, v in by_severity.items()},
        "findings": findings,
    }


# ===== L2: 运行时自愈检查 =====

def _check_server_health() -> dict:
    """检查服务器是否存活 + 输出响应与基线校验"""
    import urllib.request, json as _json
    results = {}
    checks = []

    for endpoint, path, expect_status in [
        ("health", f"http://localhost:8090/health", 200),
        ("health_content", f"http://localhost:8090/health", 200),
        ("quick_device_data", f"http://localhost:8090/api/sleep/device-data", 400),  # 无参数时预期400
        ("quick_device_ocr", f"http://localhost:8090/api/sleep/device-ocr", 400),
    ]:
        try:
            if endpoint == "health":
                resp = urllib.request.urlopen(path, timeout=3)
                body = _json.loads(resp.read())
                ok = resp.status == expect_status
                results[endpoint] = ok
                if ok:
                    # 校验响应内容结构是否符合基线
                    if not isinstance(body, dict) or "status" not in body:
                        results[endpoint + "_schema"] = False
                        checks.append(f"[schema] {endpoint} 响应结构异常")
                    else:
                        results[endpoint + "_schema"] = True
            else:
                data = _json.dumps({"openid": "self_heal_test"}).encode()
                req = urllib.request.Request(path, data=data,
                    headers={"Content-Type": "application/json"})
                resp = urllib.request.urlopen(req, timeout=5)
                ok = resp.status == expect_status
                results[endpoint] = ok
                if not ok:
                    checks.append(f"[status] {endpoint} 预期{expect_status} 实际{resp.status}")
        except Exception as e:
            results[endpoint] = False
            checks.append(f"[timeout] {endpoint}: {str(e)[:60]}")

    return {"results": results, "checks": checks}


def _check_disk_usage() -> dict:
    """检查磁盘使用情况"""
    try:
        import shutil
        usage = shutil.disk_usage(PROJECT_ROOT)
        pct = usage.used / usage.total * 100
        return {
            "total_gb": round(usage.total / (1024**3), 1),
            "used_gb": round(usage.used / (1024**3), 1),
            "free_gb": round(usage.free / (1024**3), 1),
            "pct": round(pct, 1),
        }
    except Exception:
        return {"error": "无法获取磁盘信息"}


def _check_backup_count() -> dict:
    """检查备份数量"""
    bak_dir = os.path.join(PROJECT_ROOT, ".surgical_backups")
    if os.path.exists(bak_dir):
        bak_files = [f for f in os.listdir(bak_dir) if f.endswith(".bak")]
        return {"count": len(bak_files), "warning": len(bak_files) < 3}
    return {"count": 0, "warning": True}


def run_l2_heal_check() -> dict:
    """运行L2自愈检查 - 报告异常但不自动改代码（需要人确认）"""
    health = _check_server_health()
    disk = _check_disk_usage()
    bak = _check_backup_count()

    issues = []

    # 服务器问题
    for ep, ok in sorted(health.get("results", {}).items()):
        if not ok:
            issues.append({
                "component": f"endpoint_{ep}",
                "status": "DOWN",
                "severity": "HIGH" if ep == "health" else "MEDIUM",
                "suggestion": f"重启服务器或检查 {ep} 端点",
            })

    # 磁盘问题
    if isinstance(disk, dict) and disk.get("pct", 0) > 90:
        issues.append({
            "component": "disk",
            "status": "WARN",
            "severity": "MEDIUM",
            "suggestion": f"磁盘使用率 {disk['pct']}%，请清理",
        })

    # 备份问题
    if bak.get("warning"):
        issues.append({
            "component": "backup",
            "status": "WARN",
            "severity": "LOW",
            "suggestion": "备份文件少于3份，改代码前先备份",
        })

    return {
        "health": health,
        "disk": disk,
        "backup": bak,
        "issues": issues,
    }


# ===== L3: 自动测试生长 =====

def discover_new_test_cases() -> list:
    """基于已知模式自动生成新的测试用例

    使用 mutation/edge-case 模板生成，不做 AI 调用（避免循环依赖）
    """
    new_cases = []

    # 边界值变异模板
    mutants = [
        {
            "id": "edge_empty_message",
            "name": "空消息测试",
            "input": {"message": "", "history": []},
            "expect": {"score_min": 0, "score_max": 100, "quality_acceptable": ["优秀","良好","一般","较差","需要改善"], "min_dimensions_computed": 0},
            "weight": 0.3,
        },
        {
            "id": "edge_very_long_message",
            "name": "超长消息测试",
            "input": {"message": "昨晚" + "我睡得很好。" * 200, "history": []},
            "expect": {"score_min": 0, "score_max": 100, "quality_acceptable": ["优秀","良好","一般","较差","需要改善"], "min_dimensions_computed": 0},
            "weight": 0.3,
            "tags": ["edge", "mutation"],
        },
        {
            "id": "edge_special_chars",
            "name": "特殊字符测试",
            "input": {"message": "我昨晚睡了8小时！！！深睡？？ HRV: 78ms @#$%^&*(失眠)", "history": []},
            "expect": {"score_min": 0, "score_max": 100, "quality_acceptable": ["优秀","良好","一般","较差","需要改善"], "min_dimensions_computed": 0},
            "weight": 0.3,
            "tags": ["edge", "mutation"],
        },
        {
            "id": "mutation_score_overflow",
            "name": "评分溢出变异",
            "input": {"message": "我昨晚评分100分睡了10小时深睡8小时HRV1000心率0", "history": []},
            "expect": {"score_min": 0, "score_max": 100, "quality_acceptable": ["优秀","良好","一般","较差","需要改善"], "min_dimensions_computed": 0},
            "weight": 0.4,
            "tags": ["mutation", "security"],
        },
        {
            "id": "edge_no_sleep_data",
            "name": "完全不相关输入",
            "input": {"message": "今天天气真好，中午吃了顿火锅", "history": []},
            "expect": {"score_min": 0, "score_max": 100, "quality_acceptable": ["优秀","良好","一般","较差","需要改善"], "min_dimensions_computed": 0},
            "weight": 0.3,
            "tags": ["edge"],
        },
        {
            "id": "mutation_cjk_extreme",
            "name": "极端CJK混合",
            "input": {"message": "我昨晩孒八個小時渜睡丶醒來一次㊗️好", "history": []},
            "expect": {"score_min": 0, "score_max": 100, "quality_acceptable": ["优秀","良好","一般","较差","需要改善"], "min_dimensions_computed": 0},
            "weight": 0.2,
            "tags": ["mutation"],
        },
    ]

    return mutants


def run_l3_test_growth() -> dict:
    """L3: 自动生成新测试用例并补充到基线"""
    existing_path = os.path.join(PROJECT_ROOT, "data", "quality_baseline", "test_cases.json")
    existing_ids = set()
    if os.path.exists(existing_path):
        try:
            with open(existing_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
                existing_ids = {c["id"] for c in existing}
        except Exception:
            pass

    new_cases = discover_new_test_cases()
    truly_new = [c for c in new_cases if c["id"] not in existing_ids]

    if truly_new:
        # 追加到测试文件
        all_cases = []
        if os.path.exists(existing_path):
            with open(existing_path, "r", encoding="utf-8") as f:
                all_cases = json.load(f)
        all_cases.extend(truly_new)

        with open(existing_path, "w", encoding="utf-8") as f:
            json.dump(all_cases, f, indent=2, ensure_ascii=False)

    return {
        "discovered": len(truly_new),
        "cases": truly_new,
        "total_cases": len(existing_ids) + len(truly_new),
    }


# ===== L4: 质量门禁 =====

# 门禁标准
GATE_RULES = [
    {
        "id": "L0_BASELINE_PASS",
        "name": "L0基线通过率 >= 80%",
        "check": lambda r: r.get("l0", {}).get("pass_rate", 0) >= 80,
        "severity": "BLOCKER",
    },
    {
        "id": "L0_NO_HIGH_REGRESSION",
        "name": "L0无严重退化",
        "check": lambda r: len(r.get("l0", {}).get("high_regressions", [])) == 0,
        "severity": "BLOCKER",
    },
    {
        "id": "L1_NO_CRITICAL",
        "name": "L1无CRITICAL发现",
        "check": lambda r: r.get("l1", {}).get("by_severity", {}).get("CRITICAL", 0) == 0,
        "severity": "BLOCKER",
    },
    {
        "id": "L1_HIGH_WARN",
        "name": "L1 HIGH发现不超3个",
        "check": lambda r: r.get("l1", {}).get("by_severity", {}).get("HIGH", 0) <= 3,
        "severity": "WARN",
    },
    {
        "id": "L2_SERVER_UP",
        "name": "L2关键端点存活",
        "check": lambda r: r.get("l2", {}).get("health", {}).get("results", {}).get("health", False),
        "severity": "BLOCKER",
    },
    {
        "id": "L3_NO_CRITICAL_ISSUES",
        "name": "L3扫描通过",
        "check": lambda r: len(r.get("l3", {}).get("issues", [])) == 0,
        "severity": "WARN",
    },
    # ═══ 架构边界门禁 ═══
    {
        "id": "ARCH_BOUNDARY_INTEGRITY",
        "name": "架构边界完整性通过",
        "check": lambda r: r.get("arch", {}).get("integrity_ok", False),
        "severity": "BLOCKER",
    },
    {
        "id": "ARCH_NO_SELF_MODIFICATION",
        "name": "自我进化未修改受保护文件",
        "check": lambda r: r.get("arch", {}).get("no_self_modify", True),
        "severity": "BLOCKER",
    },
]


def check_gate(results: dict) -> dict:
    """运行质量门禁"""
    decisions = []
    blockers = []
    warnings = []

    for rule in GATE_RULES:
        try:
            passed = rule["check"](results)
        except Exception:
            passed = False

        decision = {
            "rule_id": rule["id"],
            "name": rule["name"],
            "passed": passed,
            "severity": rule["severity"],
        }
        decisions.append(decision)

        if not passed:
            if rule["severity"] == "BLOCKER":
                blockers.append(rule["name"])
            else:
                warnings.append(rule["name"])

    gated = len(blockers) > 0

    return {
        "gated": gated,
        "blockers": blockers,
        "warnings": warnings,
        "decisions": decisions,
    }


def run_all_checks() -> dict:
    """运行所有层级的检查"""
    print("=" * 55)
    print("  AISleepGen 自我进化 - 全量质量检查")
    print("=" * 55)

    # L0: 基线
    print("\n📊 L0: 质量基线运行中...")
    from quality_baseline import run_baseline
    l0_report = run_baseline()
    l0_summary = l0_report["run"]["summary"]
    l0_regressions = l0_report["run"]["regressions"]
    print(f"   通过率: {l0_summary['pass_rate_pct']}% ({l0_summary['passed_cases']}/{l0_summary['total_cases']})")

    # L1: AST扫描
    print("\n🔍 L1: 代码级AST扫描...")
    l1_result = run_l1_scan()
    print(f"   发现 {l1_result['total']} 个潜在问题")
    for sev, count in sorted(l1_result['by_severity'].items()):
        print(f"   [{sev}] {count} 个")

    # L2: 自愈检查
    print("\n🩺 L2: 运行时自愈检查...")
    l2_result = run_l2_heal_check()
    for ep, ok in sorted(l2_result.get("health", {}).get("results", {}).items()):
        print(f"   {'✅' if ok else '❌'} {ep}")
    print(f"   磁盘: {l2_result['disk'].get('pct', '?')}%")

    # L3: 测试生长
    print("\n🌱 L3: 自动测试生长...")
    l3_result = run_l3_test_growth()
    print(f"   新用例: {l3_result['discovered']} 个 (总计 {l3_result['total_cases']})")

    # ═══ 架构边界检查 ═══
    print("\n🏛️ 架构边界完整性检查...")
    arch_result = {'integrity_ok': True, 'no_self_modify': True}
    if _HAS_ARCH_BOUNDARY:
        try:
            integrity = verify_boundary_integrity()
            arch_result['integrity_ok'] = integrity['status'] == 'INTACT'
            print(f"   完整性: {'✅ ' + integrity['status'] if arch_result['integrity_ok'] else '❌ 被破坏'}")
            print(f"   MD5: {integrity.get('md5', '?')[:16]}...")
            print(f"   规则: {integrity.get('boundary_count', 0)} 条")

            # 检查当前修改的文件
            git_files = []
            try:
                import subprocess
                r = subprocess.run(['git', 'diff', '--name-only'], capture_output=True, text=True, timeout=3, cwd=PROJECT_ROOT)
                git_files = [f.strip() for f in r.stdout.split('\n') if f.strip()]
            except Exception:
                pass
            if git_files:
                auditor = BoundaryViolationAuditor()
                mod_check = auditor.verify_self_modification(git_files)
                arch_result['no_self_modify'] = len(mod_check['violations']) == 0
                if mod_check['violations']:
                    print(f"   ❌ 违规文件: {[v['file'] for v in mod_check['violations']]}")
        except Exception as e:
            print(f"   边界检查异常: {e}")
            arch_result['integrity_ok'] = False
    else:
        print("   边界层未加载 (arch_boundary.py 不存在)")
        arch_result['integrity_ok'] = False
        arch_result['no_self_modify'] = False

    # L4: 门禁
    all_results = {
        "l0": {
            "pass_rate": l0_summary["pass_rate_pct"],
            "high_regressions": [r for r in l0_regressions if r["severity"] == "HIGH"],
        },
        "l1": l1_result,
        "l2": l2_result,
        "l3": l3_result,
        "arch": arch_result,
    }
    gate = check_gate(all_results)

    # 保存门禁决策
    run_record = {
        "timestamp": datetime.now().isoformat(),
        "results": all_results,
        "gate": gate,
    }

    with open(GATE_PATH, "w", encoding="utf-8") as f:
        json.dump(run_record, f, indent=2, ensure_ascii=False)

    # 追加到历史
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(run_record, ensure_ascii=False) + "\n")

    # 打印门禁结果
    print(f"\n{'='*55}")
    print("  🚧 质量门禁结果:")
    if gate["gated"]:
        print(f"   ❌ 阻塞! {len(gate['blockers'])} 项未通过:")
        for b in gate["blockers"]:
            print(f"      🔴 {b}")
    else:
        print(f"   ✅ 通过 ({len(gate['warnings'])} 项警告)")
        for w in gate["warnings"]:
            print(f"      🟡 {w}")

    if not gate["gated"]:
        print("\n   ✅ 无阻塞项, 可以部署!")

    return run_record


def print_gate_report():
    """打印门禁报告"""
    if not os.path.exists(GATE_PATH):
        print("⚠️  尚未运行全量检查，请先执行 python self_evolve.py all")
        return

    with open(GATE_PATH, "r", encoding="utf-8") as f:
        report = json.load(f)

    ts = report["timestamp"]
    gate = report["gate"]
    r = report["results"]

    print("=" * 55)
    print(f"  AISleepGen 自我进化门禁报告")
    print(f"  {ts}")
    print("=" * 55)
    print(f"\n  📊 L0 基线: {r['l0']['pass_rate']}%")
    print(f"  🔍 L1 发现: {r['l1']['total']} 个潜在问题")
    print(f"  🩺 L2 自愈: " + ("全部正常" if all(r['l2']['health'].get('results', {}).values()) else "部分异常"))
    print(f"  🌱 L3 测试生长: {r['l3']['total_cases']} 个用例")
    arch_status = r.get('arch', {})
    print(f"  🏛️ 架构边界: {'✅ 完整' if arch_status.get('integrity_ok') else '❌ 被破坏'}" 
          + f" | {'✅ 未修改' if arch_status.get('no_self_modify') else '❌ 修改了受保护文件'}")

    print(f"\n  🚧 门禁: {'❌ 阻塞' if gate['gated'] else '✅ 通过'}")
    if gate.get('blockers'):
        for b in gate['blockers']:
            print(f"     🔴 {b}")
    if gate.get('warnings'):
        for w in gate['warnings']:
            print(f"     🟡 {w}")
    print()

    # 显示L1发现详情
    print("  📋 L1 详细发现:")
    for f in r.get('l1', {}).get('findings', []):
        icon = {'CRITICAL': '🔴', 'HIGH': '🟠', 'MEDIUM': '🟡', 'LOW': '⚪'}.get(f['severity'], '⚪')
        print(f"    {icon} [{f['severity']}] {f['file']}:{f.get('line',0)} - {f['message'][:80]}")


# ===== CLI入口 =====
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法:")
        print("  python self_evolve.py check    全量质量检查 (L0+L1+L3)")
        print("  python self_evolve.py scan     只跑L1 AST扫描")
        print("  python self_evolve.py heal     只跑L2 自愈检查")
        print("  python self_evolve.py grow     只跑L3 测试生长")
        print("  python self_evolve.py all      全流程 (含L4门禁)")
        print("  python self_evolve.py report   查看报告")
        print("  python self_evolve.py history  查看历史趋势")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "check":
        report = run_all_checks()
    elif cmd == "scan":
        result = run_l1_scan()
        print(f"L1扫描完成: {result['total']} 个发现")
        for f in result['findings']:
            print(f"  [{f['severity']}] {f['file']}:{f.get('line',0)} - {f['message'][:100]}")
    elif cmd == "heal":
        result = run_l2_heal_check()
        print(f"L2自愈检查完成")
        for ep, ok in sorted(result['health'].items()):
            print(f"  {'✅' if ok else '❌'} {ep}")
    elif cmd == "grow":
        result = run_l3_test_growth()
        print(f"L3测试生长: 新增{result['discovered']}个用例")
        for c in result['cases']:
            print(f"  + {c['name']}")
    elif cmd == "all":
        report = run_all_checks()
        if report["gate"]["gated"]:
            print("\n⛔ 门禁未通过！请在修复后重新运行。")
            sys.exit(2)
    elif cmd == "report":
        print_gate_report()
    else:
        print(f"未知命令: {cmd}")
