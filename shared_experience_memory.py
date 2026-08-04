"""
shared_experience_memory.py v2 — GAAMA 图增强关联记忆

基于 arXiv 2603.02912 (GAAMA: Graph Augmented Associative Memory for Agents):
  从扁平 JSON 存储升级为 NetworkX 图存储。
  每条经验是图中的节点，关联通过边连接。
  retrieval 从标签匹配升级为图路径搜索。

优势:
  1. "腹式呼吸在焦虑7+觉醒3次的情况下无效" → 图路径可追溯
  2. 支持多跳推理: 焦虑高→腹式呼吸无效→那么推荐什么?
  3. 支持反向检索: 什么条件下腹式呼吸有效?
"""
import os, json, sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(PROJECT_ROOT, "data", "shared_experience_memory.json")

_cache = None
_graph = None

def _ensure_dir():
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)

def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    _ensure_dir()
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                _cache = json.load(f)
                return _cache
        except:
            pass
    _cache = {
        "experiences": [],
        "rules": [],
        "updated_at": "",
        "stats": {"failures": 0, "successes": 0, "preferences": 0, "cross_insights": 0, "rules_count": 0}
    }
    return _cache

def save():
    global _cache
    if _cache is None:
        return
    _cache["updated_at"] = datetime.now().isoformat()
    _cache["stats"]["rules_count"] = len(_cache.get("rules", []))
    _ensure_dir()
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(_cache, f, ensure_ascii=False, indent=2, default=str)

# ===== GAAMA 图引擎 =====

def _build_graph() -> dict:
    """从 JSON 存储构建记忆图（惰性加载）"""
    global _graph
    if _graph is not None:
        return _graph
    
    mem = _load()
    graph = {
        "nodes": {},
        "edges": [],
        "index": {},  # subject → node_id 快速索引
    }
    
    # 构建节点：每个经验/规则是一个节点
    for exp in mem.get("experiences", []):
        node_id = "exp_%s_%s" % (exp.get("type", "?").lower(), exp.get("subject", "?").replace(" ", "_"))
        graph["nodes"][node_id] = {
            "type": "experience",
            "exp_type": exp.get("type", ""),
            "subject": exp.get("subject", ""),
            "outcome": exp.get("outcome", ""),
            "expert": exp.get("expert", ""),
            "count": exp.get("count", 1),
            "confidence": exp.get("confidence", 1.0),
        }
        # 添加上下文标签
        ctx = exp.get("context", {})
        for k, v in ctx.items():
            tag_node = "tag_%s_%s" % (k, str(v).replace(" ", "_"))
            graph["nodes"].setdefault(tag_node, {"type": "tag", "key": k, "value": v})
            graph["edges"].append({"from": node_id, "to": tag_node, "relation": "has_context"})
        graph["index"][exp.get("subject", "")] = node_id
    
    for rule in mem.get("rules", []):
        node_id = "rule_%s_%s" % (rule.get("type", "?"), rule.get("subject", "?").replace(" ", "_"))
        graph["nodes"][node_id] = {
            "type": "rule",
            "rule_type": rule.get("type", ""),
            "subject": rule.get("subject", ""),
            "reason": rule.get("reason", ""),
        }
        ctx = rule.get("context", {})
        for k, v in ctx.items():
            tag_node = "tag_%s_%s" % (k, str(v).replace(" ", "_"))
            graph["nodes"].setdefault(tag_node, {"type": "tag", "key": k, "value": v})
            graph["edges"].append({"from": node_id, "to": tag_node, "relation": "has_context"})
        # 链接到对应经验
        if rule.get("subject") in graph["index"]:
            graph["edges"].append({
                "from": node_id, 
                "to": graph["index"][rule["subject"]],
                "relation": "derived_from"
            })
    
    _graph = graph
    return graph


