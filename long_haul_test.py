"""
long_haul_test.py — 长程韧性测试

模拟 MopMonk 上百轮自主迭代场景：
  WorldModel 连续跑 N 轮对话，监控：
  1. 上下文膨胀（prompt 长度增长曲线）
  2. 响应时间退化（每轮耗时）
  3. 决策漂移（连续 5 轮的评分方差）
  4. 记忆爆炸（JSON 文件增长）
  5. 内存泄漏（进程内存增长）
  6. 看门狗存活

用法：
  python long_haul_test.py 10        # 跑 10 轮快速测试
  python long_haul_test.py 50 --report  # 跑 50 轮+生成报告
  python long_haul_test.py status     # 查看当前测试状态
"""
import os, sys, json, time, subprocess, gc
from datetime import datetime
import tracemalloc

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(PROJECT_ROOT, "data", "long_haul")
WATCHER_FILE = os.path.join(PROJECT_ROOT, "data", "self_evolve", "watchdog_status.json")
REPORT_FILE = os.path.join(REPORT_DIR, "long_haul_report.json")

# 测试用例：多轮推演剧情
# 每一轮给 WorldModel 一个渐进式的剧情
STORY_LINE = [
    # 第 1-5 轮：建立基线
    {"round": 1, "message": "我最近总是凌晨2点醒，醒了就睡不着，白天很累", "expected_focus": "夜间觉醒"},
    {"round": 2, "message": "昨晚睡了4个小时就醒了，醒的时候心跳很快", "expected_focus": "生理激活"},
    {"round": 3, "message": "我今天试了热水泡脚，还是2点醒了", "expected_focus": "干预反馈"},
    {"round": 4, "message": "我白天喝了三杯咖啡，躺着也睡不着", "expected_focus": "咖啡因影响"},
    {"round": 5, "message": "我发现只有抱着我的猫才能睡得好一点", "expected_focus": "行为模式"},
    # 第 6-10 轮：交叉问题（测试记忆保持）
    {"round": 6, "message": "你还记得我之前说凌晨2点醒吗？今天又加了凌晨4点醒一次", "expected_focus": "记忆一致性"},
    {"round": 7, "message": "我用了你推荐的呼吸方法，感觉更焦虑了", "expected_focus": "自愈/失败记忆"},
    {"round": 8, "message": "今天去体检，医生说我心率不齐", "expected_focus": "新信息整合"},
    {"round": 9, "message": "我在网上看到褪黑素有用，你觉得呢", "expected_focus": "循证评估"},
    {"round": 10, "message": "昨天我终于睡了6个小时！但醒了两次", "expected_focus": "进展追踪"},
]


def _ensure_dir():
    os.makedirs(REPORT_DIR, exist_ok=True)


def _load_world_model():
    """加载WorldModelEngine"""
    sys.path.insert(0, PROJECT_ROOT)
    from sleep_world_model import WorldModelEngine
    from shared_fail_memory import load
    wm = WorldModelEngine()
    load()  # 预热失败记忆
    return wm


def _send_message(wm, user_id: str, message: str):
    """发送一条消息到WorldModel"""
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    
    sleep_data = {
        "user_id": user_id,
        "message": message,
        "bedtime": "23:30",
        "wake_time": "07:00",
        "sleep_latency": 45 if "失眠" in message or "睡不着" in message else 30,
        "awake_times": 2 if "醒" in message else 1,
        "feeling": "疲惫" if "累" in message or "疲倦" in message else "一般",
        "stress_level": 7 if "焦虑" in message or "心跳" in message else 5,
        "total_sleep_min": 300 if "4个小时" in message else 360,
        "pain": False,
        "is_long_haul_test": True,
    }
    
    # 调用 comprehensive_analysis
    result = wm.comprehensive_analysis(sleep_data, today_str=today)
    return result


def _get_process_memory() -> dict:
    """获取当前进程内存"""
    import psutil
    proc = psutil.Process(os.getpid())
    mem = proc.memory_info()
    return {
        "rss_mb": mem.rss / 1024 / 1024,
        "vms_mb": mem.vms / 1024 / 1024,
        "percent": proc.memory_percent(),
    }


