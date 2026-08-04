"""
post_edit_hook.py — AISleepGen 改后自动质量触发器

功能:
  1. Git post-commit hook: commit 后自动跑质量门禁
  2. 直接可执行: python post_edit_hook.py 手动触发
  3. 报告质量趋势对比（上次 vs 本次）

安装:
  python post_edit_hook.py install    # 注册 git hook
  python post_edit_hook.py            # 手动跑一次
  python post_edit_hook.py status     # 看质量历史
"""

import os, sys, json, subprocess, time
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
HOOK_PATH = os.path.join(PROJECT_ROOT, ".git", "hooks", "post-commit")
RESULT_PATH = os.path.join(PROJECT_ROOT, "data", "self_evolve", "post_edit_results.json")
HISTORY_PATH = os.path.join(PROJECT_ROOT, "data", "self_evolve", "evolve_history.jsonl")


def _run_gate() -> dict:
    """运行完整质量门禁"""
    sys.path.insert(0, PROJECT_ROOT)
    
    # L0: 基线
    from quality_baseline import run_baseline as _run_baseline
    l0 = _run_baseline()
    l0_sum = l0["run"]["summary"]
    
    # L1: AST扫描
    from self_evolve import run_l1_scan
    l1 = run_l1_scan()
    
    # L1+: 语义理解扫描 → 提取优先测试用例
    _semantic = {}
    try:
        import subprocess as _sp, json as _js
        _r = _sp.run([sys.executable, "-X", "utf8", "-m", "json.tool"],
          capture_output=True, text=True, timeout=5)
        # 先跑语义扫描获取output
        _sm_path = os.path.join(os.path.dirname(__file__), "semantic_scanner.py")
        _r2 = _sp.run([sys.executable, "-X", "utf8", _sm_path],
          capture_output=True, text=True, timeout=30)
        _semantic["output"] = _r2.stdout[:500]
        # 从 stdout 解析优先测试用例（简化为关键词匹配）
        _semantic["priority_tests"] = len([l for l in _r2.stdout.split('\n') if '[CRITICAL]' in l or '[HIGH]' in l])
    except Exception as e:
        _semantic["error"] = str(e)[:60]
    l1["semantic"] = _semantic
    
    # L2: 自愈
    from self_evolve import run_l2_heal_check
    l2 = run_l2_heal_check()
    
    # L2+: 端点挂了→自动触发热修复
    health = l2.get("health", {})
    down_endpoints = [k for k, v in health.items() if not v and "schema" not in k]
    if down_endpoints:
        try:
            from self_healer import run_one_cycle as _heal_cycle
            _hr = _heal_cycle()
            if _hr.get("verify", {}).get("status") == "PASS":
                l2["healed"] = True
                for ep in down_endpoints:
                    l2["health"][ep] = True
        except Exception as e:
            pass
    
    # L3: 测试生长
    from self_evolve import run_l3_test_growth
    l3 = run_l3_test_growth()
    
    # L3+: 主题感知生长
    _grow_result = {}
    try:
        from auto_case_growth import run_growth as _auto_grow
        _grow_result = _auto_grow()
        # V2：从决策轨迹采集生长
        from auto_case_growth_v2 import __file__ as _v2path
        import subprocess
        subprocess.run([sys.executable, "-X", "utf8", _v2path],
                      capture_output=True, timeout=30)
        _grow_result["from_traces"] = True
        
        # V3：从生产日志捕获异常 → 生长
        try:
            from live_capture import run_once as _live_capture
            _lc = _live_capture()
            if _lc["new_captures"] > 0:
                _grow_result["live_captures"] = _lc["new_captures"]
        except Exception as _lce:
            pass
        
    except Exception as e:
        _grow_result = {"error": str(e)[:60]}
    
    # 门禁
    from self_evolve import check_gate
    results = {
        "l0": {
            "pass_rate": l0_sum["pass_rate_pct"],
            "passed": l0_sum["passed_cases"],
            "total": l0_sum["total_cases"],
            "high_regressions": [r for r in l0["run"]["regressions"] if r["severity"] == "HIGH"],
        },
        "l1": {
            "total": l1["total"],
            "critical": l1["by_severity"].get("CRITICAL", 0),
            "high": l1["by_severity"].get("HIGH", 0),
            "medium": l1["by_severity"].get("MEDIUM", 0),
        },
        "l2": {"health": l2["health"]},
        "l3": {"new_cases": l3["discovered"] + _grow_result.get("grown", 0)},
    }
    gate = check_gate(results)
    
    # 退化趋势检测
    _regression = {}
    try:
        from regression_scanner import scan_regressions, load_history
        _records = load_history()
        _regression = scan_regressions(_records)
        # 如果有 WARNING/BLOCKER 加入门禁警告
        if _regression.get("status") in ("WARNING", "BLOCKER"):
            for m in _regression.get("metrics", []):
                if m["status"] != "PASS":
                    gate["warnings"].append(f"[退化] {m['metric']}: 连续{m['consecutive_drops']}次退化")
    except Exception as e:
        _regression = {"error": str(e)[:60]}
    
    # L4+: 差分回归（L0基线失败时定位热区）
    try:
        from differential_regression import run_diff_regression, print_report
        _diff_report = run_diff_regression(results)
        if _diff_report.get("failed_tests"):
            print_report(_diff_report)
    except:
        pass

    
    return {
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "gate": gate,
        "regression": _regression,
        "summary": {
            "pass": not gate["gated"],
            "blockers": gate["blockers"],
            "warnings": gate["warnings"],
            "score": _compute_score(results),
        },
    }


