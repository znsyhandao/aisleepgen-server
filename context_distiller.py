"""
context_distiller.py — 上下文蒸馏（Anthropic Contextual Retrieval 启示）

为 shared_experience_memory 做注入前的相关性蒸馏：
  不是把全部记忆塞进 peer_context，而是根据当前用户状态
  只提取最相关的规则和经验。

原理:
  每条经验/规则有 context 标签 {anxiety, awake_times, sleep_type, ...}
  当前用户状态也有同样标签
  只注入标签匹配度 > 阈值的规则
"""
from datetime import datetime

# 权重：不同上下文维度的匹配权重
CONTEXT_WEIGHTS = {
    "anxiety": 0.30,      # 焦虑程度最重要
    "awake_times": 0.25,  # 觉醒次数
    "sleep_latency": 0.20, # 入睡潜伏期
    "sleep_type": 0.15,   # 失眠类型
    "use_count": 0.10,    # 使用次数（越低越匹配初用）
}

# 注入长度上限（字符数）
MAX_INJECTION_CHARS = 500

def score_match(rule_context: dict, user_context: dict) -> float:
    """计算规则与用户上下文的匹配度 0-1"""
    if not rule_context:
        return 0.3  # 无上下文的规则给一个基础分
    
    score = 0.0
    total_weight = 0.0
    
    for key, weight in CONTEXT_WEIGHTS.items():
        rule_val = rule_context.get(key)
        user_val = user_context.get(key)
        if rule_val is not None and user_val is not None:
            # 数值匹配度
            if isinstance(rule_val, (int, float)) and isinstance(user_val, (int, float)):
                diff = abs(rule_val - user_val)
                max_range = max(abs(rule_val), abs(user_val), 1)
                match = max(0, 1 - diff / max_range)
                score += match * weight
                total_weight += weight
            # 字符串匹配
            elif isinstance(rule_val, str) and isinstance(user_val, str):
                if rule_val == user_val:
                    score += 1.0 * weight
                    total_weight += weight
    
    if total_weight == 0:
        return 0.3
    
    return score / total_weight


def distill(mem, user_context: dict, max_items: int = 5) -> dict:
    """
    从经验记忆中蒸馏出最相关的规则和经验
    
    返回:
      {
        "avoids": [...],
        "prefers": [...],
        "habits": [...],
        "total_scored": N,  # 评估了多少条
        "max_score": 0.9    # 最高匹配度
      }
    """
    if not user_context:
        # 无上下文时退化到全量模式（上限 max_items）
        return _fallback(mem, max_items)
    
    scored = {
        "avoids": [],
        "prefers": [],
        "habits": [],
    }
    
    for rule in mem.get("rules", []):
        rtype = rule.get("type")
        if rtype not in ("avoid", "prefer", "user_habit"):
            continue
        
        match_score = score_match(rule.get("context", {}), user_context)
        
        target = {
            "avoid": "avoids",
            "prefer": "prefers",
            "user_habit": "habits",
        }.get(rtype)
        
        if target and match_score > 0.3:
            scored[target].append({
                "subject": rule.get("subject", ""),
                "reason": rule.get("reason", ""),
                "score": round(match_score, 2),
            })
    
    # 按匹配度排序，截断
    for key in scored:
        scored[key].sort(key=lambda x: x["score"], reverse=True)
        scored[key] = scored[key][:max_items]
    
    scored["total_scored"] = sum(len(v) for v in scored.values() if isinstance(v, list))
    all_scores = [r["score"] for v in scored.values()
                  if isinstance(v, list) for r in v if isinstance(r, dict)]
    scored["max_score"] = max(all_scores, default=0.0)
    
    return scored


def _fallback(mem, max_items):
    """无上下文时的全量降级"""
    result = {"avoids": [], "prefers": [], "habits": [], "total_scored": 0, "max_score": 0.3}
    count = 0
    for rule in mem.get("rules", []):
        if count >= max_items * 3:
            break
        rtype = rule.get("type")
        target = {"avoid": "avoids", "prefer": "prefers", "user_habit": "habits"}.get(rtype)
        if target:
            result[target].append({
                "subject": rule.get("subject", ""),
                "reason": rule.get("reason", "")[:60],
                "score": 0.3,
            })
            count += 1
    result["total_scored"] = count
    return result


def to_advisory(scored: dict) -> str:
    """将蒸馏结果转为自然语言建议（不超过 MAX_INJECTION_CHARS）"""
    lines = []
    char_count = 0
    
    sections = [
        ("avoids", "⚠️ 跨专家经验（相关性过滤）：建议避免", "  - {subject}（{reason}）"),
        ("prefers", "✅ 跨专家经验：可优先考虑", "  - {subject}（{reason}）"),
        ("habits", "👤 用户习惯", "  - {subject}"),
    ]
    
    for key, title, fmt in sections:
        items = scored.get(key, [])
        if items:
            section = [title]
            for item in items:
                line = fmt.format(**item)
                section.append(line)
            section_text = "\n".join(section) + "\n"
            if char_count + len(section_text) > MAX_INJECTION_CHARS:
                break
            lines.extend(section)
            char_count += len(section_text)
    
    if not lines:
        return ""
    
    advisory = "\n".join(lines)
    if len(advisory) > MAX_INJECTION_CHARS:
        advisory = advisory[:MAX_INJECTION_CHARS] + "\n..."
    
    return advisory


def inject(mem, peer_context: dict, user_context: dict = None) -> dict:
    """上下⽂蒸馏注入：替代 shared_experience_memory.inject_into_peer_context"""
    distilled = distill(mem, user_context or {})
    advisory = to_advisory(distilled)
    if advisory:
        peer_context["_distilled_experience"] = advisory
        peer_context["_distilled_stats"] = {
            "matched": distilled["total_scored"],
            "max_relevance": distilled["max_score"],
        }
    return peer_context
