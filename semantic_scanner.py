"""
semantic_scanner.py — AISleepGen 语义理解扫描引擎 (L1→L5)

核心能力：
  1. AST 解析 Python 源码，构建函数调用图
  2. 检测改动影响范围：改了 X 函数 → 哪些用例依赖 X
  3. 智能降噪：同样的 api_key 在不同上下文有不同严重级别
  4. 输出：标记高风险用例 ID + 建议优先重跑

用法：
  python semantic_scanner.py                  # 增量扫描（对比上次 git HEAD~1）
  python semantic_scanner.py full             # 全量扫描
  python semantic_scanner.py map              # 打印当前调用图
  python semantic_scanner.py trace <func>     # 追踪某函数的影响路径

与 quality_baseline.py 集成：
  run_baseline(semantic=semantic_scan) → 
  priority_runs = semantic_scan['affected_tests'] → 
  优先跑这些 + 跑完重点对比

与 self_evolve.py L1 的关系：
  不替代原有正则扫描，而是叠加语义层输出，帮助门禁做智能决策
"""

import os, sys, ast, json, subprocess, re
from collections import defaultdict
from typing import Dict, Set, List

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SEMANTIC_CACHE = os.path.join(PROJECT_ROOT, "data", "self_evolve", "semantic_cache.json")
TEST_CASES_PATH = os.path.join(PROJECT_ROOT, "data", "quality_baseline", "test_cases.json")


# ====================================================================
# 调用图构建
# ====================================================================

def build_call_graph(files: List[str] = None) -> dict:
    """构建函数调用图
    
    返回 {
        "functions": {"module.func": {"calls": ["module.func2", ...], "called_by": [...], "line": 123}},
        "modules": {"module_name": {"defines": ["func1", ...], "imports": ["module2", ...]}},
        "api_handlers": {"POST /api/sleep/world-step": {"handler": "module.func", "line": 456}},
    }
    """
    if files is None:
        files = [os.path.join(PROJECT_ROOT, f) for f in os.listdir(PROJECT_ROOT)
                 if f.endswith(".py") and os.path.isfile(os.path.join(PROJECT_ROOT, f))
                 and f not in ("post_edit_hook.py", "quality_baseline.py")]
    
    graph = {
        "functions": {},
        "modules": {},
        "api_handlers": {},
        "test_bindings": {},
    }
    
    for fp in files:
        mname = os.path.splitext(os.path.basename(fp))[0]
        graph["modules"][mname] = {"defines": [], "imports": []}
        
        try:
            with open(fp, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=fp)
        except SyntaxError:
            continue
        
        # 第一遍：收集所有导入
        imports = _collect_imports(tree)
        graph["modules"][mname]["imports"] = list(imports.keys())
        
        # 第二遍：收集所有函数定义 + 调用
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fqn = f"{mname}.{node.name}"
                graph["modules"][mname]["defines"].append(fqn)
                
                # 提取函数体中的调用
                calls = _extract_calls(node, mname)
                called_by = []  # 反向填充稍后做
                
                graph["functions"][fqn] = {
                    "module": mname,
                    "name": node.name,
                    "line": node.lineno,
                    "calls": list(calls),
                    "called_by": [],
                    "api_path": _detect_api_handler(node),
                    "is_test": bool(re.match(r'^(test|auto_|edge_|mutation_)', node.name)),
                    "has_annotation": bool(node.returns),
                    "imports_used": [imp for imp, names in imports.items() for n in names 
                                    if _is_used_in_node(n, node)],
                }
                
                if graph["functions"][fqn]["api_path"]:
                    graph["api_handlers"][graph["functions"][fqn]["api_path"]] = {
                        "handler": fqn, "line": node.lineno
                    }
    
    # 反向填充 called_by
    for fqn, info in graph["functions"].items():
        for callee in info["calls"]:
            if callee in graph["functions"]:
                graph["functions"][callee]["called_by"].append(fqn)
    
    return graph


def _collect_imports(tree: ast.Module) -> Dict[str, List[str]]:
    """收集所有 import 语句"""
    imports = defaultdict(list)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.name] = ["*"]
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names = [a.name for a in node.names]
                imports[node.module] = names
    return dict(imports)