def _compute_score(results: dict) -> int:
    """计算质量分数 (0-100)"""
    score = 80  # 基础分 80
    l0 = results.get("l0", {})
    l1 = results.get("l1", {})
    
    # L0 通过率加分/扣分（±15分范围）
    rate = l0.get("pass_rate", 100)
    if rate >= 100:
        score += 10
    elif rate >= 80:
        score += 0
    elif rate >= 60:
        score -= 10
    else:
        score -= 20
    
    # CRITICAL 扣分（一项扣 20）
    score -= l1.get("critical", 0) * 20
    
    # HIGH 扣分（每10个扣1分，20个以下不扣）
    high = l1.get("high", l1.get("HIGH", 0))
    score -= max(0, high - 20) // 10
    
    # MEDIUM 扣分（每50个扣1分，50个以下不扣）
    med = l1.get("medium", l1.get("MEDIUM", 0))
    score -= max(0, med - 50) // 5

    # 退化扣分
    score -= len(l0.get("high_regressions", [])) * 15
    
    return max(0, min(100, int(score)))


def _compare_with_last(report: dict) -> dict:
    """对比上次结果"""
    if not os.path.exists(RESULT_PATH):
        return {"change": "first_run", "delta": 0}
    
    try:
        last = json.load(open(RESULT_PATH, "r", encoding="utf-8"))
        old_score = last.get("summary", {}).get("score", 100)
        new_score = report["summary"]["score"]
        
        return {
            "old_score": old_score,
            "new_score": new_score,
            "delta": new_score - old_score,
            "change": "up" if new_score > old_score else ("down" if new_score < old_score else "stable"),
            "old_critical": last.get("results", {}).get("l1", {}).get("critical", 0),
            "new_critical": report["results"]["l1"]["critical"],
        }
    except Exception:
        return {"change": "error", "delta": 0}


def _print_report(report: dict, comparison: dict):
    """打印可读报告"""
    s = report["summary"]
    r = report["results"]
    
    print()
    print("=" * 50)
    print(f"  AISleepGen 改后质量报告")
    print(f"  {report['timestamp']}")
    print("=" * 50)
    print()
    
    # 质量分数
    print(f"  📊 质量分数: {s['score']}/100", end="")
    if comparison.get("change") == "first_run":
        print(" (基线建立)")
    elif comparison["delta"] > 0:
        print(f" 📈 +{comparison['delta']}")
    elif comparison["delta"] < 0:
        print(f" 📉 {comparison['delta']}")
    else:
        print(" (不变)")
    print()
    
    # L0 基线
    l0 = r["l0"]
    print(f"  📋 L0 基线: {l0['passed']}/{l0['total']} ({l0['pass_rate']}%)")
    if l0.get("high_regressions"):
        print(f"     🚨 {len(l0['high_regressions'])} 项严重退化!")
    
    # L1 扫描
    l1 = r["l1"]
    print(f"  🔍 L1 扫描: {l1['total']} 发现")
    if l1["critical"]:
        print(f"     🔴 {l1['critical']} CRITICAL")
    if l1["high"]:
        print(f"     🟠 {l1['high']} HIGH")
    
    # L2 自愈
    l2_ok = all(r["l2"]["health"].get("results", {}).values())
    print(f"  🩺 L2 自愈: {'✅' if l2_ok else '⚠️ 部分异常'}")
    
    # 门禁
    if s["pass"]:
        print(f"\n  ✅ 门禁通过! 可以部署")
    else:
        print(f"\n  ❌ 门禁阻塞! {len(s['blockers'])} 项未通过:")
        for b in s["blockers"]:
            print(f"     🔴 {b}")
    
    print()


