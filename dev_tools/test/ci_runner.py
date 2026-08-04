#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ci_runner.py - 持续集成运行器 v1.0

自动运行全部测试，生成报告，记录历史趋势。
可作为cron任务每天运行。

流程：
1. 运行 test all（全量测试）
2. 运行 check health（静态检查）
3. 运行 audit kinetic（突变动力学）
4. 对比上次结果，检测退化
5. 生成趋势报告

用法:
  python dev_tools/test/ci_runner.py [--notify] [--email]
  python aisleepgen_tool.py test ci
"""

import os, sys, json, subprocess, time, datetime
sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REPORT_DIR = os.path.join(BASE, "data", "test_reports")
HISTORY_FILE = os.path.join(REPORT_DIR, "ci_history.json")

PASS = 0
FAIL = 0
WARN = 0

def report(result, label, detail=''):
    global PASS, FAIL, WARN
    if result == 'PASS': PASS += 1; print(f"  [PASS] {label}")
    elif result == 'FAIL': FAIL += 1; print(f"  [FAIL] {label}: {detail}")
    elif result == 'WARN': WARN += 1; print(f"  [WARN] {label}: {detail}")

def run_subprocess(cmd, timeout=120):
    """Run a subprocess and return output"""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=BASE
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout[-1000:] if len(proc.stdout) > 1000 else proc.stdout,
            "stderr": proc.stderr[-500:] if len(proc.stderr) > 500 else proc.stderr,
            "success": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "TIMEOUT", "success": False}
    except FileNotFoundError:
        return {"returncode": -2, "stdout": "", "stderr": "FILE_NOT_FOUND", "success": False}

def load_history():
    """Load CI history"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"runs": []}
    return {"runs": []}

def save_history(history):
    """Save CI history"""
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def run_stage(name, cmd, stage_type):
    """Run a CI stage"""
    print(f"\n{'='*60}")
    print(f"  STAGE: {name}")
    print(f"{'='*60}")
    
    start = time.time()
    result = run_subprocess(cmd)
    duration = time.time() - start
    
    stage_result = {
        "name": name,
        "type": stage_type,
        "duration_s": round(duration, 1),
        "success": result["success"],
        "timestamp": datetime.datetime.now().isoformat(),
    }
    
    if result["success"]:
        report('PASS', f"{name} 通过 ({duration:.1f}s)")
    else:
        report('FAIL' if stage_type != "optional" else 'WARN', 
               f"{name} 未完全通过 ({duration:.1f}s)")
        if result["stderr"]:
            print(f"  stderr: {result['stderr'][:300]}")
    
    return stage_result

def check_regression(history, current):
    """检查相比于上次运行是否有退化"""
    print("\n=== 退化检测 ===")
    
    if not history["runs"]:
        report('INFO', "首次运行，无历史对比基线")
        return
    
    last_run = history["runs"][-1]
    
    # Compare passed stages
    current_passed = sum(1 for s in current["stages"] if s["success"])
    last_passed = sum(1 for s in last_run.get("stages", []) if s.get("success"))
    
    if current_passed < last_passed:
        # Check which stages regressed
        current_stages = {s["name"]: s for s in current["stages"]}
        last_stages = {s["name"]: s for s in last_run.get("stages", [])}
        
        regressed = []
        for name, ls in last_stages.items():
            cs = current_stages.get(name)
            if cs and ls.get("success") and not cs.get("success"):
                regressed.append(name)
        
        if regressed:
            report('FAIL', f"检测到{len(regressed)}个退化: {', '.join(regressed)}")
            return False
        else:
            report('WARN', "部分阶段失败（非退化，可能是首次运行）")
    else:
        report('PASS', f"与上次相比无退化（{current_passed}/{last_passed} passed）")
    
    return True

def generate_trend_report(history):
    """生成趋势报告"""
    print("\n=== 趋势分析 ===")
    
    runs = history.get("runs", [])
    if len(runs) < 2:
        report('INFO', "需要至少2次运行记录才能生成趋势")
        return
    
    # Show last 7 runs
    recent = runs[-7:] if len(runs) > 7 else runs
    
    print(f"\n  最近{len(recent)}次运行趋势:")
    print(f"  {'日期':<14} {'通过率':<10} {'持续时间':<10}")
    for r in recent:
        stages = r.get("stages", [])
        passed = sum(1 for s in stages if s.get("success"))
        total = len(stages)
        date = r.get("timestamp", "?")[:10]
        duration = r.get("total_duration_s", 0)
        rate = f"{passed}/{total}"
        
        # If degraded, mark
        marker = " ⚠️" if passed < total else " ✅"
        print(f"  {date:<14} {rate:<10} {duration}s{marker}")

def main():
    print(f"{'='*60}")
    print(f"  AISleepGen CI持续集成运行器 v1.0")
    print(f"  {datetime.datetime.now().isoformat()}")
    print(f"{'='*60}")
    
    total_start = time.time()
    history = load_history()
    current_run = {
        "timestamp": datetime.datetime.now().isoformat(),
        "stages": [],
    }
    
    # Stage 1: Health Check (static)
    s1 = run_stage("健康检查", 
                   [sys.executable, "-B", os.path.join(BASE, "aisleepgen_tool.py"), "check", "health"],
                   "static")
    current_run["stages"].append(s1)
    
    # Stage 2: Kinetic Scan
    s2 = run_stage("突变动力学扫描",
                   [sys.executable, "-B", os.path.join(BASE, "aisleepgen_tool.py"), "check", "kinetic", BASE],
                   "static")
    current_run["stages"].append(s2)
    
    # Stage 3: Offline Tests
    s3 = run_stage("离线测试",
                   [sys.executable, "-B", os.path.join(BASE, "aisleepgen_tool.py"), "test", "all"],
                   "test")
    current_run["stages"].append(s3)
    
    # Stage 4: Compile Check (all .py files)
    s4 = run_stage("全量编译检查",
                   [sys.executable, "-c", 
                    "import os, py_compile; base=r'{}'; ok=0; fail=0; ".format(BASE.replace('\\', '/')) +
                    "for root,dirs,files in os.walk(base): " +
                    "  for f in files: " +
                    "    if f.endswith('.py'): " +
                    "      try: py_compile.compile(os.path.join(root,f), doraise=True); ok+=1 " +
                    "      except: fail+=1; print(f'  FAIL: {f}') " +
                    "print(f'OK: {ok}, FAIL: {fail}')"],
                   "static")
    current_run["stages"].append(s4)
    
    total_duration = time.time() - total_start
    current_run["total_duration_s"] = round(total_duration, 1)
    
    # Regression check
    regression_ok = check_regression(history, current_run)
    
    # Trend
    generate_trend_report(history)
    
    # Save history
    history["runs"].append(current_run)
    # Keep max 30 runs
    if len(history["runs"]) > 30:
        history["runs"] = history["runs"][-30:]
    save_history(history)
    
    # Summary
    stages_passed = sum(1 for s in current_run["stages"] if s["success"])
    stages_total = len(current_run["stages"])
    
    print(f"\n{'='*60}")
    print(f"  CI运行完成")
    print(f"  总耗时: {total_duration:.1f}s")
    print(f"  阶段: {stages_passed}/{stages_total} 通过")
    print(f"  历史记录: {len(history['runs'])}次")
    if regression_ok is False:
        print(f"  ⚠️  检测到退化！")
    print(f"{'='*60}")
    
    return 0 if stages_passed == stages_total else 1

if __name__ == "__main__":
    sys.exit(main())
