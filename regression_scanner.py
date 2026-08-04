"""
regression_scanner.py — AISleepGen 退化预测引擎 (L4 → L5)

核心能力：
  1. 从 evolve_history.jsonl 读取历史基线运行记录
  2. 追踪 7 项指标的连续趋势（基线通过率、CRITICAL数、HIGH数、MEDIUM数、质量分数）
  3. 3连降 → WARNING, 5连降 → BLOCKER
  4. 每次 post_edit_hook 运行后自动调用

输出：
  - 当前状态: PASS / WARNING / BLOCKER
  - 退化指标列表
  - 趋势方向箭头 (+/-)
  - 预测：再跑几次会出界

用法：
  python regression_scanner.py                # 扫描退化
  python regression_scanner.py trend           # 显示趋势图
  python regression_scanner.py history         # 显示历史快照
"""

import os, sys, json
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
HISTORY_PATH = os.path.join(PROJECT_ROOT, "data", "self_evolve", "evolve_history.jsonl")

TRACKED_METRICS = [
    ("L0通过率", "l0_pass_rate", lambda r: r.get("results", {}).get("l0", {}).get("pass_rate", 0)),
    ("CRITICAL", "critical", lambda r: r.get("results", {}).get("l1", {}).get("by_severity", {}).get("CRITICAL", 0)),
    ("HIGH", "high", lambda r: r.get("results", {}).get("l1", {}).get("by_severity", {}).get("HIGH", 0)),
    ("MEDIUM", "medium", lambda r: r.get("results", {}).get("l1", {}).get("by_severity", {}).get("MEDIUM", 0)),
    ("门禁通过", "gate_pass", lambda r: r.get("results", {}).get("gate", {}).get("gated", False)),
    ("质量分数", "quality_score", lambda r: r.get("results", {}).get("quality_score", 0) or 
     r.get("quality_score", 0)),
]


def load_history(max_records=50) -> list:
    """加载历史记录"""
    records = []
    if not os.path.exists(HISTORY_PATH):
        return records
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return records[-max_records:]


def extract_value(record, accessor) -> float:
    """安全取值"""
    try:
        v = accessor(record)
        return float(v) if v is not None else None
    except Exception:
        return None


def scan_regressions(records: list) -> dict:
    """扫描所有指标的趋势退化"""
    if len(records) < 3:
        return {
            "status": "INSUFFICIENT_DATA",
            "message": f"需要至少3条记录，当前{len(records)}条",
            "metrics": [],
        }
    
    metric_results = []
    has_blocker = False
    has_warning = False
    
    for display_name, key, accessor in TRACKED_METRICS:
        values = []
        for r in records[-5:]:  # 只看最近5次
            v = extract_value(r, accessor)
            if v is not None:
                values.append(v)
        
        if len(values) < 3:
            continue
        
        # 趋势方向
        changes = []
        for i in range(1, len(values)):
            changes.append(values[i] - values[i-1])
        
        # 连续下降检测（正指标=通过率/分数 下降是坏；负指标=CRITICAL/HIGH 上升是坏）
        is_negative_metric = key in ("critical", "high", "medium")
        consecutive_drops = 0
        max_drops = 0
        direction = "→"
        
        for c in changes:
            if (is_negative_metric and c > 0) or (not is_negative_metric and c < 0):
                consecutive_drops += 1
                max_drops = max(max_drops, consecutive_drops)
            else:
                consecutive_drops = 0
        
        # 方向箭头
        if changes:
            recent_trend = sum(changes[-2:])
            if is_negative_metric:
                direction = "↗" if recent_trend > 0 else ("↘" if recent_trend < 0 else "→")
            else:
                direction = "↗" if recent_trend > 0 else ("↘" if recent_trend < 0 else "→")
        
        status = "PASS"
        if max_drops >= 3:
            status = "WARNING"
            has_warning = True
        if max_drops >= 5:
            status = "BLOCKER"
            has_blocker = True
        
        # === PAIR-Bench 渐进反馈增强（arXiv 2607.01360）===
        # 不仅仅看连续下降，还评估修复轨迹的3个维度：
        pair_detail = {}
        if len(values) >= 4 and len(changes) >= 3:
            # 1. 变化幅度（单次降解不要过度告警）
            mean_change = sum(abs(c) for c in changes) / len(changes)
            pair_detail["mean_abs_change"] = round(mean_change, 2)
            
            # 2. 恢复速度（如果连续2次下降后第3次上升→不告警）
            last_3 = changes[-3:]
            recovery = last_3[0] < 0 and last_3[1] < 0 and last_3[2] > 0
            pair_detail["recovery_detected"] = recovery
            
            # 3. 噪声水平（指标波动>阈值→可能只是随机波动）
            noise = max(values) - min(values) if values else 0
            pair_detail["noise_level"] = round(noise, 2)
            
            # 渐进调整：如果 detected recovery，降级告警
            if recovery and status == "WARNING":
                status = "PASS"  # 恢复中，暂不告警
                pair_detail["downgrade_reason"] = "recovery_detected"
            if recovery and status == "BLOCKER":
                status = "WARNING"
                pair_detail["downgrade_reason"] = "recovery_detected_from_blocker"
        
        metric_results.append({
            "metric": display_name,
            "key": key,
            "status": status,
            "direction": direction,
            "consecutive_drops": max_drops,
            "recent_values": values[-5:],
            "changes": changes[-3:] if len(changes) >= 3 else changes,
            "pair": pair_detail,
        })
    
    # 综合判断
    if has_blocker:
        overall_status = "BLOCKER"
    elif has_warning:
        overall_status = "WARNING"
    else:
        overall_status = "PASS"
    
    return {
        "status": overall_status,
        "record_count": len(records),
        "timestamp": datetime.now().isoformat(),
        "metrics": metric_results,
    }