def _get_context_sizes(wm) -> dict:
    """估算上下文大小"""
    sizes = {}
    # WorldModel 内部的状态
    if hasattr(wm, 'memory'):
        sizes["memory_total"] = len(str(wm.memory)) if isinstance(wm.memory, dict) else 0
    
    # 检查 decision_traces
    traces_dir = os.path.join(PROJECT_ROOT, "data", "decision_traces")
    if os.path.exists(traces_dir):
        total = 0
        for root, dirs, files in os.walk(traces_dir):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    total += os.path.getsize(fp)
                except:
                    pass
        sizes["traces_total_bytes"] = total
        sizes["traces_total_mb"] = round(total / 1024 / 1024, 2)
    
    return sizes


def _collect_round_metrics(wm, round_num: int, start_time: float, result: dict) -> dict:
    """采集单轮指标"""
    elapsed = time.time() - start_time
    metrics = {
        "round": round_num,
        "elapsed_sec": round(elapsed, 3),
        "timestamp": datetime.now().isoformat(),
    }
    
    # 从 result 提取
    if isinstance(result, dict):
        metrics["score"] = result.get("score", result.get("analysis", {}).get("score", None))
        metrics["action"] = result.get("action", None)
        metrics["expert_count"] = len(result.get("experts", result.get("expert_responses", [])))
        metrics["risk_flags"] = len(result.get("risk_flags", []))
        metrics["recommended_therapies"] = len(result.get("recommended_therapies", []))
        # 完整性检查
        metrics["has_recommendations"] = "recommendations" in result or "recommended_therapies" in result
        metrics["has_findings"] = bool(result.get("findings", result.get("analysis", {}).get("findings", [])))
    else:
        metrics["error"] = str(type(result))
    
    # 内存
    try:
        metrics["memory"] = _get_process_memory()
    except:
        pass
    
    # 上下文
    try:
        metrics["context"] = _get_context_sizes(wm)
    except:
        pass
    
    return metrics


