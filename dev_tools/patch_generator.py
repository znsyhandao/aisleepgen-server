#!/usr/bin/env python3
"""
patch_generator.py — 实验报告→代码patch (2026-07-06)

输入: experiment_runner.finish_experiment() 的 report
输出: 代码patch + 风险评分 → 写入 pending_alerts 供至尊宝确认

不自动落地代码, 只生成 patch 建议。
"""

import os, json, datetime

AISLEEP = r"D:\AISleepGen_Optimized"
RADAR = r"D:\super_frontier_radar"

PATCH_TEMPLATES = {
    "calibration._regression_coefs.pain_flag": {
        "description": "实验表明优化疼痛权重对改善评分有效",
        "code_change": "在 sleep_world_model.py L83536-$LINE 更新 pain_flag 权重值: $OLD → $NEW",
        "file": "sleep_world_model.py",
        "lines": 2,
        "risk": "低: 只改 calibration 级别的权重, 不影响专家逻辑",
    },
    "calibration._regression_coefs.awake": {
        "description": "实验表明优化夜醒权重对改善评分有效",
        "code_change": "在 calibration.json 更新 awake 系数: $OLD → $NEW",
        "file": "calibration.json",
        "lines": 0,
        "risk": "极低: 纯数据文件修改, 无需重启",
    },
    "calibration._regression_coefs.latency": {
        "description": "实验表明优化入睡时间权重对改善评分有效",
        "code_change": "在 calibration.json 更新 latency 系数: $OLD → $NEW",
        "file": "calibration.json",
        "lines": 0,
        "risk": "极低: 纯数据文件修改",
    },
    "calibration._regression_coefs.wm_score": {
        "description": "实验表明优化综合评分权重对改善评分有效",
        "code_change": "在 calibration.json 更新 wm_score 系数: $OLD → $NEW",
        "file": "calibration.json",
        "lines": 0,
        "risk": "极低: 纯数据文件修改",
    },
    "calibration.pain_penalty_base": {
        "description": "实验表明调整疼痛惩罚基数对改善评分有效",
        "code_change": "在 calibration.json 更新 pain_penalty_base: $OLD → $NEW",
        "file": "calibration.json",
        "lines": 0,
        "risk": "极低: 纯数据文件修改",
    },
    "calibration._regression_coefs.duration": {
        "description": "实验表明优化睡眠时长权重对改善评分有效",
        "code_change": "在 calibration.json 更新 duration 系数: $OLD → $NEW",
        "file": "calibration.json",
        "lines": 0,
        "risk": "极低: 纯数据文件修改",
    },
    "calibration._regression_coefs.stress": {
        "description": "实验表明优化压力权重对改善评分有效",
        "code_change": "在 calibration.json 更新 stress 系数: $OLD → $NEW",
        "file": "calibration.json",
        "lines": 0,
        "risk": "极低: 纯数据文件修改",
    },
    "use_jepa": {
        "description": "JEPA架构在A/B实验中表现更好, 建议改为全员启用",
        "code_change": """在 sleep_world_model.py L2615-L2633:
  删除 A/B 分流逻辑, 直接设置 _exp_group = "jepa"
  删除 calibration.json 的 _experiment_jepa.enabled 检查""",
        "file": "sleep_world_model.py + calibration.json",
        "lines": 12,
        "risk": "中: 移除分流逻辑, 需要备份后修改",
    },
}


def generate_patch(report: dict) -> dict:
    """
    从实验报告生成 patch 建议
    
    Args:
        report: experiment_runner.finish_experiment() 的返回值
    
    Returns:
        patch 建议字典
    """
    knob_key = report.get("knob_key", "")
    old_val = report.get("old_value")
    new_val = report.get("new_value")
    recommendation = report.get("recommendation", "数据不足")
    avg_rating = report.get("avg_rating", None)
    old_rating = report.get("old_avg_rating", None)

    # 只在上线建议时生成 patch
    if recommendation != "上线":
        return {"status": "skipped", "reason": f"建议: {recommendation}"}

    # 找对应模板
    template = PATCH_TEMPLATES.get(knob_key)
    if not template:
        # 没有预设模板 → 通用建议
        return {
            "status": "no_template",
            "knob_key": knob_key,
            "old_value": old_val,
            "new_value": new_val,
            "avg_rating": avg_rating,
            "recommendation": "上线",
            "code_change": f"更新 calibration.json 的 {knob_key}: {old_val} → {new_val}",
            "file": "calibration.json",
            "lines": 0,
            "risk": "低",
            "note": "无预设模板, 需要手写修改说明",
        }

    # 填充模板
    code_change = template["code_change"].replace("$OLD", str(old_val)).replace("$NEW", str(new_val))
    lines = template["lines"]

    patch = {
        "status": "ready",
        "knob_key": knob_key,
        "old_value": old_val,
        "new_value": new_val,
        "avg_rating": avg_rating,
        "description": template["description"],
        "code_change": code_change,
        "file": template["file"],
        "lines": lines,
        "risk": template["risk"],
        "generated_at": datetime.datetime.now().isoformat(),
    }

    return patch


def write_alert(patch: dict):
    """将 patch 写入 pending_alerts"""
    if patch.get("status") != "ready":
        return

    try:
        sys.path.insert(0, RADAR)
        from _pending_alerts import PendingAlerts
        pa = PendingAlerts()
        risk_icon = {"低": "🟢", "极低": "🟢", "中": "🟡", "高": "🔴"}.get(patch["risk"], "🟡")
        pa.add(
            f"patch_{patch['knob_key']}_{datetime.datetime.now().strftime('%Y%m%d')}",
            f"[Patch] {patch['description']} | {risk_icon}{patch['risk']}风险 | 文件: {patch['file']} ({patch['lines']}行) | {patch['code_change'][:80]}",
            "INFO"
        )
    except:
        pass


def main():
    """CLI: 从 finish_experiment 结果测试生成"""
    import argparse
    parser = argparse.ArgumentParser(description="实验→patch 生成器")
    parser.add_argument("--from-report", metavar="JSON", help="从JSON字符串生成")
    parser.add_argument("--test-all", action="store_true", help="测试所有模板")
    args = parser.parse_args()

    if args.test_all:
        print("=== 模板测试 ===")
        for knob, template in PATCH_TEMPLATES.items():
            report = {
                "knob_key": knob,
                "old_value": 0.5,
                "new_value": 0.6,
                "avg_rating": 4.2,
                "recommendation": "上线",
            }
            patch = generate_patch(report)
            print(f"  {knob}: {patch['status']}")
            if patch['status'] == 'ready':
                print(f"    file={patch['file']} lines={patch['lines']} risk={patch['risk']}")
        print()

    if args.from_report:
        import json
        report = json.loads(args.from_report)
        patch = generate_patch(report)
        print(json.dumps(patch, ensure_ascii=False, indent=2))

    if not args.test_all and not args.from_report:
        parser.print_help()


if __name__ == "__main__":
    import sys  # 给 write_alert 用的
    main()
