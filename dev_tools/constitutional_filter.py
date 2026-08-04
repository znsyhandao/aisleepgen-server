#!/usr/bin/env python3
"""
constitutional_filter.py - Constitutional AI 自约束过滤器 (2026-07-06 15:21)

原理:
  Anthropic Constitutional AI - 在输出前过一道自问:"这个建议安全吗?"

  对 AISleepGen: 干预建议(呼吸法/冥想/运动) 95% 天然安全
  但需要过滤:
    1. 医学术语可能被误解 (如"睡眠呼吸暂停" → 必须加"请就医")
    2. 运动建议不适合高危人群
    3. 没有资格当诊断工具

集成:
  在 _build_actionable_takeaway(推荐生成) 之后、return result 之前调用
  或者挂在 comprehensive_analysis return result 之前
"""

SAFETY_RULES = [
    # 规则: (关键词, 需要补充的免责声明)
    ("osa", "睡眠呼吸暂停", "⚠️ 以上分析不构成诊断。如果您怀疑睡眠呼吸暂停，请到呼吸科就诊。"),
    ("sleep_disorder", "睡眠障碍", "⚠️ 以上分析不构成诊断。睡眠障碍的确诊需要临床面诊和多导睡眠监测。"),
    ("osa_risk", "OSA风险", "⚠️ OSA风险评估不等于临床诊断。确诊需多导睡眠监测。"),
    ("depression", "抑郁", "⚠️ 以上筛查不替代专业心理评估。如持续情绪低落或自杀念头，请立即联系心理危机热线。"),
    ("suicide", "自杀", "🚨 如果您有自杀念头，请立即拨打心理危机热线: 010-82951332。"),
    ("anxiety", "焦虑", "⚠️ 以上分析不构成心理诊断。焦虑症状持续影响生活时请寻求心理专业帮助。"),
    ("medication", "药物", "⚠️ 以上建议不替代医嘱。用药调整请咨询主治医生。"),
    ("exercise_high_risk", "高危运动", "⚠️ 如果您有心脏病、高血压或其他慢性疾病，请在开始新的运动计划前咨询医生。"),
    ("diagnosis", "诊断", "⚠️ 以上分析基于自报数据，不构成医学诊断。"),
]

# 必须带的免责声明（不管content有什么）
BASE_DISCLAIMER = "⚠️ 本分析基于自报睡眠数据，仅供健康参考，不构成医学诊断或治疗建议。"


def filter_content(content: str) -> dict:
    """
    检查一段文本是否需要安全过滤

    Args:
        content: 原文（findings / recommendations / risk_flags）

    Returns:
        {"safe": True/False, "warnings": [...], "disclaimers": [...], "modified": content}
    """
    warnings = []
    disclaimers = set()
    modified = str(content)

    content_lower = content.lower()

    for key, keyword, disclaimer in SAFETY_RULES:
        if keyword in content or key in content_lower:
            # 检查免责声明是否已存在
            if disclaimer not in content:
                disclaimers.add(disclaimer)
                warnings.append(f"触发 {key}")

    # 强制加基础免责（如果结果里有评分/风险标记）
    is_scored = any(term in content_lower for term in ["score", "评分", "风险", "percent", "指数"])
    if is_scored and BASE_DISCLAIMER not in content:
        disclaimers.add(BASE_DISCLAIMER)
        if BASE_DISCLAIMER not in warnings:
            warnings.append("基础免责")

    if warnings:
        # 在内容末尾追加免责声明（不修改原文内容）
        disclaimer_text = "\n\n" + "\n".join(sorted(disclaimers))
        modified = str(content) + disclaimer_text

    return {
        "safe": len(warnings) == 0,
        "warnings": warnings,
        "disclaimers": sorted(disclaimers),
        "modified": modified,
    }