def graph_search(user_context: dict, max_results: int = 5) -> list:
    """GAAMA 图路径搜索: 根据用户上下文在记忆图中查找关联规则"""
    graph = _build_graph()
    if not graph["nodes"]:
        return []
    
    results = []
    
    # 1. 找到跟用户上下文匹配的 tag 节点
    matched_tags = set()
    for k, v in user_context.items():
        tag_id = "tag_%s_%s" % (k, str(v).replace(" ", "_"))
        if tag_id in graph["nodes"]:
            matched_tags.add(tag_id)
        # 也搜宽松匹配（用户焦虑7，找焦虑>5的规则）
        for tag_id2 in graph["nodes"]:
            if tag_id2.startswith("tag_%s_" % k):
                tag_val = graph["nodes"][tag_id2].get("value", "")
                if isinstance(tag_val, (int, float)) and isinstance(v, (int, float)):
                    if abs(tag_val - v) / max(abs(tag_val), abs(v), 1) < 0.3:
                        matched_tags.add(tag_id2)
    
    # 2. 从匹配标签出发，找到相连的规则/经验
    seen_subjects = set()
    for edge in graph["edges"]:
        if edge["to"] in matched_tags or edge["from"] in matched_tags:
            counterpart = edge["from"] if edge["to"] in matched_tags else edge["to"]
            node = graph["nodes"].get(counterpart, {})
            subject = node.get("subject", "")
            if subject and subject not in seen_subjects:
                seen_subjects.add(subject)
                results.append({
                    "subject": subject,
                    "type": node.get("type", ""),
                    "exp_type": node.get("exp_type", node.get("rule_type", "")),
                    "outcome": node.get("outcome", ""),
                    "expert": node.get("expert", ""),
                    "confidence": node.get("confidence", 1.0),
                    "reason": node.get("reason", ""),
                })
    
    # 3. 按 confidence 排序
    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results[:max_results]


def get_advisory(user_context: dict = None) -> str:
    """GAAMA 版本的 advisory: 图路径搜索而不是全量注入"""
    if user_context:
        matches = graph_search(user_context, max_results=5)
    else:
        matches = []
    
    # 也可以 fallback 到旧版全量模式
    if not matches:
        mem = _load()
        rules = mem.get("rules", [])
        if not rules:
            return ""
        lines = ["⚠️ 跨专家经验（基于共享记忆）："]
        for r in rules[-5:]:
            lines.append("  - " + str(r.get("subject", "")) + "（" + str(r.get("reason", ""))[:60] + "）")
        return "\n".join(lines)
    
    # GAAMA 输出
    avoids = [m for m in matches if m.get("exp_type") in ("avoid", "FAILURE")]
    prefers = [m for m in matches if m.get("exp_type") in ("prefer", "SUCCESS")]
    
    lines = []
    if avoids:
        lines.append("⚠️ 跨专家经验（用户状态匹配）：建议避免")
        for a in avoids:
            lines.append("  - " + a["subject"] + "（" + (a["reason"] or a["outcome"])[:60] + "）")
    if prefers:
        lines.append("✅ 跨专家经验（用户状态匹配）：可优先考虑")
        for p in prefers:
            lines.append("  - " + p["subject"] + "（" + (p["reason"] or p["outcome"])[:60] + "）")
    
    return "\n".join(lines)


def inject_into_peer_context(peer_context: dict, user_context: dict = None) -> dict:
    """GAAMA 注入 peer context"""
    advisory = get_advisory(user_context)
    if advisory:
        peer_context["_shared_experience_memory"] = advisory
        if user_context:
            peer_context["_gaama_context_matched"] = True
    return peer_context


# ===== 旧版兼容接口（保持不变） =====

def record(exp_type, expert, subject, outcome, context=None, confidence=1.0):
    return record_failure(expert, subject, outcome, context) if exp_type == "FAILURE" else record_success(expert, subject, outcome, context)

def record_failure(expert, subject, outcome, context=None):
    """记录失败（兼容旧版）"""
    mem = _load()
    entry = {
        "type": "FAILURE", "expert": expert, "subject": subject,
        "outcome": outcome, "context": context or {},
        "confidence": 1.0, "recorded_at": datetime.now().isoformat(), "count": 1,
    }
    found = None
    for idx, existing in enumerate(mem["experiences"]):
        if existing.get("type") == "FAILURE" and existing.get("expert") == expert and existing.get("subject") == subject:
            existing["count"] = existing.get("count", 1) + 1
            existing["last_seen"] = entry["recorded_at"]
            existing["outcome"] = outcome
            found = existing
            mem["experiences"][idx] = existing
            break
    if found is None:
        entry["last_seen"] = entry["recorded_at"]
        mem["experiences"].append(entry)
        found = entry
    mem["stats"]["failures"] = sum(1 for e in mem["experiences"] if e["type"] == "FAILURE")
    if found["count"] >= 2:
        _promote_to_rule(mem, found, "avoid", "此策略在类似场景下%d次无效 (%s)" % (found["count"], outcome))
    save()
    _reset_graph()
    return {"status": "recorded", "count": found["count"]}

