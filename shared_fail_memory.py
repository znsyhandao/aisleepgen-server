"""
shared_fail_memory.py — 跨专家共享失败记忆

类似 MopMonk 的结构化漏洞记忆：
- 一个专家验证的失败策略，记录下来让其他专家自动避开
- 比如"放松训练对焦虑型失眠无效"被 AI 行为专家发现后，CBT 专家不会再推荐
"""
import os, json, time
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(PROJECT_ROOT, "data", "shared_fail_memory.json")

# 内存缓存
_fail_cache = None

def _ensure_dir():
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)

def load() -> dict:
    """加载共享失败记忆"""
    global _fail_cache
    if _fail_cache is not None:
        return _fail_cache
    _ensure_dir()
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                _fail_cache = json.load(f)
                return _fail_cache
        except:
            pass
    _fail_cache = {"failures": [], "rules": [], "updated_at": ""}
    return _fail_cache

def save():
    """持久化"""
    global _fail_cache
    if _fail_cache is None:
        return
    _fail_cache["updated_at"] = datetime.now().isoformat()
    _ensure_dir()
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(_fail_cache, f, ensure_ascii=False, indent=2)

def record_failure(expert_name: str, intervention: str, 
                   user_context: str, outcome: str):
    """记录一次失败：某专家在某场景下的某个干预无效"""
    mem = load()
    entry = {
        "expert": expert_name,
        "intervention": intervention,
        "user_context": user_context[:100],
        "outcome": outcome[:100],
        "recorded_at": datetime.now().isoformat(),
    }
    # 去重：同样专家+同样干预不重复记录（不同上下文合并）
    found = None
    for existing in mem["failures"]:
        if (existing["expert"] == entry["expert"] and
            existing["intervention"] == entry["intervention"]):
            existing["count"] = existing.get("count", 1) + 1
            existing["last_seen"] = entry["recorded_at"]
            existing["outcome"] = entry["outcome"]
            found = existing
            break
    if found is None:
        entry["count"] = 1
        entry["last_seen"] = entry["recorded_at"]
        mem["failures"].append(entry)
        found = entry
    
    # 当一个失败出现 2 次以上，自动升格为规则
    if found["count"] >= 2:
        _promote_to_rule(mem, found)
    save()

def _promote_to_rule(mem: dict, entry: dict):
    """从失败升格为规则"""
    rule = {
        "type": "avoid",
        "intervention": entry["intervention"],
        "reason": f"{entry['expert']}报告此干预在类似场景下{entry['count']}次无效",
        "evidence": entry["outcome"],
        "created_at": datetime.now().isoformat(),
    }
    # 去重
    for r in mem["rules"]:
        if r["intervention"] == rule["intervention"]:
            return
    mem["rules"].append(rule)

def get_avoid_list() -> list:
    """获取当前所有应避免的干预/策略列表"""
    mem = load()
    return [r["intervention"] for r in mem.get("rules", [])]

def get_peer_advisory() -> str:
    """生成给专家的跨会诊提示（自然语言）"""
    mem = load()
    if not mem.get("rules"):
        return ""
    rules = mem["rules"]
    lines = ["⚠️ 跨专家失败记忆：以下策略在历史中被标记为低效，建议避免："]
    for r in rules[-5:]:  # 只给最近5条，避免上下文爆炸
        lines.append(f"- {r['intervention']} ({r['reason']})")
    return "\n".join(lines)

def get_status() -> dict:
    """查看状态"""
    mem = load()
    return {
        "total_failures": len(mem.get("failures", [])),
        "total_rules": len(mem.get("rules", [])),
        "rules": [r["intervention"] for r in mem.get("rules", [])],
    }

def inject_into_peer_context(peer_context: dict) -> dict:
    """在第二轮交叉会诊时，把失败记忆注入peer_findings"""
    advisory = get_peer_advisory()
    if advisory:
        peer_context["_shared_fail_memory"] = advisory
    return peer_context

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        s = get_status()
        print(f"Failures: {s['total_failures']}")
        print(f"Rules: {s['total_rules']}")
        if s['rules']:
            print("Active rules:")
            for r in s['rules']:
                print(f"  - {r}")
    else:
        # Demo
        print("Demo: recording failures...")
        record_failure("AI行为专家", "腹式呼吸放松训练", "焦虑型失眠患者", "用户反馈无效，平静不下来")
        record_failure("AI行为专家", "腹式呼吸放松训练", "焦虑型失眠患者", "连续3天无效")
        record_failure("CBT专家", "睡眠限制疗法", "慢性失眠", "用户依从性差，未能坚持")
        s = get_status()
        print(f"Failures: {s['total_failures']}")
        print(f"Rules: {s['total_rules']}")
        print(f"Get avoid list: {get_avoid_list()}")
        print(f"Advisory:\n{get_peer_advisory()}")
