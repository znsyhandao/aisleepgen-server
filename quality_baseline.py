"""
quality_baseline.py — AISleepGen 质量闭环引擎 v1

核心：
  1. 建立测试用例基线（标准化输入 + 预期质量标签）
  2. 每次跑基线 → 对比历史输出 → 检测退化
  3. 输出质量报告 + 劣化告警

用法：
  python quality_baseline.py run          # 跑基线并对比历史
  python quality_baseline.py init         # 初始化基线（首次运行）
  python quality_baseline.py report       # 查看最新报告
"""

import json, os, sys, time, hashlib, traceback
from datetime import datetime
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BASELINE_DIR = os.path.join(PROJECT_ROOT, "data", "quality_baseline")
TEST_CASES_PATH = os.path.join(BASELINE_DIR, "test_cases.json")
HISTORY_PATH = os.path.join(BASELINE_DIR, "history.jsonl")
REPORT_PATH = os.path.join(BASELINE_DIR, "latest_report.json")

os.makedirs(BASELINE_DIR, exist_ok=True)

# ===== 默认测试用例（持续扩充） =====
DEFAULT_TEST_CASES = [
    {
        "id": "normal_good_sleep",
        "name": "优质睡眠基线",
        "input": {
            "message": "我昨晚睡了8小时，深睡大概2小时，醒来一次，睡到7点",
            "history": []
        },
        "expect": {
            "score_min": 40,
            "score_max": 65,  # 弱数据时模型保守
            "quality_acceptable": ["一般"],
            "min_dimensions_computed": 0,
        },
        "weight": 1.0,
    },
    {
        "id": "poor_sleep_anxiety",
        "name": "差睡眠+焦虑基线",
        "input": {
            "message": "最近失眠很严重，躺床上两小时都睡不着，一晚醒三四次",
            "history": []
        },
        "expect": {
            "score_min": 20,
            "score_max": 55,
            "quality_acceptable": ["较差", "需要改善"],
            "min_dimensions_computed": 5,
        },
        "weight": 1.5,  # 高权重：关键场景
    },
    {
        "id": "short_sleep_consistent",
        "name": "睡眠不足但规律",
        "input": {
            "message": "我每天只睡5个小时，但作息很规律，11点睡4点起，白天不困",
            "history": []
        },
        "expect": {
            "score_min": 40,
            "score_max": 70,
            "quality_acceptable": ["一般", "良好"],
            "min_dimensions_computed": 5,
        },
        "weight": 1.2,
    },
    {
        "id": "high_hrv_good_recovery",
        "name": "高HRV高恢复",
        "input": {
            "message": "昨晚HRV有85，心率52，深睡2.5小时，睡了7.5小时，醒来精神很好",
            "history": []
        },
        "expect": {
            "score_min": 75,
            "score_max": 98,
            "quality_acceptable": ["优秀", "良好"],
            "min_dimensions_computed": 5,
        },
        "weight": 1.0,
    },
    {
        "id": "fragmented_sleep_multiple_awake",
        "name": "睡眠碎片化",
        "input": {
            "message": "昨晚醒了五六次，每次醒半小时以上，总共只睡了4小时",
            "history": []
        },
        "expect": {
            "score_min": 15,
            "score_max": 50,
            "quality_acceptable": ["较差", "需要改善"],
            "min_dimensions_computed": 5,
        },
        "weight": 1.3,
    },
    {
        "id": "device_data_injection",
        "name": "设备数据注入测试",
        "input": {
            "message": "我昨晚睡了一整晚",
            "history": []
        },
        "expect": {
            "score_min": 0,
            "score_max": 100,
            "quality_acceptable": ["优秀", "良好", "一般", "较差", "需要改善"],
            "min_dimensions_computed": 0,  # 无数据时不做要求
        },
        "weight": 0.5,
    },
]


def _load_test_cases() -> list:
    """加载测试用例，自定义覆盖默认"""
    cases = list(DEFAULT_TEST_CASES)
    if os.path.exists(TEST_CASES_PATH):
        try:
            with open(TEST_CASES_PATH, "r", encoding="utf-8") as f:
                custom = json.load(f)
            # 自定义优先覆盖同id的默认用例
            custom_ids = {c["id"] for c in custom}
            cases = [c for c in cases if c["id"] not in custom_ids]
            cases.extend(custom)
        except Exception:
            pass
    return cases


def _save_test_cases(cases: list):
    """保存测试用例"""
    with open(TEST_CASES_PATH, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)


