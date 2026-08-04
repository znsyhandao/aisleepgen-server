#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_all_runner.py - 全量测试运行器 v1.0

单命令运行所有测试脚本并生成汇总报告。
自动识别需要服务器的测试和离线测试。

用法:
  python dev_tools/test/test_all_runner.py
  python aisleepgen_tool.py test all

输出:
  - 控制台汇总
  - test_report_{timestamp}.json
"""

import os, sys, json, time, datetime, traceback, subprocess, multiprocessing.pool

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEST_DIR = os.path.join(BASE, 'dev_tools', 'test')
REPORT_DIR = os.path.join(BASE, 'data', 'test_reports')

PASS_TOTAL = 0
FAIL_TOTAL = 0
WARN_TOTAL = 0
ERROR_TOTAL = 0
TIMEOUT = 30  # seconds per test

# ===== Test Registry =====
# Tests that are meaningful to run (skip temp/deprecated)
# Categories: offline (no server needed), online (needs server), hybrid

TESTS = [
    # --- Offline tests (can run anytime) ---
    {"cmd": "pii_leak_test",       "file": "pii_leak_test.py",          "cat": "offline", "type": "安全合规"},
    {"cmd": "rx_block_test",       "file": "rx_block_test.py",          "cat": "offline", "type": "安全合规"},
    {"cmd": "anti_pseudoscience",  "file": "anti_pseudoscience.py",     "cat": "offline", "type": "安全合规"},
    {"cmd": "disclaimer_test",     "file": "disclaimer_test.py",        "cat": "offline", "type": "安全合规"},
    {"cmd": "clinical_safety_test","file": "clinical_safety_test.py",   "cat": "offline", "type": "安全合规"},
    {"cmd": "jailbreak_test",      "file": "jailbreak_test.py",         "cat": "offline", "type": "安全合规"},
    {"cmd": "hallucination_test",  "file": "hallucination_test.py",     "cat": "offline", "type": "临床验证"},
    {"cmd": "abnormal_input_test", "file": "abnormal_input_test.py",    "cat": "offline", "type": "鲁棒性"},
    {"cmd": "idempotency_test",    "file": "idempotency_test.py",       "cat": "offline", "type": "鲁棒性"},
    {"cmd": "multi_user_isolation_test", "file": "multi_user_isolation_test.py", "cat": "offline", "type": "鲁棒性"},
    {"cmd": "test_retest_test",    "file": "test_retest_test.py",       "cat": "offline", "type": "鲁棒性"},
    {"cmd": "isi_validation_test", "file": "isi_validation_test.py",    "cat": "offline", "type": "临床验证"},
    {"cmd": "phq_benchmark_test",  "file": "phq_benchmark_test.py",     "cat": "offline", "type": "临床验证"},
    {"cmd": "symptom_probing_test","file": "symptom_probing_test.py",   "cat": "offline", "type": "临床验证"},
    {"cmd": "referral_timing_test","file": "referral_timing_test.py",   "cat": "offline", "type": "临床验证"},

    # --- Online tests (need server) ---
    {"cmd": "comprehensive_test",  "file": "comprehensive_test.py",     "cat": "online", "type": "工程测试"},
    {"cmd": "smoke_test",          "file": "smoke_test.py",             "cat": "online", "type": "工程测试"},
    {"cmd": "quick_test",          "file": "quick_test.py",             "cat": "online", "type": "工程测试"},
    {"cmd": "full_serial_test",    "file": "full_serial_test.py",       "cat": "online", "type": "工程测试"},

    # --- Static analysis (always runs) ---
    {"cmd": "full_health_check",   "file": "check/full_health_check.py","cat": "static", "type": "静态检查"},
]

def server_running():
    """Check if server is running"""
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:8090/health", timeout=3)
        return True
    except:
        return False

def run_test(test_def):
    """Run a single test and return results"""
    start = time.time()
    result = {
        "name": test_def["cmd"],
        "file": test_def["file"],
        "type": test_def["type"],
        "category": test_def["cat"],
        "status": "SKIP",
        "pass": 0, "fail": 0, "warn": 0,
        "duration_ms": 0,
        "error": None
    }
    
    fpath = os.path.join(BASE, 'dev_tools', test_def["file"])
    if not os.path.exists(fpath):
        result["error"] = "file_not_found"
        return result
    
    # Check server requirement
    if test_def["cat"] == "online" and not server_running():
        result["status"] = "SKIP"
        result["error"] = "server_not_running"
        return result
    
    try:
        proc = subprocess.run(
            [sys.executable, fpath],
            capture_output=True, text=True,
            timeout=TIMEOUT,
            cwd=BASE
        )
        
        output = (proc.stdout + "\n" + proc.stderr)
        result["duration_ms"] = int((time.time() - start) * 1000)
        
        # Parse results from stdout
        import re
        p = len(re.findall(r'\[PASS\]', output))
        f = len(re.findall(r'\[FAIL\]', output))
        w = len(re.findall(r'\[WARN\]', output))
        
        result["pass"] = p
        result["fail"] = f
        result["warn"] = w
        
        if proc.returncode != 0:
            result["status"] = "FAIL" if f > 0 else "ERROR"
            if not result["error"]:
                result["error"] = f"exit_code={proc.returncode}"
        elif f > 0:
            result["status"] = "FAIL"
        elif p > 0 or w > 0:
            result["status"] = "PASS"
        else:
            result["status"] = "PASS"  # no news is good news
        
        # Truncate output for report
        result["output_summary"] = output[-500:] if len(output) > 500 else output
        
    except subprocess.TimeoutExpired:
        result["status"] = "TIMEOUT"
        result["error"] = f"exceeded {TIMEOUT}s"
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)[:200]
    
    return result

def generate_report(results, start_time):
    """Generate summary report"""
    categories = {}
    types = {}
    
    for r in results:
        cat = r["category"]
        tp = r["type"]
        if cat not in categories:
            categories[cat] = {"total": 0, "pass": 0, "fail": 0, "skip": 0, "error": 0}
        if tp not in types:
            types[tp] = {"total": 0, "pass": 0, "fail": 0, "skip": 0, "error": 0}
        
        categories[cat]["total"] += 1
        types[tp]["total"] += 1
        
        if r["status"] == "PASS": categories[cat]["pass"] += 1; types[tp]["pass"] += 1
        elif r["status"] == "FAIL": categories[cat]["fail"] += 1; types[tp]["fail"] += 1
        elif r["status"] == "SKIP": categories[cat]["skip"] += 1; types[tp]["skip"] += 1
        else: categories[cat]["error"] += 1; types[tp]["error"] += 1
    
    total_pass = sum(r["pass"] for r in results)
    total_fail = sum(r["fail"] for r in results)
    total_warn = sum(r["warn"] for r in results)
    duration = time.time() - start_time
    
    report = {
        "timestamp": datetime.datetime.now().isoformat(),
        "duration_s": round(duration, 1),
        "tests_run": len([r for r in results if r["status"] != "SKIP"]),
        "tests_skipped": len([r for r in results if r["status"] == "SKIP"]),
        "tests_failed": len([r for r in results if r["status"] == "FAIL"]),
        "tests_errored": len([r for r in results if r["status"] == "ERROR"]),
        "test_points_pass": total_pass,
        "test_points_fail": total_fail,
        "test_points_warn": total_warn,
        "by_category": categories,
        "by_type": types,
        "results": results,
    }
    
    return report

def print_summary(report):
    """Pretty print summary"""
    print("\n" + "=" * 65)
    print("  AISleepGen 全量测试报告")
    print(f"  时间: {report['timestamp']}")
    print(f"  用时: {report['duration_s']}s")
    print("=" * 65)
    
    # Overall
    ran = report['tests_run']
    skipped = report['tests_skipped']
    failed = report['tests_failed']
    errored = report['tests_errored']
    
    print(f"\n📊 总览: {ran} 运行, {skipped} 跳过, {failed} 失败, {errored} 错误")
    print(f"  测试点: ✅ {report['test_points_pass']}  ❌ {report['test_points_fail']}  ⚠️ {report['test_points_warn']}")
    
    # By type
    print(f"\n📋 按类型:")
    for tp, stats in sorted(report['by_type'].items()):
        icon = "✅" if stats['fail'] == 0 and stats['error'] == 0 else "❌"
        print(f"  {icon} {tp}: {stats['pass']}/{stats['total']} pass, {stats['fail']} fail, {stats['skip']} skip")
    
    # By category
    print(f"\n📁 按类别:")
    for cat, stats in sorted(report['by_category'].items()):
        icon = "✅" if stats['fail'] == 0 and stats['error'] == 0 else "❌"
        print(f"  {icon} {cat}: {stats['pass']}/{stats['total']} pass, {stats['fail']} fail")
    
    # Failed tests detail
    failures = [r for r in report['results'] if r['status'] in ['FAIL', 'ERROR', 'TIMEOUT']]
    if failures:
        print(f"\n🔴 失败详情:")
        for r in failures:
            print(f"  ❌ {r['name']} ({r['type']})")
            if r['error']:
                print(f"     {r['error']}")
    
    print(f"\n{'='*65}")

def main():
    global PASS_TOTAL, FAIL_TOTAL, WARN_TOTAL
    
    start_time = time.time()
    
    print(f"{'='*65}")
    print(f"  AISleepGen 全量测试运行器 v1.0")
    print(f"  测试数: {len(TESTS)}")
    print(f"  目录: {TEST_DIR}")
    print(f"{'='*65}")
    
    # Check server once
    server_up = server_running()
    print(f"  服务器状态: {'✅ 运行中' if server_up else '⏹️ 未启动（在线测试跳过）'}")
    print()
    
    # Run tests
    results = []
    for i, test_def in enumerate(TESTS):
        name = test_def["cmd"]
        print(f"  [{i+1}/{len(TESTS)}] {name}...", end=" ", flush=True)
        
        result = run_test(test_def)
        results.append(result)
        
        status_icon = {
            "PASS": "✅", "FAIL": "❌", "SKIP": "⏭️",
            "ERROR": "💥", "TIMEOUT": "⏰"
        }.get(result["status"], "❓")
        
        duration = result["duration_ms"]
        print(f"{status_icon} ({duration}ms)")
        
        if result["status"] == "FAIL":
            print(f"           fail={result['fail']} warn={result['warn']}")
    
    # Generate and print report
    report = generate_report(results, start_time)
    print_summary(report)
    
    # Save report
    os.makedirs(REPORT_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(REPORT_DIR, f"test_report_{ts}.json")
    with open(report_path, 'w', encoding='utf-8') as f:
        # Don't save full output in report file
        report_min = {k: v for k, v in report.items() if k != 'results'}
        report_min['results'] = [
            {k: v for k, v in r.items() if k != 'output_summary'}
            for r in report['results']
        ]
        json.dump(report_min, f, ensure_ascii=False, indent=2)
    print(f"  报告保存: {report_path}")
    
    return 1 if report['tests_failed'] > 0 or report['tests_errored'] > 0 else 0

if __name__ == "__main__":
    sys.exit(main())