def filter_result(result: dict) -> dict:
    """
    对 comprehensive_analysis 的结果做自约束过滤

    不改动原有字段, 增加 _constitutional 字段记录过滤信息
    """
    filtered = dict(result)
    all_warnings = []
    all_disclaimers = set()

    # 1. 检查 findings
    findings = result.get("findings", [])
    for f in findings:
        f_result = filter_content(f)
        all_warnings.extend(f_result["warnings"])
        all_disclaimers.update(f_result["disclaimers"])

    # 2. 检查 risk_flags
    risk_flags = result.get("risk_flags", [])
    for r in risk_flags:
        r_result = filter_content(r)
        all_warnings.extend(r_result["warnings"])
        all_disclaimers.update(r_result["disclaimers"])

    # 3. 检查 action_plan 内的任何文本
    action_plan = result.get("action_plan", {})
    if isinstance(action_plan, dict):
        for key, val in action_plan.items():
            if isinstance(val, str) and len(val) > 5:
                ap_result = filter_content(val)
                all_warnings.extend(ap_result["warnings"])
                all_disclaimers.update(ap_result["disclaimers"])

    # 4. 检查 attribution 的专家归因
    attribution = result.get("attribution", {})
    if isinstance(attribution, dict):
        for expert_name, expert_info in attribution.items():
            if isinstance(expert_info, dict):
                spec = expert_info.get("specialty", "")
                if spec:
                    spec_result = filter_content(spec)
                    all_warnings.extend(spec_result["warnings"])
                    all_disclaimers.update(spec_result["disclaimers"])

    filtered["_constitutional"] = {
        "safe": len(all_warnings) == 0 and len(all_disclaimers) == 0,
        "warnings": list(set(all_warnings)),
        "disclaimers": sorted(all_disclaimers),
        "rule_count": len(all_warnings),
    }

    # ===== v2: 深入各专家的输出（多模态免疫探针辅助）=====
    try:
        analysis = result.get("analysis", {})
        if isinstance(analysis, dict):
            dimensions = analysis.get("dimensions", {})
            if isinstance(dimensions, dict):
                for _en, _ed in dimensions.items():
                    if not isinstance(_ed, dict):
                        continue
                    # 每个专家的 findings
                    for _f in _ed.get("findings", []):
                        if isinstance(_f, str):
                            _fr = filter_content(_f)
                            filtered["_constitutional"]["warnings"].extend(
                                w for w in _fr["warnings"] if w not in filtered["_constitutional"]["warnings"]
                            )
                            filtered["_constitutional"]["disclaimers"].extend(
                                d for d in _fr["disclaimers"] if d not in filtered["_constitutional"]["disclaimers"]
                            )
                    # 每个专家的 risk_flags
                    for _rf in _ed.get("risk_flags", []):
                        _rf_text = str(_rf)
                        _rfr = filter_content(_rf_text)
                        filtered["_constitutional"]["warnings"].extend(
                            w for w in _rfr["warnings"] if w not in filtered["_constitutional"]["warnings"]
                        )
                        filtered["_constitutional"]["disclaimers"].extend(
                            d for d in _rfr["disclaimers"] if d not in filtered["_constitutional"]["disclaimers"]
                        )
                    # 每个专家的 narrative
                    _narr = _ed.get("narrative", "")
                    if isinstance(_narr, str) and len(_narr) > 10:
                        _nr = filter_content(_narr)
                        filtered["_constitutional"]["warnings"].extend(
                            w for w in _nr["warnings"] if w not in filtered["_constitutional"]["warnings"]
                        )
                        filtered["_constitutional"]["disclaimers"].extend(
                            d for d in _nr["disclaimers"] if d not in filtered["_constitutional"]["disclaimers"]
                        )

        filtered["_constitutional"]["safe"] = (
            len(filtered["_constitutional"]["warnings"]) == 0
            and len(filtered["_constitutional"]["disclaimers"]) == 0
        )
    except Exception:
        pass

    return filtered


def summary(filtered: dict) -> str:
    """摘要"""
    con = filtered.get("_constitutional", {})
    if con.get("safe"):
        return "Constitutional AI: ✅ 安全"
    w = con.get("warnings", [])
    d = con.get("disclaimers", [])
    return f"Constitutional AI: ⚠️ {len(w)}条警告, {len(d)}条免责"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Constitutional AI 自约束过滤器")
    parser.add_argument("--test", action="store_true", help="自测")
    args = parser.parse_args()

    if args.test:
        # 测试
        test_contents = [
            "您有中度睡眠呼吸暂停风险",
            "您的睡眠质量良好",
            "建议每周跑步3次",
            "您的焦虑评分较高, 建议练习呼吸法",
            "睡眠障碍的典型表现包括入睡困难和早醒",
        ]
        print("Constitutional AI 过滤测试:\n")
        for c in test_contents:
            res = filter_content(c)
            print(f"  输入: {c}")
            print(f"  安全: {'✅' if res['safe'] else '⚠️'}")
            if res["warnings"]:
                print(f"  触发: {res['warnings']}")
            if res["disclaimers"]:
                for d in res["disclaimers"]:
                    print(f"  {d}")
            print()

        # 模拟完整结果
        fake_result = {
            "score": 0.72,
            "findings": ["您有轻度睡眠呼吸暂停迹象", "夜醒次数偏多"],
            "risk_flags": ["osa_risk_0.6", "高OSA风险"],
            "action_plan": {"recommended_therapies": ["cpap_consideration"]},
        }
        filtered = filter_result(fake_result)
        print("完整结果过滤:")
        print(f"  原始: {len(json.dumps(fake_result))} 字符")
        print(f"  安全: {'✅' if filtered['_constitutional']['safe'] else '⚠️'}")
        print(f"  警告: {filtered['_constitutional']['warnings']}")
        print(f"  免责: {filtered['_constitutional']['disclaimers'][:2]}")


if __name__ == "__main__":
    import json
    main()