def _extract_calls(func_node: ast.FunctionDef, module: str) -> Set[str]:
    """提取函数体内的所有调用"""
    calls = set()
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                # obj.method()
                calls.add(f"{module}.{node.func.attr}")
                calls.add(node.func.attr)
            elif isinstance(node.func, ast.Name):
                # func()
                calls.add(node.func.id)
    return calls


def _detect_api_handler(func_node: ast.FunctionDef) -> str:
    """检测函数是否为 API handler 并返回如 'POST /api/sleep/xxx'"""
    api_path = None
    for node in ast.walk(func_node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value
            if s.startswith("/api/"):
                # 查找上层是否有 POST/GET
                api_path = s
            elif s in ("POST", "GET") and api_path:
                return f"{s} {api_path}"
    return api_path


def _is_used_in_node(name: str, node: ast.FunctionDef) -> bool:
    """检查 name 是否在函数体内使用"""
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id == name:
            return True
    return False


# ====================================================================
# 差异分析
# ====================================================================

def diff_analysis(all_files: List[str] = None) -> dict:
    """Git diff 分析：HEAD~1 vs HEAD
    
    返回 {file: {changes: [{type: A/M/D, name: funcname, line: N}]}}
    """
    if all_files is None:
        all_files = [os.path.join(PROJECT_ROOT, f) for f in os.listdir(PROJECT_ROOT)
                     if f.endswith(".py") and os.path.isfile(os.path.join(PROJECT_ROOT, f))]
    
    changes = {}
    
    # Git diff 输出
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--", *[os.path.basename(p) for p in all_files[:20]]],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=10
        )
        diff_text = result.stdout
    except Exception:
        diff_text = ""
    
    if not diff_text:
        # 没有 git 历史 → 对所有 main.py 做全量扫描
        return {"type": "full_scan", "reason": "no git history"}
    
    current_file = None
    for line in diff_text.split("\n"):
        if line.startswith("+++ b/"):
            current_file = os.path.basename(line[6:])
            if current_file not in changes:
                changes[current_file] = {"adds": [], "removes": [], "modified_functions": []}
        elif line.startswith("@@") and current_file:
            # hunk header: @@ -old_start,old_count +new_start,new_count @@ ... function_name
            m = re.search(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@.*?(?:def (\w+)|class (\w+))', line)
            if m:
                func_name = m.group(2) or m.group(3) or "unknown"
                line_num = int(m.group(1))
                changes[current_file]["modified_functions"].append({
                    "name": func_name, "line": line_num
                })
    
    return {
        "type": "git_diff",
        "changed_files": {k: v for k, v in changes.items() if v["adds"] or v["removes"] or v["modified_functions"]},
    }


# ====================================================================
# 影响传播
# ====================================================================

def trace_impact(change_info: dict, graph: dict, test_cases_path: str = None) -> dict:
    """追踪改动的影响：改了 X → 影响 Y → 影响测试用例 Z → 算优先级"""
    from collections import Counter
    if test_cases_path is None:
        test_cases_path = "D:/AISleepGen_Optimized/data/quality_baseline/test_cases.json"
    
    affected_functions = set()
    affected_tests = set()
    affected_api_handlers = set()
    propagation_paths = []
    call_depth = {}  # fqn -> min call depth from changed function
    
    if change_info.get("type") == "full_scan":
        return {"type": "full_scan", "suggestion": "没有 git 历史，建议全量跑基线"}
    
    for fname, info in change_info.get("changed_files", {}).items():
        module_name = os.path.splitext(fname)[0]
        
        for func_info in info.get("modified_functions", []):
            func_name = func_info["name"]
            fqn = f"{module_name}.{func_name}"
            affected_functions.add(fqn)
            
            # BFS 传播：找到所有直接/间接调用者
            visited = {fqn}
            queue = [(fqn, 0)]  # (fqn, depth)
            call_depth[fqn] = 0
            
            while queue:
                current, depth = queue.pop(0)
                func_data = graph["functions"].get(current, {})
                for caller in func_data.get("called_by", []):
                    if caller not in visited:
                        visited.add(caller)
                        new_depth = depth + 1
                        call_depth[caller] = min(call_depth.get(caller, 999), new_depth)
                        queue.append((caller, new_depth))
                        
                        # 如果是测试函数
                        if graph["functions"].get(caller, {}).get("is_test"):
                            affected_tests.add(caller)
            
            if len(visited) > 1:
                propagation_paths.append({"from": fqn, "through": list(visited)[1:-1], "to": list(affected_tests)})
    
    # ===== 计算优先级 =====
    priority_tests = []
    
    # 加载测试用例ID到名称的映射
    test_id_to_name = {}
    try:
        import json
        if os.path.exists(test_cases_path):
            with open(test_cases_path, "r", encoding="utf-8") as f:
                for tc in json.load(f):
                    test_id_to_name[tc["id"]] = tc.get("name", tc["id"])
    except Exception:
        pass
    
    for test_fn in sorted(affected_tests):
        depth = call_depth.get(test_fn, 99)
        # 深度越低 → 影响越直接 → 优先级越高
        if depth <= 1:
            priority = "CRITICAL"
        elif depth <= 3:
            priority = "HIGH"
        elif depth <= 6:
            priority = "MEDIUM"
        else:
            priority = "LOW"
        
        # 映射到 test_cases.json 中的 ID
        test_id = test_fn.split(".")[-1] if "." in test_fn else test_fn
        
        priority_tests.append({
            "function": test_fn,
            "test_id": test_id,
            "test_name": test_id_to_name.get(test_id, test_id),
            "priority": priority,
            "call_depth": depth,
        })
    
    return {
        "impacted_functions": sorted(affected_functions) if affected_functions else [],
        "impacted_api_handlers": sorted(affected_api_handlers) if affected_api_handlers else [],
        "priority_tests": sorted(priority_tests, key=lambda x: (-ord(x["priority"][0]), x["call_depth"])),
        "propagation_paths": propagation_paths,
    }


# ====================================================================
# 测试用例绑定
# ====================================================================

def bind_tests_to_functions(graph: dict, test_cases_file: str = None) -> dict:
    """将测试用例绑定到其依赖的函数"""
    if test_cases_file is None:
        test_cases_file = TEST_CASES_PATH
    
    test_bindings = defaultdict(set)
    
    # 从测试用例输入关键词推测其依赖的函数
    test_cases = []
    if os.path.exists(test_cases_file):
        try:
            with open(test_cases_file, "r", encoding="utf-8") as f:
                test_cases = json.load(f)
        except Exception:
            pass
    
    for case in test_cases:
        cid = case.get("id", "?")
        msg = case.get("input", {}).get("message", "")
        
        # 根据消息内容推测依赖哪些模块
        msg_lower = msg.lower()
        depend_modules = set()
        
        if any(kw in msg_lower for kw in ["深睡", "浅睡", "rem", "睡眠阶段", "睡着", "醒来", "起夜"]):
            depend_modules.update(("sleep_stage_analyzer", "sleep_world_model", "world_model", "extractor"))
        if any(kw in msg_lower for kw in ["hrv", "心率", "呼吸", "heart"]):
            depend_modules.update(("hrv_analyzer", "sleep_world_model", "world_model"))
        if any(kw in msg_lower for kw in ["焦虑", "压力", "情绪", "心情", "stress"]):
            depend_modules.update(("emotion_analyzer", "sleep_world_model", "world_model"))
        if any(kw in msg_lower for kw in ["设备", "手环", "手表", "华为", "apple"]):
            depend_modules.update(("huawei_health_kit", "device_importer", "sleep_world_model"))
        if any(kw in msg_lower for kw in ["打鼾", "打呼"]):
            depend_modules.update(("sleep_stage_analyzer", "sleep_world_model"))
        if any(kw in msg_lower for kw in ["咖啡", "酒", "茶"]):
            depend_modules.update(("substance_tracker", "emotion_analyzer"))
        if any(kw in msg_lower for kw in ["运动", "锻炼", "跑步"]):
            depend_modules.update(("activity_tracker", "sleep_world_model"))
        
        if not depend_modules:
            depend_modules.add("sleep_world_model")
        
        # 从模块名 → 实际函数名
        for mname in depend_modules:
            if mname in graph.get("modules", {}):
                for fqn in graph["modules"][mname].get("defines", []):
                    test_bindings[fqn].add(cid)
                    test_bindings[cid].add(fqn)
    
    return {k: list(v) for k, v in test_bindings.items()}


# ====================================================================
# 智能评分：根据上下文判断严重性
# ====================================================================

def contextual_severity(pattern_id: str, line_text: str, surrounding_lines: list) -> str:
    """根据上下文判断模式的实际严重性
    
    同一个 api_key 在不同的上下文中严重性不同：
      - api_key = 'ghp_xxx' 在 api_client.py → CRITICAL
      - line.startswith('API_KEY=') 读取 .env → INFO
      - os.environ.get('API_KEY') → SAFE
    """
    joined = " ".join(surrounding_lines).lower()
    
    # 安全模式
    if any(kw in joined for kw in ["os.environ", "env", "getenv"]):
        return "INFO"
    if "startswith" in joined and ".env" in joined:
        return "INFO"
    if "config" in joined and "load" in joined:
        return "INFO"
    if "# test" in joined or "# mock" in joined or "# placeholder" in joined:
        return "LOW"
    
    # 危险模式
    if pattern_id in ("hardcoded_secret",):
        if ".env" not in joined and "environ" not in joined:
            return "CRITICAL"
    
    return "MEDIUM"


# ====================================================================
# CLI
# ====================================================================

def print_call_graph_summary(graph: dict):
    """打印调用图摘要"""
    print(f"调用图: {len(graph['functions'])} 函数, {len(graph['modules'])} 模块")
    print(f"API 处理函数: {len(graph['api_handlers'])} 个")
    
    # 高扇出函数（被最多地方调用的）
    by_calls = sorted(graph["functions"].items(), 
                     key=lambda x: len(x[1]["called_by"]), reverse=True)[:5]
    print(f"\n被调用最多的函数:")
    for fqn, info in by_calls:
        if info["called_by"]:
            print(f"  {fqn:<50} ← {len(info['called_by'])} 处调用")
    
    # API handler 列表
    if graph["api_handlers"]:
        print(f"\nAPI 处理器:")
        for path, info in graph["api_handlers"].items():
            print(f"  {path:<45} → {info['handler']}")


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "map":
            graph = build_call_graph()
            print_call_graph_summary(graph)
        elif cmd == "trace":
            if len(sys.argv) > 2:
                target = sys.argv[2]
                graph = build_call_graph()
                # 找到匹配的函数
                for fqn, info in graph["functions"].items():
                    if target.lower() in fqn.lower():
                        print(f"\n追踪: {fqn} (line {info['line']})")
                        print(f"  调用: {info['calls'][:10]}")
                        print(f"  被调用: {info['called_by'][:10]}")
            else:
                print("用法: python semantic_scanner.py trace <函数名>")
        elif cmd == "context":
            if len(sys.argv) > 2:
                fp = sys.argv[2]
                try:
                    lines = open(fp, "r", encoding="utf-8").readlines()
                except Exception:
                    lines = []
                target_sev = contextual_severity("hardcoded_secret", "", lines[:10])
                print(f"上下文严重性: {target_sev}")
        else:
            print("用法: semantic_scanner.py [map|trace <f>|context <f>]")
    else:
        # 增量扫描
        graph = build_call_graph()
        changes = diff_analysis()
        impact = trace_impact(changes, graph)
        
        print("=" * 50)
        print("  AISleepGen 语义理解扫描")
        print("=" * 50)
        print()
        
        if impact.get("impacted_functions"):
            print(f"受影响函数: {len(impact['impacted_functions'])}")
            for f in impact["impacted_functions"][:10]:
                print(f"  • {f}")
        
        pt = impact.get("priority_tests", [])
        if pt:
            print(f"\n受影响测试(按优先级):")
            for t in pt[:15]:
                icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "⚪"}.get(t["priority"], "⚪")
                print(f"  {icon} [{t['priority']:<8}] {t['test_name']:<30} (深度={t['call_depth']})")
            if len(pt) > 15:
                print(f"  ...还有 {len(pt)-15} 个")
        
        if impact.get("impacted_api_handlers"):
            print(f"\n受影响 API: {len(impact['impacted_api_handlers'])}")
            for h in impact["impacted_api_handlers"]:
                print(f"  • {h}")
        
        if not pt and not impact.get("impacted_functions"):
            print("  无增量改动影响。首次运行或 git 历史不足。")
            print_call_graph_summary(graph)
        
        # 测试绑定
        bindings = bind_tests_to_functions(graph)
        print(f"\n测试-函数绑定: {len(bindings)} 个映射")


if __name__ == "__main__":
    main()