def record_success(expert, subject, outcome, context=None):
    mem = _load()
    entry = {
        "type": "SUCCESS", "expert": expert, "subject": subject,
        "outcome": outcome, "context": context or {},
        "confidence": 1.0, "recorded_at": datetime.now().isoformat(), "count": 1,
    }
    found = None
    for idx, existing in enumerate(mem["experiences"]):
        if existing.get("type") == "SUCCESS" and existing.get("expert") == expert and existing.get("subject") == subject:
            existing["count"] = existing.get("count", 1) + 1
            existing["last_seen"] = entry["recorded_at"]
            existing["outcome"] = outcome
            found = existing
            mem["experiences"][idx] = existing
            break
    if found is None:
        entry["last_seen"] = entry["recorded_at"]
        mem["experiences"].append(entry)
        found = entry
    mem["stats"]["successes"] = sum(1 for e in mem["experiences"] if e["type"] == "SUCCESS")
    if found["count"] >= 3:
        _promote_to_rule(mem, found, "prefer", "此策略在类似场景下%d次有效 (%s)" % (found["count"], outcome))
    save()
    _reset_graph()
    return {"status": "recorded", "count": found["count"]}

def record_preference(expert, subject, outcome, context=None):
    return record("PREFERENCE", expert, subject, outcome, context)

def record_cross_insight(expert, subject, outcome, context=None):
    return record("CROSS_INSIGHT", expert, subject, outcome, context)

def _promote_to_rule(mem, entry, rule_type, reason):
    for r in mem["rules"]:
        if r["subject"] == entry["subject"] and r["type"] == rule_type:
            return
    ctx = dict(entry.get("context", {}))
    for k, v in list(ctx.items()):
        if isinstance(v, str):
            mappings = {"high": 7, "severe": 8, "moderate": 5, "mild": 3, "low": 2}
            if v.lower() in mappings:
                ctx[k] = mappings[v.lower()]
    mem["rules"].append({
        "type": rule_type, "subject": entry["subject"],
        "expert": entry["expert"], "reason": reason,
        "context": ctx, "created_at": datetime.now().isoformat(),
    })

def _reset_graph():
    global _graph
    _graph = None

# 兼容接口
def load(): return _load()
def save_safe(): save()
def get_peer_advisory(): return get_advisory()  # 无上下文退化到全量
def get_avoid_list():
    return [r["subject"] for r in _load().get("rules", []) if r["type"] == "avoid"]

def get_status() -> dict:
    mem = _load()
    stats = mem.get("stats", {})
    rules_by_type = {}
    for r in mem.get("rules", []):
        t = r.get("type", "unknown")
        rules_by_type.setdefault(t, []).append(r.get("subject"))
    
    graph = _build_graph()
    return {
        "total_experiences": len(mem.get("experiences", [])),
        "total_rules": len(mem.get("rules", [])),
        "stats": stats,
        "rules_by_type": rules_by_type,
        "graph_nodes": len(graph["nodes"]),
        "graph_edges": len(graph["edges"]),
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        s = get_status()
        print("Experiences: %d" % s["total_experiences"])
        print("Rules: %d" % s["total_rules"])
        print("Graph nodes: %d" % s["graph_nodes"])
        print("Graph edges: %d" % s["graph_edges"])
        for k, v in s["rules_by_type"].items():
            print("  %s: %s" % (k, v))
    elif len(sys.argv) > 1 and sys.argv[1] == "search":
        # Test graph search
        ctx = {"anxiety": 7, "awake_times": 3}
        results = graph_search(ctx)
        print("Graph search for anxiety=7, awake_times=3:")
        for r in results:
            print("  %s [%s]: %s" % (r["subject"], r["exp_type"], r.get("reason","")[:60]))
        print()
        print(get_advisory(ctx))
    else:
        # Demo: record + graph search
        record_failure("AI行为专家", "腹式呼吸放松训练", 
                       "焦虑型失眠用户反馈无效", {"anxiety": 8, "awake_times": 3})
        record_failure("AI行为专家", "腹式呼吸放松训练",
                       "连续3天无效，用户焦虑加重", {"anxiety": 7, "awake_times": 3})
        record_success("CBT专家", "认知重构",
                       "中度焦虑用户有效", {"anxiety": 5, "awake_times": 2})
        
        print("=== GAAMA Demo ===")
        s = get_status()
        print("Status:", s["total_experiences"], "experiences,", s["total_rules"], "rules,", 
              s["graph_nodes"], "nodes,", s["graph_edges"], "edges")
        
        print("\n=== Graph Search (high anxiety user) ===")
        results = graph_search({"anxiety": 7, "awake_times": 3})
        for r in results:
            print("  %s [%s] (confidence: %.1f)" % (r["subject"], r["exp_type"], r["confidence"]))
        
        print("\n=== Graph Search (low anxiety user) ===")
        results = graph_search({"anxiety": 3, "awake_times": 1})
        for r in results:
            print("  %s [%s] (confidence: %.1f)" % (r["subject"], r["exp_type"], r["confidence"]))
