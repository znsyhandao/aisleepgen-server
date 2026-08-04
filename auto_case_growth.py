"""
auto_case_growth.py — AISleepGen 测试用例自动生长引擎

核心：从线上真实失败的请求自动提取新测试用例追加到基线。

触发方式：
  python auto_case_growth.py                   # 主动扫描失败日志
  python auto_case_growth.py serve              # 常驻监控模式（watchdog）
  python auto_case_growth.py report             # 查看生长历史

原理：
  每次 quality_baseline.py run 跑完后对比结果 → 
  发现基线未覆盖的行为模式 → 
  自动生成新的测试用例追加到 test_cases.json
"""

import os, sys, json, re, time, hashlib
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BASELINE_DIR = os.path.join(PROJECT_ROOT, "data", "quality_baseline")
TEST_CASES_PATH = os.path.join(BASELINE_DIR, "test_cases.json")
HISTORY_PATH = os.path.join(BASELINE_DIR, "history.jsonl")
GROWTH_LOG_PATH = os.path.join(BASELINE_DIR, "growth_log.jsonl")
FAILURE_LOG_PATH = os.path.join(PROJECT_ROOT, "data", "audit_logs")
os.makedirs(BASELINE_DIR, exist_ok=True)


def _load_test_cases() -> list:
    """加载当前测试用例"""
    if not os.path.exists(TEST_CASES_PATH):
        return []
    try:
        with open(TEST_CASES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_test_cases(cases: list):
    """保存测试用例"""
    with open(TEST_CASES_PATH, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)


def _existing_keywords(cases: list) -> set:
    """从已有用例提取关键词集，避免重复"""
    keywords = set()
    for c in cases:
        msg = c.get("input", {}).get("message", "")
        # 提取核心词
        for word in re.findall(r'[\u4e00-\u9fff]{2,}', msg):
            keywords.add(word)
    return keywords


def _scan_history_for_new_patterns() -> list:
    """从基线历史记录中扫描未覆盖的模式"""
    if not os.path.exists(HISTORY_PATH):
        return []
    
    failures = []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    details = rec.get("details", [])
                    for d in details:
                        if not d.get("passed"):
                            failures.append({
                                "test_name": d.get("test_name", "unknown"),
                                "test_id": d.get("test_id", ""),
                                "issues": d.get("issues", []),
                                "timestamp": rec.get("timestamp", ""),
                            })
                except Exception:
                    pass
    except Exception:
        return []
    
    return failures


def _find_new_message_patterns(cases: list, failures: list) -> list:
    """从失败记录中发现基线未覆盖的输入模式"""
    existing_kw = _existing_keywords(cases)
    
    # 分析失败原因→推断缺失的测试类型
    missing_types = set()
    
    for f in failures:
        for issue in f.get("issues", []):
            issue_lower = issue.lower()
            tid = f.get("test_id", "")
            
            # 评分超范围 → 需要边界值用例
            if "评分" in issue:
                missing_types.add(("boundary", "边界值测试——极端评分输入"))
            
            # 质量标签不符 → 需要更多质量标签用例
            if "质量标签" in issue:
                missing_types.add(("quality_edge", "质量标签边界——混合质量描述"))
            
            # 维度不足 → 需要稀疏数据用例
            if "维度不足" in issue:
                missing_types.add(("sparse", "稀疏数据——信息不足以计算维度"))
            
            # 调用异常 → 需要异常输入用例
            if "异常" in issue_lower or "error" in issue_lower:
                missing_types.add(("error_input", "异常输入——特殊字符/格式错误"))
    
    # 从已有用例中推理缺失的主题领域
    all_messages = [c.get("input", {}).get("message", "") for c in cases]
    all_text = " ".join(all_messages)
    
    # 检查是否覆盖了关键睡眠主题
    key_topics = {
        "nap": ["午睡", "小睡", "打盹"],
        "exercise": ["运动", "锻炼", "跑步"],
        "caffeine": ["咖啡", "茶", "咖啡因"],
        "dream": ["梦", "噩梦"],
        "snore": ["打鼾", "打呼噜", "呼吸暂停"],
        "travel": ["时差", "出差", "旅游"],
        "age": ["老人", "小孩", "青少年", "年龄"],
        "temperature": ["温度", "热", "冷", "空调"],
        "noise": ["噪音", "吵", "安静"],
    }
    
    new_meta_cases = []
    for topic, keywords in key_topics.items():
        covered = any(kw in all_text for kw in keywords)
        if not covered:
            # 生成一个代表这个主题的新用例
            if topic == "nap":
                new_meta_cases.append({
                    "id": f"auto_nap_{len(cases)}",
                    "name": "午睡影响睡眠",
                    "input": {"message": "下午睡了2小时午觉，晚上到2点都睡不着", "history": []},
                    "expect": {"score_min": 20, "score_max": 65,
                               "quality_acceptable": ["一般","较差","需要改善"],
                               "min_dimensions_computed": 3},
                    "weight": 0.7,
                    "tags": ["auto_grown"],
                })
            elif topic == "exercise":
                new_meta_cases.append({
                    "id": f"auto_exercise_{len(cases)}",
                    "name": "运动后睡眠",
                    "input": {"message": "昨晚跑步5公里，11点睡到6点半，深睡感觉特别多", "history": []},
                    "expect": {"score_min": 40, "score_max": 90,
                               "quality_acceptable": ["优秀","良好","一般","较差"],
                               "min_dimensions_computed": 0},
                    "weight": 0.7,
                    "tags": ["auto_grown"],
                })
            elif topic == "caffeine":
                new_meta_cases.append({
                    "id": f"auto_caffeine_{len(cases)}",
                    "name": "咖啡因影响",
                    "input": {"message": "晚上喝了杯咖啡，躺床上脑壳清醒得很", "history": []},
                    "expect": {"score_min": 15, "score_max": 65,
                               "quality_acceptable": ["较差","需要改善","一般"],
                               "min_dimensions_computed": 0},
                    "weight": 0.7,
                    "tags": ["auto_grown"],
                })
            elif topic == "dream":
                new_meta_cases.append({
                    "id": f"auto_dream_{len(cases)}",
                    "name": "梦境描述",
                    "input": {"message": "昨晚做了很多梦，感觉睡得不踏实，但实际睡了8小时", "history": []},
                    "expect": {"score_min": 30, "score_max": 80,
                               "quality_acceptable": ["较差","一般","良好"],
                               "min_dimensions_computed": 0},
                    "weight": 0.6,
                    "tags": ["auto_grown"],
                })
            elif topic == "snore":
                new_meta_cases.append({
                    "id": f"auto_snore_{len(cases)}",
                    "name": "打鼾/呼吸暂停",
                    "input": {"message": "老公说我打鼾声音很大，有时感觉呼吸停了", "history": []},
                    "expect": {"score_min": 20, "score_max": 60,
                               "quality_acceptable": ["较差","需要改善","一般"],
                               "min_dimensions_computed": 3},
                    "weight": 0.8,
                    "tags": ["auto_grown"],
                })
            elif topic == "travel":
                new_meta_cases.append({
                    "id": f"auto_travel_{len(cases)}",
                    "name": "时差/旅行",
                    "input": {"message": "出差倒时差，连续三天每天只睡4小时", "history": []},
                    "expect": {"score_min": 10, "score_max": 65,
                               "quality_acceptable": ["较差","需要改善","一般"],
                               "min_dimensions_computed": 0},
                    "weight": 0.6,
                    "tags": ["auto_grown"],
                })
            elif topic == "temperature":
                new_meta_cases.append({
                    "id": f"auto_temp_{len(cases)}",
                    "name": "温度/环境",
                    "input": {"message": "房间太热了一晚上翻来覆去，开了空调才好点", "history": []},
                    "expect": {"score_min": 25, "score_max": 65,
                               "quality_acceptable": ["一般","较差","需要改善"],
                               "min_dimensions_computed": 3},
                    "weight": 0.6,
                    "tags": ["auto_grown"],
                })
    
    return new_meta_cases


def run_growth() -> dict:
    """运行测试生长流程"""
    cases = _load_test_cases()
    failures = _scan_history_for_new_patterns()
    
    # 从失败中识别新模式（暂未实现——需要更深入的分析）
    # 先从主题覆盖生长开始
    
    new_cases = _find_new_message_patterns(cases, failures)
    existing_ids = {c["id"] for c in cases}
    truly_new = [c for c in new_cases if c["id"] not in existing_ids]
    
    if truly_new:
        cases.extend(truly_new)
        _save_test_cases(cases)
    
    # 记录生长日志
    growth_record = {
        "timestamp": datetime.now().isoformat(),
        "total_before": len(cases) - len(truly_new),
        "grown": len(truly_new),
        "total_after": len(cases),
        "new_ids": [c["id"] for c in truly_new],
        "failure_count": len(failures),
    }
    
    with open(GROWTH_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(growth_record, ensure_ascii=False) + "\n")
    
    return growth_record


def print_growth_report():
    """打印生长报告"""
    growths = []
    if os.path.exists(GROWTH_LOG_PATH):
        with open(GROWTH_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        growths.append(json.loads(line))
                    except Exception:
                        pass
    
    print("=" * 50)
    print("  AISleepGen 测试用例生长史")
    print("=" * 50)
    print()
    
    if not growths:
        print("  尚无生长记录")
        return
    
    total_grown = sum(g.get("grown", 0) for g in growths)
    print(f"  🌱 累计生长: {total_grown} 个用例")
    print(f"  历史记录: {len(growths)} 次")
    print()
    
    for i, g in enumerate(growths[-10:]):
        ts = g.get("timestamp", "?")[:19]
        grown = g.get("grown", 0)
        total = g.get("total_after", 0)
        before = g.get("total_before", 0)
        print(f"  #{i+1:2d} {ts} | +{grown} | {before}→{total}")
        for nid in g.get("new_ids", []):
            print(f"       新增: {nid}")
    
    print()
    # 显示当前所有用例
    cases = _load_test_cases()
    print(f"  当前基线: {len(cases)} 个用例")
    for c in cases:
        tags = c.get("tags", [])
        tag_str = f" [{','.join(tags)}]" if tags else ""
        print(f"    {c['id']:<45} {c['name']}{tag_str}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "report":
            print_growth_report()
        else:
            print(f"未知命令: {cmd}")
            sys.exit(1)
    else:
        result = run_growth()
        print(f"🌱 测试生长完成: +{result['grown']} 个用例 (总计 {result['total_after']})")
        for nid in result["new_ids"]:
            print(f"  新增: {nid}")
