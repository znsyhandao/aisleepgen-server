#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缺口 A: 边界审计者的审计（meta-meta 审计）
解决"谁审计 arch_boundary 本身"的问题

核心设计：
1. MD5锚定历史追踪 — 每次部署记录 arch_boundary.py 的 MD5
2. 边界参数漂移检测 — 检查阈值是否随时间变化
3. meta-meta 规则：边界本身可以在受控条件下进化，但必须记录：
   - 谁改了什么
   - 为什么改
   - 改之前的效果基线
   - 改之后的效果变化
"""

import hashlib, json, os, time
from datetime import datetime
from typing import Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOUNDARY_AUDIT_DIR = os.path.join(BASE_DIR, "data", "boundary_audit")
os.makedirs(BOUNDARY_AUDIT_DIR, exist_ok=True)

ANCHOR_PATH = os.path.join(BOUNDARY_AUDIT_DIR, "md5_anchor_history.jsonl")
PARAM_HISTORY_PATH = os.path.join(BOUNDARY_AUDIT_DIR, "param_drift.jsonl")
EVOLUTION_LOG_PATH = os.path.join(BOUNDARY_AUDIT_DIR, "boundary_evolution.jsonl")
VIOLATION_LOG_PATH = os.path.join(BOUNDARY_AUDIT_DIR, "violations.jsonl")


def compute_file_md5(filepath: str) -> str:
    """计算文件 MD5"""
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def anchor_boundary_md5():
    """锚定 arch_boundary.py 的当前 MD5"""
    arch_path = os.path.join(BASE_DIR, "arch_boundary.py")
    if not os.path.exists(arch_path):
        return {"error": "arch_boundary.py not found"}

    md5 = compute_file_md5(arch_path)
    record = {
        "timestamp": time.time(),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file": "arch_boundary.py",
        "md5": md5,
    }
    with open(ANCHOR_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def check_md5_drift() -> Dict:
    """检查 arch_boundary.py 的 MD5 是否与上一次锚定一致"""
    arch_path = os.path.join(BASE_DIR, "arch_boundary.py")
    if not os.path.exists(arch_path):
        return {"status": "error", "message": "arch_boundary.py not found"}

    current_md5 = compute_file_md5(arch_path)

    if not os.path.exists(ANCHOR_PATH):
        # 无历史记录，锚定当前值
        r = anchor_boundary_md5()
        return {
            "status": "first_anchor",
            "current_md5": current_md5,
            "anchored_md5": current_md5,
            "note": "首次锚定",
        }

    # 读取上一次锚定
    with open(ANCHOR_PATH, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    if not lines:
        r = anchor_boundary_md5()
        return {"status": "first_anchor", "current_md5": current_md5}

    last_anchor = json.loads(lines[-1])
    last_md5 = last_anchor.get("md5", "")

    drifted = current_md5 != last_md5

    # 如果漂移了，自动记录新的锚定
    if drifted:
        anchor_boundary_md5()

    return {
        "status": "drifted" if drifted else "intact",
        "current_md5": current_md5,
        "anchored_md5": last_md5,
        "last_anchor_time": last_anchor.get("date", "?"),
        "drift_count": sum(1 for l in lines if l.strip()),
        "note": "arch_boundary.py 已修改，请审核变更！" if drifted else "边界文件未修改",
    }


def track_param_drift(boundary_id: str, param_name: str,
                      old_value: float, new_value: float,
                      reason: str = ""):
    """记录边界参数的漂移

    参数漂移不等于违规——但必须记录原因，以便后续审计。
    """
    record = {
        "timestamp": time.time(),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "boundary_id": boundary_id,
        "param": param_name,
        "old_value": old_value,
        "new_value": new_value,
        "delta": round(new_value - old_value, 4),
        "reason": reason,
    }
    with open(PARAM_HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def log_boundary_evolution(action: str, detail: Dict):
    """记录架构边界的进化历史

    Args:
        action: 'add_rule', 'remove_rule', 'modify_threshold',
                'add_protected_file', 'change_meta_rule',
                'deploy', 'rollback'
        detail: 具体变更详情
    """
    record = {
        "timestamp": time.time(),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "detail": detail,
        "md5_boundary": compute_file_md5(os.path.join(BASE_DIR, "arch_boundary.py")),
    }
    with open(EVOLUTION_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def get_meta_meta_report() -> Dict:
    """生成 meta-meta 审计报告"""
    report = {
        "arch_md5": check_md5_drift(),
        "drift_history": [],
        "evolution_history": [],
        "violation_history": [],
    }

    # 参数漂移历史
    if os.path.exists(PARAM_HISTORY_PATH):
        with open(PARAM_HISTORY_PATH, "r", encoding="utf-8") as f:
            report["drift_history"] = [
                json.loads(l) for l in f.readlines() if l.strip()
            ][-20:]  # 最近20条

    # 进化历史
    if os.path.exists(EVOLUTION_LOG_PATH):
        with open(EVOLUTION_LOG_PATH, "r", encoding="utf-8") as f:
            report["evolution_history"] = [
                json.loads(l) for l in f.readlines() if l.strip()
            ][-20:]

    return report


def deploy_hook():
    """部署钩子——部署时自动检查和锚定"""
    print("[MetaMeta] === 部署前边界审核 ===")
    drift = check_md5_drift()
    print(f"  arch_boundary.py MD5: {drift['status']}")
    if drift['status'] == 'drifted':
        print(f"  警告: arch_boundary.py 已修改!")
        print(f"  旧: {drift['anchored_md5'][:16]}...")
        print(f"  新: {drift['current_md5'][:16]}...")
        log_boundary_evolution("deploy_with_change", {
            "note": "部署时检测到边界文件变更，已自动重新锚定",
            "old_md5": drift['anchored_md5'],
            "new_md5": drift['current_md5'],
        })

    # 检查依赖强化循环
    print(f"  MD5漂移次数: {drift.get('drift_count', 0)}")
    print(f"  [{'OK' if drift['status'] == 'intact' else 'WARN'}] 边界完整性")

    log_boundary_evolution("deploy_check", {
        "md5_current": drift.get('current_md5', '?'),
        "status": drift['status'],
    })
    return drift


# ============================================================
# 缺口 C: 依赖强化循环检测器
# ============================================================

class DependencyReinforcementDetector:
    """检测 effectiveness_loop 自身的权重调整是否在制造依赖强化

    依赖强化循环:
      推荐方案A → 用户依赖A → 其他方案效果差 → A权重更高 → 更多推荐A
    这个自指路径是 effectiveness_loop 自身的权重更新机制产生的。
    """

    def __init__(self):
        pass

    def detect(self, openid: str,
               recommendation_history: List[Dict],
               weight_history: List[Dict]) -> Dict:
        """检测依赖强化循环

        Args:
            recommendation_history: 推荐历史 [{'strategy': ..., 'date': ..., 'weight': ...}, ...]
            weight_history: 权重历史 [{'strategy': ..., 'weight': ..., 'date': ...}, ...]

        Returns:
            {
                'has_reinforcement': bool,      # 是否存在依赖强化
                'reinforcement_score': float,   # 0~1 强化强度
                'strongest_loop': {             # 最强强化环
                    'anchor_strategy': str,      # 锚定策略（依赖的中心）
                    'entropy': float,            # 策略多样性
                    'weight_monopoly': float,    # 权重垄断度
                },
                'signals': {...},
            }
        """
        if len(recommendation_history) < 10:
            return {
                "has_reinforcement": False,
                "reinforcement_score": 0.0,
                "message": "数据不足（<10条推荐记录）",
            }

        signals = {}

        # ---- 信号1: 策略多样性熵 ----
        # 熵越低 = 越依赖单一策略
        strategy_counts = {}
        for r in recommendation_history:
            s = r.get("strategy", "unknown")
            strategy_counts[s] = strategy_counts.get(s, 0) + 1

        total_recs = sum(strategy_counts.values())
        entropy = 0.0
        for s, c in strategy_counts.items():
            p = c / total_recs
            if p > 0:
                entropy -= p * (p and __import__('math').log2(p))

        max_strategy = max(strategy_counts, key=strategy_counts.get)
        monopoly = strategy_counts[max_strategy] / total_recs

        signals["strategy_entropy"] = {
            "value": round(entropy, 3),
            "score": round(max(0, 1.0 - entropy / __import__('math').log2(max(2, len(strategy_counts)))), 3),
            "note": "熵越低=越单一依赖",
        }
        signals["weight_monopoly"] = {
            "value": round(monopoly, 3),
            "score": round(monopoly, 3),
            "note": f"'{max_strategy}'占{monopoly:.0%}的推荐",
        }

        # ---- 信号2: 权重偏好方差 ----
        # 如果 weights 逐渐向少数策略收敛 → 强化循环
        if weight_history and len(weight_history) >= 5:
            recent_weights = weight_history[-10:]
            strategies_in_weights = set(w.get("strategy", "") for w in recent_weights)
            if len(strategies_in_weights) >= 2:
                # 计算权重随时间向某个策略收敛的趋势
                convergence_scores = {}
                for strategy in strategies_in_weights:
                    strat_weights = [w.get("weight", 0) for w in recent_weights
                                    if w.get("strategy") == strategy]
                    if len(strat_weights) >= 3:
                        # 权重增大会被分成两半，看前半平均 vs 后半平均
                        half = len(strat_weights) // 2
                        first_half = sum(strat_weights[:half]) / half if half > 0 else 0
                        second_half = sum(strat_weights[half:]) / (len(strat_weights) - half) if (len(strat_weights) - half) > 0 else 0
                        trend = second_half - first_half
                        convergence_scores[strategy] = trend

                if convergence_scores:
                    max_conv = max(convergence_scores.values())
                    signals["weight_convergence"] = {
                        "value": round(max_conv, 3),
                        "score": min(1.0, max(0, max_conv / 0.1)),
                        "details": {s: round(v, 3) for s, v in convergence_scores.items()},
                        "note": "权重正向收敛 = 强化循环信号",
                    }

        # ---- 信号3: 切换条件触发但不切换 ----
        # 依赖检测触发了 flag 但实际没有 force_switch
        dep_flags = [r for r in recommendation_history
                    if r.get("dependency_flag") and not r.get("force_switched")]
        if dep_flags:
            signals["unswitched_dependency"] = {
                "value": len(dep_flags),
                "score": min(1.0, len(dep_flags) / 5.0),
                "note": f"{len(dep_flags)}次依赖标记但未切换",
            }

        # ---- 综合得分 ----
        weights_config = {
            "strategy_entropy": 0.35,
            "weight_monopoly": 0.30,
            "weight_convergence": 0.20,
            "unswitched_dependency": 0.15,
        }
        score = 0.0
        for key, w in weights_config.items():
            if key in signals:
                score += w * signals[key]["score"]

        result = {
            "has_reinforcement": score >= 0.5,
            "reinforcement_score": round(score, 3),
            "threshold": 0.5,
            "signals": signals,
            "strongest_loop": {
                "anchor_strategy": max_strategy,
                "entropy": round(entropy, 3),
                "weight_monopoly": round(monopoly, 3),
            },
            "message": (
                f"依赖强化检测: 得分{score:.2f}/{0.5:.2f}, "
                f"最高策略'{max_strategy}'({monopoly:.0%})"
            ),
        }
        return result


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    import sys
    print("=== MetaMeta: 边界审计者的审计 ===")

    # 1. MD5锚定
    print("\n[1] MD5锚定:")
    r = anchor_boundary_md5()
    print(f"  arch_boundary.py md5={r['md5'][:16]}...")
    drift = check_md5_drift()
    print(f"  漂移检测: {drift['status']}")

    # 2. 参数漂移日志
    print("\n[2] 参数漂移日志:")
    track_param_drift("AB_001", "max_consecutive", 5, 6, "测试调参")
    print(f"  已写入 {PARAM_HISTORY_PATH}")

    # 3. 进化日志
    print("\n[3] 进化日志:")
    log_boundary_evolution("add_rule", {"rule": "SB_003", "name": "test"})
    log_boundary_evolution("deploy_check", {"status": "ok"})
    print(f"  已写入 {EVOLUTION_LOG_PATH}")

    # 4. 依赖强化检测
    print("\n[4] 依赖强化循环检测:")
    dd = DependencyReinforcementDetector()
    recents = [
        {"strategy": "冥想_呼吸", "date": "2026-07-09", "weight": 0.3},
        {"strategy": "冥想_呼吸", "date": "2026-07-09", "weight": 0.35},
        {"strategy": "冥想_呼吸", "date": "2026-07-09", "weight": 0.4},
        {"strategy": "白噪音", "date": "2026-07-07", "weight": 0.25},
        {"strategy": "冥想_呼吸", "date": "2026-07-08", "weight": 0.5},
        {"strategy": "冥想_呼吸", "date": "2026-07-08", "weight": 0.55},
        {"strategy": "冥想_呼吸", "date": "2026-07-09", "weight": 0.6},
        {"strategy": "冥想_呼吸", "date": "2026-07-09", "weight": 0.65},
        {"strategy": "冥想_呼吸", "date": "2026-07-09", "weight": 0.7},
        {"strategy": "冥想_呼吸", "date": "2026-07-09", "weight": 0.72},
    ]
    # 权重历史
    weights = [
        {"strategy": "冥想_呼吸", "weight": 0.3, "date": "2026-07-01"},
        {"strategy": "冥想_呼吸", "weight": 0.4, "date": "2026-07-02"},
        {"strategy": "冥想_呼吸", "weight": 0.5, "date": "2026-07-03"},
        {"strategy": "冥想_呼吸", "weight": 0.6, "date": "2026-07-04"},
        {"strategy": "冥想_呼吸", "weight": 0.7, "date": "2026-07-05"},
        {"strategy": "冥想_呼吸", "weight": 0.75, "date": "2026-07-06"},
        {"strategy": "白噪音", "weight": 0.25, "date": "2026-07-01"},
        {"strategy": "白噪音", "weight": 0.20, "date": "2026-07-06"},
    ]
    result = dd.detect("test", recents, weights)
    print(f"  强化得分: {result['reinforcement_score']}")
    print(f"  有强化循环: {result['has_reinforcement']}")
    print(f"  锚定策略: {result['strongest_loop']['anchor_strategy']}")
    print(f"  策略熵: {result['strongest_loop']['entropy']}")
    print(f"  权重垄断: {result['strongest_loop']['weight_monopoly']}")

    # 5. 部署钩子
    print("\n[5] 部署钩子:")
    deploy_hook()

    # 6. 全量报告
    print("\n[6] MetaMeta报告:")
    report = get_meta_meta_report()
    print(f"  边界 MD5: {report['arch_md5']['status']}")
    print(f"  参数漂移数: {len(report['drift_history'])}")
    print(f"  进化事件数: {len(report['evolution_history'])}")

    print("\nDone.")
