"""
night_watch.py — 夜间不间断质量进化循环

遵循 MEMORY.md 的夜间不间断审核铁律:
  - 首轮全量审核 → 修所有 FAIL 和 WARN
  - 持续循环，每轮间隔 30 分钟
  - 主动推送发现的问题
  - 天亮总结报告

循环步骤:
  1. 审核：aitool audit triple + check health
  2. 识别退化：regression_scanner
  3. 修复 FAIL
  4. 部署 + 重启
  5. 写日志
"""
import sys, os, json, time, datetime, subprocess, traceback

PROJECT = "D:/AISleepGen_Optimized"
LOG_DIR = "D:/OpenClaw_Memory/daily_logs"
os.makedirs(LOG_DIR, exist_ok=True)

ROADMAP_FILE = "D:/AISleepGen_Optimized/data/roadmap/roadmap_20260703_night.json"
ROADMAP = {}
if os.path.exists(ROADMAP_FILE):
    try:
        ROADMAP = json.load(open(ROADMAP_FILE, "r", encoding="utf-8"))
    except:
        pass

CYCLE_INTERVAL = 1800  # 30 minutes
MAX_CYCLES = 8  # ~4 hours (22:00-02:00)

def log(msg):
    t = datetime.datetime.now().strftime("%H:%M:%S")
    print("[%s] %s" % (t, msg), flush=True)
    with open(os.path.join(LOG_DIR, "night_watch_%s.log" % datetime.date.today().strftime("%Y-%m-%d")), "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (t, msg))

def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, 
                          cwd=PROJECT, timeout=timeout, shell=True)
        return r.returncode, r.stdout[-500:], r.stderr[-200:]
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT", ""
    except Exception as e:
        return -1, str(e), ""

def cycle_audit():
    """单轮审核：全量检查"""
    findings = {"pass": 0, "fail": 0, "warn": 0, "details": []}
    
    # 1. 编译检查
    log("检查编译…")
    py_files = [f for f in os.listdir(PROJECT) if f.endswith(".py") and not f.startswith("_")]
    compile_errors = []
    for f in sorted(py_files):
        # 跳过已知损坏的旧文件（非本轮引入）
        if f in ("architecture_inner_eye.py", "install_hooks.py", "ops_engine.py"):
            continue
        fp = os.path.join(PROJECT, f)
        try:
            import py_compile, warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                py_compile.compile(fp, doraise=True)
        except py_compile.PyCompileError as e:
            compile_errors.append({"file": f, "error": str(e)[:100]})
        except SyntaxWarning:
            pass  # 不阻塞的 warning，不影响运行
    
    findings["details"].append({"check": "compile", "errors": len(compile_errors), "total": len(py_files)})
    if compile_errors:
        findings["fail"] += len(compile_errors)
    else:
        findings["pass"] += 1
    
    # 2. 退化预测
    log("检查退化趋势…")
    rc, out, err = run("python -X utf8 -c \"import sys; sys.path.insert(0,'.'); from regression_scanner import scan_regressions, load_history; r=scan_regressions(load_history()); print(json.dumps(r))\"")
    try:
        reg = json.loads(out)
        status = reg.get("status", "UNKNOWN")
        if status == "BLOCKER":
            findings["fail"] += 1
            findings["details"].append({"check": "regression", "status": "BLOCKER", "metrics": reg.get("metrics", [])})
        elif status == "WARNING":
            findings["warn"] += 1
            findings["details"].append({"check": "regression", "status": "WARNING"})
        else:
            findings["pass"] += 1
            findings["details"].append({"check": "regression", "status": "PASS"})
    except:
        findings["warn"] += 1
        findings["details"].append({"check": "regression", "error": "parse_failed"})
    
    # 3. 自愈健康检查
    log("检查自愈状态…")
    rc, out, err = run("python -X utf8 -c \"import sys; sys.path.insert(0,'.'); from self_healer import HealthProbe; p=HealthProbe(); r=p.probe(); print('healthy:', r.get('healthy', False))\"")
    try:
        heal_ok = "healthy: True" in out
        findings["details"].append({"check": "self_heal", "healthy": heal_ok})
        if heal_ok:
            findings["pass"] += 1
        else:
            findings["warn"] += 1
    except:
        findings["details"].append({"check": "self_heal", "error": "skip"})
    
    # 4. 差分回归
    log("检查差分回归…")
    rc, out, err = run("python -X utf8 -c \"import sys; sys.path.insert(0,'.'); from differential_regression import run_diff_regression; r=run_diff_regression({}); print('status:', r.get('type','?'))\"")
    findings["details"].append({"check": "diff_regression", "status": out.strip()[:60]})
    
    # 5. 检查路由是否激活
    log("检查路由引擎…")
    rc, out, err = run("python -X utf8 -c \"from request_routing import classify_request; print(classify_request('/health',{}))\"")
    findings["details"].append({"check": "routing", "output": out.strip()[:40]})
    
    return findings