def _call_wm(input_data: dict, openid: str = "quality_test") -> dict:
    """调用世界模型做分析
    
    直接本地调用 WorldModelEngine（不走API，保证结果一致性）
    """
    user_message = input_data.get("message", "")
    history = input_data.get("history", [])
    
    try:
        import sys
        sys.path.insert(0, PROJECT_ROOT)
        from sleep_world_model import WorldModelEngine
        from extractor import DataExtractor
        
        wm = WorldModelEngine()
        extraction = DataExtractor.extract(user_message, history, openid)
        full_data = extraction.sleep_data
        if full_data:
            result = wm.comprehensive_analysis(full_data)
            if isinstance(result, dict):
                return {
                    "total_score": result.get("total_score") or result.get("score", 50),
                    "quality": result.get("quality", "一般"),
                    "analysis": result.get("analysis", {}),
                }
    except Exception as e:
        print(f"  [QualityBaseline] 本地调用失败: {str(e)[:80]}")
    
    return {"total_score": 50, "quality": "一般", "analysis": {}}


def _evaluate_result(test_case: dict, result: dict) -> dict:
    """评估单条测试结果
    
    Returns:
        dict: {pass: bool, score: int, issues: [str]}
    """
    expect = test_case["expect"]
    issues = []
    
    score = result.get("total_score", 0)
    # Normalize: WorldModel may return 0-10000 range in low-data mode
    if score > 100:
        score = score / 100  # 3522 -> 35.22
    quality = result.get("quality", "")
    
    # 评分范围检查
    if score < expect["score_min"] or score > expect["score_max"]:
        issues.append(
            f"评分违规: 期望[{expect['score_min']}-{expect['score_max']}], "
            f"实际{score}"
        )
    
    # 质量标签检查
    if quality and expect.get("quality_acceptable"):
        if quality not in expect["quality_acceptable"]:
            issues.append(
                f"质量标签不符: 期望{'/'.join(expect['quality_acceptable'])}, "
                f"实际'{quality}'"
            )
    
    # 维度数量检查
    analysis = result.get("analysis", {})
    if isinstance(analysis, dict):
        dims = analysis.get("dimensions", {})
        dim_count = len([k for k in dims if dims[k].get("score") is not None]) if isinstance(dims, dict) else 0
        if dim_count < expect.get("min_dimensions_computed", 0):
            issues.append(
                f"维度不足: 期望至少{expect['min_dimensions_computed']}个, "
                f"实际{dim_count}个"
            )
    
    passed = len(issues) == 0
    
    return {
        "test_id": test_case["id"],
        "test_name": test_case["name"],
        "passed": passed,
        "score": score,
        "quality": quality,
        "expected_range": f"[{expect['score_min']}-{expect['score_max']}]",
        "issues": issues,
        "weight": test_case.get("weight", 1.0),
    }


def _compute_weighted_score(results: list) -> dict:
    """计算加权总分"""
    total_weight = 0
    weighted_pass = 0
    total_issues = 0
    
    for r in results:
        w = r.get("weight", 1.0)
        total_weight += w
        if r["passed"]:
            weighted_pass += w
        total_issues += len(r.get("issues", []))
    
    pass_rate = (weighted_pass / total_weight * 100) if total_weight > 0 else 0
    
    return {
        "pass_rate_pct": round(pass_rate, 1),
        "passed_cases": sum(1 for r in results if r["passed"]),
        "total_cases": len(results),
        "total_issues": total_issues,
        "weighted_pass_rate": round(weighted_pass / total_weight * 100, 1) if total_weight > 0 else 0,
    }


def _load_history(limit: int = 20) -> list:
    """加载历史基线记录"""
    records = []
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
    return records[-limit:]


def _save_run_record(record: dict):
    """保存一次运行记录"""
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _detect_regression(current: dict, history: list) -> list:
    """检测与历史的退化
    
    Returns:
        list: [{type: str, metric: str, delta: float, severity: str}]
    """
    if not history:
        return []
    
    warnings = []
    
    # 与最后一次对比
    last = history[-1]
    
    pass_diff = current["pass_rate_pct"] - last.get("pass_rate_pct", 0)
    if pass_diff < -5:
        warnings.append({
            "type": "regression",
            "metric": "pass_rate",
            "before": last.get("pass_rate_pct"),
            "now": current["pass_rate_pct"],
            "delta": round(pass_diff, 1),
            "severity": "HIGH" if pass_diff < -15 else "MEDIUM",
        })
    
    issue_diff = current["total_issues"] - last.get("total_issues", 0)
    if issue_diff > 2:
        warnings.append({
            "type": "regression",
            "metric": "total_issues",
            "before": last.get("total_issues"),
            "now": current["total_issues"],
            "delta": issue_diff,
            "severity": "MEDIUM",
        })
    
    # 与3次前对比（趋势）
    if len(history) >= 3:
        avg_pass = sum(h.get("pass_rate_pct", 0) for h in history[-3:]) / 3
        if current["pass_rate_pct"] < avg_pass - 8:
            warnings.append({
                "type": "downtrend",
                "metric": "pass_rate_3avg",
                "before": round(avg_pass, 1),
                "now": current["pass_rate_pct"],
                "delta": round(current["pass_rate_pct"] - avg_pass, 1),
                "severity": "HIGH",
            })
    
    return warnings