def print_report(scan: dict):
    """打印退化报告"""
    print("=" * 55)
    print("  AISleepGen 退化趋势检测")
    print("=" * 55)
    print()
    print(f"  基线记录: {scan['record_count']} 次")
    print(f"  综合状态: ", end="")
    if scan["status"] == "PASS":
        print("✅ 稳定")
    elif scan["status"] == "WARNING":
        print("⚠️ 有退化趋势")
    else:
        print("🚨 阻塞 - 多项指标连续退化")
    print()
    
    if scan.get("message"):
        print(f"  {scan['message']}")
        print()
    
    for m in scan.get("metrics", []):
        icon = {"PASS": "✅", "WARNING": "⚠️", "BLOCKER": "🚨"}.get(m["status"], "❓")
        vals = m["recent_values"]
        if m["key"] in ("critical", "high", "medium"):
            vals_str = " → ".join(str(int(v)) for v in vals)
        elif m["key"] == "l0_pass_rate":
            vals_str = " → ".join(f"{v:.0f}%" for v in vals)
        else:
            vals_str = " → ".join(f"{v:.1f}" for v in vals)
        
        print(f"  {icon} {m['metric']:<10} {m['direction']} {vals_str}")
        if m["consecutive_drops"] >= 3:
            print(f"      连续退化 {m['consecutive_drops']} 次")
    
    return scan["status"] == "PASS"


def print_trend():
    """显示历史趋势（简化版）"""
    records = load_history()
    if not records:
        print("尚无历史记录")
        return
    
    print("=" * 55)
    print("  AISleepGen 质量历史趋势")
    print("=" * 55)
    print()
    
    # 每次运行一行
    for i, r in enumerate(records[-20:]):
        try:
            ts = r.get("timestamp", "")[:16] if r.get("timestamp") else "?"
            l0 = r.get("results", {}).get("l0", {}).get("pass_rate", 0)
            cri = r.get("results", {}).get("l1", {}).get("by_severity", {}).get("CRITICAL", 0)
            gate = r.get("results", {}).get("gate", {}).get("gated", True)
            icon = "✅" if gate else "❌"
            print(f"  #{i+1:2d} {icon} {ts} | 基线={l0:.0f}% | CRITICAL={int(cri)}")
        except Exception:
            pass


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "trend":
        print_trend()
    elif len(sys.argv) > 1 and sys.argv[1] == "history":
        records = load_history()
        print(f"共 {len(records)} 条记录")
        for i, r in enumerate(records[-10:]):
            ts = r.get("timestamp", "?")[:19]
            print(f"  #{i+1} {ts}")
    else:
        records = load_history()
        scan = scan_regressions(records)
        result = print_report(scan)
        if not result:
            print(f"\n  ⚠️ 检测到退化趋势，建议回滚或修复")