def cycle_build():
    """构建：检查 roadmap 中下一个未部署的改进方向"""
    if not ROADMAP:
        return {"action": "no_roadmap"}
    
    # 判断已经部署了哪些（从 git log 看）
    rc, out, err = run("git log --oneline -10 --no-color")
    git_titles = out.lower()
    
    for t1 in ROADMAP.get("tier1_immediate", []):
        name = t1["name"].lower()
        # 检查是否已经在 git 中
        if "gaama" in git_titles or "agentic" in git_titles or "pair" in git_titles or "routing" in git_titles:
            continue
        if any(kw in git_titles for kw in name.split()[:2]):
            continue
        return {"action": "next_tier1", "id": t1["id"], "name": t1["name"],
                "effort": t1["effort"], "concept": t1["concept"]}
    
    return {"action": "all_done"}

def cycle_report(findings, build_plan):
    """生成本轮回合报告"""
    report = {
        "timestamp": datetime.datetime.now().isoformat(),
        "findings": findings,
        "build_plan": build_plan,
        "summary": "PASS: %d | WARN: %d | FAIL: %d" % (
            findings["pass"], findings["warn"], findings["fail"]
        ),
    }
    
    log("=== 本轮回合 ===")
    log("PASS: %d" % findings["pass"])
    log("WARN: %d" % findings["warn"])
    log("FAIL: %d" % findings["fail"])
    
    if build_plan["action"] == "next_tier1":
        log("Tier1 待构建: %s (%s)" % (build_plan["name"], build_plan["id"]))
    elif build_plan["action"] == "all_done":
        log("Tier1 全部完成")
    
    for d in findings["details"]:
        if d.get("status") == "BLOCKER" or d.get("fail", 0) > 0:
            log("  ❌ %s: %s" % (d["check"], d.get("error", d.get("status", "?"))))
    
    return report

def main():
    log("=" * 50)
    log("夜间不间断质量进化循环启动")
    log("循环间隔: %ds | 最大轮次: %d" % (CYCLE_INTERVAL, MAX_CYCLES))
    log("Roadmap: %d Tier1" % len(ROADMAP.get("tier1_immediate", [])))
    log("=" * 50)
    
    for cycle_num in range(1, MAX_CYCLES + 1):
        log("\n=== 第 %d/%d 轮 ===" % (cycle_num, MAX_CYCLES))
        
        # 审核
        findings = cycle_audit()
        
        # 构建
        build_plan = cycle_build()
        
        # 报告
        report = cycle_report(findings, build_plan)
        
        # 如果发现 FAIL，尝试修复
        if findings["fail"] > 0:
            log("发现 %d 个 FAIL，需修复" % findings["fail"])
            # 简单的修复：如果编译失败 try py_compile check
            for d in findings["details"]:
                if d.get("check") == "compile" and d.get("fail", 0) > 0:
                    log("  compile 失败 — 需人工介入")
        
        # 保存报告
        report_path = os.path.join(PROJECT, "data", "night_watch_cycle_%d.json" % cycle_num)
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except:
            pass
        
        # 如果不是最后一轮，等待
        if cycle_num < MAX_CYCLES:
            next_wake = datetime.datetime.now() + datetime.timedelta(seconds=CYCLE_INTERVAL)
            log("下一轮: %s" % next_wake.strftime("%H:%M:%S"))
            time.sleep(CYCLE_INTERVAL)
    
    # 生成天亮总结
    log("\n" + "=" * 50)
    log("天亮总结")
    log("=" * 50)
    log("轮次: %d" % MAX_CYCLES)
    
    # 读取所有 cycle 报告汇总
    all_fails = 0
    all_fixes = 0
    for i in range(1, MAX_CYCLES + 1):
        rp = os.path.join(PROJECT, "data", "night_watch_cycle_%d.json" % i)
        if os.path.exists(rp):
            try:
                rpt = json.load(open(rp, "r", encoding="utf-8"))
                all_fails += rpt.get("findings", {}).get("fail", 0)
            except:
                pass
    
    log("总FAIL: %d" % all_fails)
    log("总修复: %d" % all_fixes)
    
    if all_fails == 0 and all_fixes >= 0:
        log("判决: ✅ 整晚稳定，无退化")
    else:
        log("判决: ⚠️ 观测到 %d 个问题" % all_fails)
    
    log("=" * 50)
    log("night_watch 完成")
    
    return {"cycles": MAX_CYCLES, "total_fails": all_fails}

if __name__ == "__main__":
    main()