def run_and_report() -> int:
    """执行并返回退出码"""
    report = _run_gate()
    comparison = _compare_with_last(report)
    
    # 保存结果 + 追加到历史
    json.dump(report, open(RESULT_PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    try:
        history_entry = {"timestamp": datetime.now().isoformat(), "results": report.get("results", {}), 
                        "gate": report.get("gate", {}), "summary": report.get("summary", {})}
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(history_entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    
    _print_report(report, comparison)
    
    # 退化趋势
    if report.get("regression") and report["regression"].get("status"):
        rs = report["regression"]["status"]
        if rs == "WARNING":
            print(f"  📉 退化趋势: ⚠️ 有退化")
        elif rs == "BLOCKER":
            print(f"  📉 退化趋势: 🚨 严重退化!")
        else:
            print(f"  📉 退化趋势: ✅ 稳定")
    
    if not report["summary"]["pass"]:
        print(f"  ⛔ 门禁阻塞，共 {len(report['summary']['blockers'])} 项阻塞项")
        _auto_revert('[gate-blocked] quality score dropped')
        return 1
    
    # 自动回滚检测：即使门禁通过，如果分数猛降也要回滚
    if comparison.get("change") == "down" and comparison["delta"] <= -20:
        print(f"  🚨 质量分数骤降 {comparison['delta']} 分！自动回滚...")
        _auto_revert(reason=f"质量分数从 {comparison['old_score']} 降至 {comparison['new_score']}")
        return 1
    
    # 新引入 CRITICAL
    if comparison.get("new_critical", 0) > comparison.get("old_critical", 0):
        print(f"  🚨 新增 {comparison['new_critical'] - comparison['old_critical']} 个CRITICAL！自动回滚...")
        _auto_revert(reason="新增 CRITICAL 级别问题")
        return 1
    
    print("  ✅ 所有检查通过，质量稳定")
    return 0


def _auto_revert(reason: str = ""):
    """自动 git revert 到上一个正常版本"""
    import subprocess
    try:
        # 获取上一个 commit 的 hash
        result = subprocess.run(
            ["git", "log", "--oneline", "-2"],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=10
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            prev_hash = lines[1].split()[0]
            msg = f"auto-revert: 质量门禁触发回滚 — {reason}"
            print(f"  🔄 回滚到 {prev_hash}...")
            subprocess.run(["git", "revert", "--no-edit", prev_hash],
                          cwd=PROJECT_ROOT, timeout=30)
            print(f"  ✅ 已回滚到 {prev_hash}")
        else:
            print("  ⚠️ 只有一个 commit，跳过自动回滚")
    except Exception as e:
        print(f"  ⚠️ 自动回滚失败: {e}")
        print("  请手动回滚: git checkout HEAD~1")


def install_git_hook():
    """安装 Git post-commit hook"""
    hook_dir = os.path.dirname(HOOK_PATH)
    if not os.path.exists(hook_dir):
        print("❌ 不是 Git 仓库，无法安装 hook")
        print(f"   期待: {HOOK_PATH}")
        return 1
    
    hook_content = f'''#!/bin/sh
#
# post-commit hook — AISleepGen 质量门禁
# 每次 commit 后自动运行质量检查

# 只在特定项目目录触发
if [ -f "{__file__}" ]; then
    cd "{PROJECT_ROOT}" && python "{__file__}" 2>/dev/null
fi
'''
    
    with open(HOOK_PATH, "w", encoding="utf-8") as f:
        f.write(hook_content)
    
    # 设置为可执行
    try:
        os.chmod(HOOK_PATH, 0o755)
    except Exception:
        pass
    
    # Windows 也需要 .bat 配合
    bat_path = HOOK_PATH + ".bat"
    bat_content = f'@echo off\npython "{__file__}"\n'
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    
    print(f"✅ Git post-commit hook 已安装")
    print(f"   脚本路径: {HOOK_PATH}")
    print(f"   Hook bat: {bat_path}")
    print(f"   下次 git commit 后自动触发质量门禁")
    return 0


def show_status():
    """显示质量趋势"""
    if not os.path.exists(RESULT_PATH):
        print("❌ 尚无质量报告，请先运行: python post_edit_hook.py")
        return 1
    
    report = json.load(open(RESULT_PATH, "r", encoding="utf-8"))
    
    # 看历史趋势
    history_records = []
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        history_records.append(json.loads(line))
                    except Exception:
                        pass
    
    print("=" * 50)
    print("  AISleepGen 质量历史趋势")
    print("=" * 50)
    print()
    
    for i, rec in enumerate(history_records[-10:]):
        ts = rec.get("timestamp", "?")[:19]
        r = rec.get("results", {})
        gate = rec.get("gate", {})
        l0 = r.get("l0", {})
        l1 = r.get("l1", {})
        status = "✅" if not gate.get("gated") else "❌"
        critical = l1.get("critical", 0)
        high = l1.get("high", 0)
        print(f"  {status} #{i+1:2d} {ts} | L0:{l0.get('pass_rate','?')}% | C:{critical} H:{high}")
    
    print()
    print(f"  最新质量分数: {report['summary']['score']}/100")
    print(f"  最新门禁: {'通过' if report['summary']['pass'] else '阻塞'}")
    print()
    print("  提示: 每次 `python post_edit_hook.py` 手动更新")
    return 
    # === T1-Agent: 多Agent闭环测试（arXiv 2601.02454） ===
    try:
        _agent_max_iter = 3
        _agent_iter = 0
        while _agent_iter < _agent_max_iter:
            _score = report.get("quality_score", 0)
            _l0_pass = report.get("results", {}).get("l0", {}).get("pass_rate", 0)
            _critical = report.get("results", {}).get("l1", {}).get("critical", 0)
            _has_blockers = len(gate.get("blockers", [])) > 0
            
            # 诊断：门禁通过的指标不循环
            _needs_improvement = _critical > 0 or _l0_pass < 0.8 or _has_blockers
            if not _needs_improvement:
                break
            
            _agent_iter += 1
            gate["warnings"].append("[Agent测试迭代#" + str(_agent_iter) + "] 质量未达标，生成新测试…")
            
            # 生成针对性测试用例
            try:
                from auto_case_growth import grow_cases
                _new_cases = grow_cases() 
                if _new_cases:
                    gate["warnings"].append("  自动生成" + str(len(_new_cases)) + "个新用例")
            except:
                pass
            
            # 重新跑基线
            try:
                from quality_baseline import run_baseline
                _recheck = run_baseline(force_refresh=True)
                if isinstance(_recheck, dict):
                    _new_rate = _recheck.get("pass_rate", _l0_pass)
                    _new_critical = _recheck.get("critical", _critical)
                    gate["warnings"].append("  重检: 基线" + str(round(_new_rate*100,1)) + "% CRITICAL=" + str(_new_critical))
                    if _new_rate > _l0_pass or _new_critical < _critical:
                        gate["warnings"].append("  迭代有效，继续逼近目标")
            except:
                pass
    except:
        pass

0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "install":
            sys.exit(install_git_hook())
        elif cmd == "status":
            sys.exit(show_status())
        else:
            print(f"未知命令: {cmd}")
            print("用法:")
            print("  python post_edit_hook.py            手动跑质量门禁")
            print("  python post_edit_hook.py install    安装 Git post-commit hook")
            print("  python post_edit_hook.py status     查看质量历史")
            sys.exit(1)
    else:
        sys.exit(run_and_report())
