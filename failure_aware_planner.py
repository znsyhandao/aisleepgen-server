"""
failure_aware_planner.py — DeepMind 失败感知规划启示

每个干预方案附带一个 failure_condition 字段：
"此方案在 X>Y 条件下不可用（基于 N 次失效经验）"

从 shared_experience_memory 加载规则，
对 action_planner 的输出做后处理过滤。
"""
import os, sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 干预方案的已知失效条件（内置知识）
# 格式: {干预名: [{"condition": "变量>阈值", "reason": "原因"}]}
BUILTIN_FAILURES = {
    "sleep_restriction": [
        {"condition": "anxiety>7", "reason": "高焦虑患者对睡眠限制依从性差，可能加重焦虑"},
        {"condition": "stress_level>7", "reason": "高压状态下限制睡眠时间可能导致情绪崩溃"},
    ],
    "stimulus_control": [
        {"condition": "mobility_limited=1", "reason": "行动不便者难以执行20分钟离床规则"},
    ],
    "paradoxical_intention": [
        {"condition": "anxiety>6", "reason": "反向意图在高焦虑患者中常被误解为'不要睡觉'"},
        {"condition": "depression_flag=1", "reason": "抑郁症患者可能将反向意图理解为消极确认"},
    ],
    "腹式呼吸放松训练": [
        {"condition": "anxiety>7", "reason": "共享经验：高焦虑患者反馈此方法无效"},
        {"condition": "panic_history=1", "reason": "有惊恐发作史者集中注意呼吸可能诱发过度换气"},
    ],
    "渐进式肌肉放松": [
        {"condition": "chronic_pain=1", "reason": "慢性疼痛患者可能无法完成肌肉紧张步骤"},
    ],
    "正念冥想": [
        {"condition": "ptsd_flag=1", "reason": "PTSD患者静坐冥想可能触发闪回"},
    ],
}


def get_failure_conditions(therapy_name: str) -> list:
    """获取某个干预的已知失效条件（内置+经验记忆）"""
    conditions = list(BUILTIN_FAILURES.get(therapy_name, []))
    
    # 从共享经验记忆中补充
    try:
        sys.path.insert(0, PROJECT_ROOT)
        from shared_experience_memory import _load
        mem = _load()
        for rule in mem.get("rules", []):
            if rule.get("type") == "avoid" and rule.get("subject") == therapy_name:
                ctx = rule.get("context", {})
                if ctx:
                    # 把 context 转为 condition 字符串
                    for k, v in ctx.items():
                        if isinstance(v, (int, float)) and v > 0:
                            conditions.append({
                                "condition": f"{k}>{v-2}",  # 略宽松
                                "reason": f"共享经验：此干预在类似条件(阈值)下被标记为低效",
                                "source": "experience_memory",
                            })
    except:
        pass
    
    return conditions


def filter_therapies(therapies: list, user_context: dict) -> list:
    """
    对推荐方案做失败感知过滤
    
    参数:
      therapies: 原始推荐方案列表（字符串或dict）
      user_context: 用户当前状态 {anxiety:7, stress_level:6, ...}
    
    返回:
      filtered: 过滤后的推荐（附加过滤理由）
      blocked: 被阻止的方案及理由
    """
    filtered = []
    blocked = []
    
    for therapy in therapies:
        name = therapy if isinstance(therapy, str) else therapy.get("name", "")
        conditions = get_failure_conditions(name)
        
        trigger_reasons = []
        for cond in conditions:
            raw = cond["condition"]
            reason = cond.get("reason", "")
            
            # 解析 condition: "变量>阈值"
            if ">" not in raw:
                continue
            try:
                var, threshold_str = raw.split(">", 1)
                var = var.strip()
                threshold = float(threshold_str)
                
                # 检查用户上下文
                user_val = user_context.get(var)
                if user_val is not None:
                    if float(user_val) > threshold:
                        trigger_reasons.append(f"{name}:{reason}")
            except:
                continue
        
        if trigger_reasons:
            blocked.append({
                "therapy": name,
                "reasons": trigger_reasons,
            })
        else:
            filtered.append(therapy)
    
    return filtered, blocked


def format_blocked_summary(blocked: list) -> str:
    """格式化为自然语言提示"""
    if not blocked:
        return ""
    lines = ["🚫 失败感知过滤：以下方案因条件不满足已自动排除："]
    for b in blocked:
        for r in b["reasons"][:2]:
            lines.append(f"  - {b['therapy']}: {r}")
    return "\n".join(lines)


def inject_into_result(wm_result: dict, user_context: dict) -> dict:
    """注入到 WorldModel 输出结果中"""
    if not isinstance(wm_result, dict):
        return wm_result
    
    therapies = wm_result.get("recommended_therapies", [])
    if not therapies:
        return wm_result
    
    filtered, blocked = filter_therapies(therapies, user_context)
    
    wm_result["recommended_therapies"] = filtered
    wm_result["_failure_aware_blocked"] = blocked
    wm_result["_failure_aware_summary"] = format_blocked_summary(blocked)
    
    return wm_result


def status() -> dict:
    """查看状态"""
    total_builtin = sum(len(v) for v in BUILTIN_FAILURES.values())
    
    # 从经验记忆加载补充规则
    try:
        sys.path.insert(0, PROJECT_ROOT)
        from shared_experience_memory import _load
        mem = _load()
        exp_rules = [r for r in mem.get("rules", []) if r.get("type") == "avoid"]
    except:
        exp_rules = []
    
    return {
        "builtin_failures": total_builtin,
        "covered_therapies": list(BUILTIN_FAILURES.keys()),
        "experience_rules_available": len(exp_rules),
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        s = status()
        print(f"内置失败条件: {s['builtin_failures']}")
        print(f"覆盖方案: {', '.join(s['covered_therapies'])}")
        print(f"经验规则: {s['experience_rules_available']}")
    else:
        # Demo
        therapies = ["sleep_restriction", "stimulus_control", "腹式呼吸放松训练", "正念冥想"]
        user = {"anxiety": 8, "stress_level": 7}
        
        filtered, blocked = filter_therapies(therapies, user)
        print(f"原始: {therapies}")
        print(f"过滤后: {filtered}")
        print(f"被阻止: {[b['therapy'] for b in blocked]}")
        print(f"\n{format_blocked_summary(blocked)}")