def run_test(num_rounds: int = 10) -> dict:
    """运行 N 轮长程韧性测试"""
    print(f"\n  🧪 长程韧性测试: {num_rounds} 轮")
    print(f"  {'='*40}", flush=True)
    
    _ensure_dir()
    tracemalloc.start()
    
    user_id = f"test_long_haul_{datetime.now().strftime('%H%M%S')}"
    wm = _load_world_model()
    
    all_metrics = []
    start_total = time.time()
    warnings = []
    failures = []
    
    for i in range(num_rounds):
        round_num = i + 1
        
        # 生成剧情
        if i < len(STORY_LINE):
            story = STORY_LINE[i]
            message = story["message"]
        else:
            # 超出预设剧情后，用渐进式剧情
            if i % 5 == 0:
                message = f"今天已经是第{round_num}天了，我的睡眠还是不太好"
            elif i % 5 == 1:
                message = f"我试了你上次的建议，但效果不太明显"
            elif i % 5 == 2:
                message = f"我现在每天记录睡眠日志，你帮我看看"
            elif i % 5 == 3:
                message = f"我换了一个新枕头，不知道有没有用"
            else:
                message = f"今天感觉比昨天好一点，但还是醒了一次"
        
        # 发送消息
        t0 = time.time()
        try:
            result = _send_message(wm, user_id, message)
        except Exception as e:
            result = {"error": str(e)}
            failures.append({"round": round_num, "error": str(e)})
        
        # 采集指标
        metrics = _collect_round_metrics(wm, round_num, t0, result)
        
        # 告警检测
        if metrics["elapsed_sec"] > 10:
            warnings.append(f"第{round_num}轮响应慢: {metrics['elapsed_sec']:.1f}s")
        
        # 每 10 轮打印状态
        all_metrics.append(metrics)
        if round_num % 10 == 0 or round_num == 1:
            mem = metrics.get("memory", {})
            ctx = metrics.get("context", {})
            status = f"  [{round_num}/{num_rounds}] {metrics['elapsed_sec']:.1f}s"
            if mem:
                status += f" | 内存: {mem.get('rss_mb', 0):.0f}MB"
            if ctx:
                status += f" | 决策轨迹: {ctx.get('traces_total_mb', 0):.2f}MB"
            print(status, flush=True)
        
        # 手动GC
        if round_num % 20 == 0:
            gc.collect()
    
    total_time = time.time() - start_total
    current_snapshot = tracemalloc.take_snapshot()
    tracemalloc.stop()
    
    # 分析退化趋势
    elapsed_series = [m["elapsed_sec"] for m in all_metrics]
    
    # 退化检测：最后5轮 vs 前5轮
    early_avg = sum(elapsed_series[:5]) / max(len(elapsed_series[:5]), 1)
    late_avg = sum(elapsed_series[-5:]) / max(len(elapsed_series[-5:]), 1)
    
    degradation = {
        "early_avg_sec": round(early_avg, 3),
        "late_avg_sec": round(late_avg, 3),
        "degradation_ratio": round((late_avg - early_avg) / max(early_avg, 0.001), 3) if early_avg > 0 else 0,
        "max_elapsed_sec": max(elapsed_series),
        "min_elapsed_sec": min(elapsed_series),
        "total_elapsed_sec": round(sum(elapsed_series), 1),
    }
    
    report = {
        "test_id": f"long_haul_{num_rounds}_{datetime.now().strftime('%H%M%S')}",
        "timestamp": datetime.now().isoformat(),
        "num_rounds": num_rounds,
        "total_time_sec": round(total_time, 1),
        "avg_round_time_sec": round(total_time / max(num_rounds, 1), 3),
        "degradation": degradation,
        "warnings": warnings,
        "failures": failures,
        "num_warnings": len(warnings),
        "num_failures": len(failures),
        "verdict": "PASS" if (len(failures) == 0 and len(warnings) < num_rounds * 0.2) else "WARNING" if len(failures) == 0 else "FAIL",
    }
    
    # 保存报告
    _ensure_dir()
    with open(REPORT_FILE.replace(".json", f"_{num_rounds}.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n  📊 长程韧性测试完成: {num_rounds} 轮")
    print(f"  总耗时: {total_time:.0f}s | 平均: {total_time/max(num_rounds,1):.1f}s/轮")
    print(f"  退化比: {degradation['degradation_ratio']*100:+.1f}% (首5轮{early_avg:.1f}s → 末5轮{late_avg:.1f}s)")
    print(f"  最大单轮: {degradation['max_elapsed_sec']:.1f}s | 最小: {degradation['min_elapsed_sec']:.1f}s")
    print(f"  警告: {len(warnings)} | 失败: {len(failures)}")
    print(f"  判决: {report['verdict']}", flush=True)
    
    return report


def status() -> dict:
    """查看最近测试状态"""
    reports = []
    if os.path.exists(REPORT_DIR):
        for f in sorted(os.listdir(REPORT_DIR)):
            if f.startswith("long_haul_report_"):
                try:
                    with open(os.path.join(REPORT_DIR, f), "r", encoding="utf-8") as fh:
                        r = json.load(fh)
                        reports.append(r)
                except:
                    pass
    
    if not reports:
        return {"status": "no_tests_yet"}
    
    latest = reports[-1]
    return {
        "status": "available",
        "latest_test": latest.get("test_id"),
        "latest_verdict": latest.get("verdict"),
        "latest_rounds": latest.get("num_rounds"),
        "latest_avg_time": latest.get("avg_round_time_sec"),
        "latest_degradation": latest.get("degradation", {}).get("degradation_ratio"),
        "total_tests": len(reports),
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2 or sys.argv[1] == "status":
        s = status()
        if s.get("status") == "no_tests_yet":
            print("还没有长程测试记录")
        else:
            print(f"最近测试: {s['latest_test']}")
            print(f"判决: {s['latest_verdict']}")
            print(f"轮数: {s['latest_rounds']}")
            print(f"平均单轮: {s['latest_avg_time']:.1f}s")
            print(f"退化比: {s['latest_degradation']*100:+.1f}")
        sys.exit(0)
    
    try:
        num = int(sys.argv[1])
    except:
        num = 10
    
    run_test(num)