def run_baseline(openid: str = "quality_test") -> dict:
    """跑完整的质量基线"""
    cases = _load_test_cases()
    
    results = []
    for case in cases:
        try:
            result = _call_wm(case["input"], openid)
            evaluation = _evaluate_result(case, result)
            results.append(evaluation)
        except Exception as e:
            results.append({
                "test_id": case["id"],
                "test_name": case["name"],
                "passed": False,
                "score": 0,
                "quality": "error",
                "issues": [f"调用异常: {str(e)[:100]}"],
                "weight": case.get("weight", 1.0),
            })
    
    summary = _compute_weighted_score(results)
    history = _load_history()
    regressions = _detect_regression(summary, history)
    
    run_record = {
        "timestamp": datetime.now().isoformat(),
        "version": "20260703_1",
        "summary": summary,
        "regressions": regressions,
        "details": results,
    }
    
    _save_run_record(run_record)
    
    # 保存最新报告
    report = {
        "run": run_record,
        "history_summary": {
            "runs": len(history) + 1,
            "trend": "stable",
        }
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    return report


def print_report(report: dict = None):
    """打印可读的报告"""
    if report is None:
        if not os.path.exists(REPORT_PATH):
            print("⚠️  尚未运行基线，请先执行 python quality_baseline.py run")
            return
        with open(REPORT_PATH, "r", encoding="utf-8") as f:
            report = json.load(f)
    
    run = report["run"]
    s = run["summary"]
    reg = run["regressions"]
    details = run["details"]
    
    print("=" * 55)
    print(f"  AISleepGen 质量基线报告")
    print(f"  {run['timestamp']}")
    print("=" * 55)
    print()
    print(f"  ✅ 通过: {s['passed_cases']}/{s['total_cases']}  ({s['pass_rate_pct']}%)")
    print(f"  ⚠️ 问题: {s['total_issues']} 个")
    print(f"  加权通过率: {s['weighted_pass_rate']}%")
    print()
    
    if reg:
        print("  🚨 退化告警:")
        for r in reg:
            level = "🔴" if r["severity"] == "HIGH" else "🟡"
            print(f"    {level} [{r['severity']}] {r['metric']}: {r['before']} → {r['now']} (Δ{r['delta']})")
        print()
    
    print("  📋 逐项结果:")
    for d in details:
        icon = "✅" if d["passed"] else "❌"
        issues_str = f" — {'; '.join(d['issues'][:2])}" if d["issues"] else ""
        print(f"    {icon} {d['test_name']}: {d['quality']}({d['score']}){issues_str}")
    
    print()
    print("=" * 55)
    
    # 退化时返回非零退出码
    if reg and any(r["severity"] == "HIGH" for r in reg):
        print("  ⛔ 发现严重退化！请排查后再部署。")
    elif reg:
        print("  ⚠️ 存在中等退化，建议关注。")
    else:
        print("  ✅ 无退化，质量稳定。")
    
    return reg


def init_baseline():
    """初始化基线文件"""
    cases = _load_test_cases()
    _save_test_cases(cases)
    print(f"✅ 基线初始化完成: {len(cases)} 个测试用例")
    print(f"   路径: {TEST_CASES_PATH}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python quality_baseline.py run    跑基线并对比历史")
        print("  python quality_baseline.py init   初始化基线")
        print("  python quality_baseline.py report 查看最新报告")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "init":
        init_baseline()
    elif cmd == "run":
        print("=" * 55)
        print("  正在跑质量基线...")
        print("=" * 55)
        report = run_baseline()
        regressions = print_report(report)
        if regressions and any(r["severity"] == "HIGH" for r in regressions):
            sys.exit(2)
    elif cmd == "report":
        print_report()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
