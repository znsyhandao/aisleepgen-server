"""
differential_regression.py — 差分回归（MopMonk启示 #1）

核心逻辑：
  门禁失败后 → 
  1. git diff 获取当前修改的文件列表
  2. 从 semantic_scanner 的调用图找到这些文件影响的函数
  3. 限制后续回归只跑这些函数相关的测试用例
  4. 输出"退化热区"报告

类似于 MopMonk 的「基于失败证据缩小搜索空间」:
  不仅知道"失败了"，还知道"失败跟哪些代码修改有关"。
"""
import os, sys, json, subprocess
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 语义扫描结果缓存
_CALL_GRAPH = None

def _load_call_graph() -> dict:
    """从 semantic_scanner 加载调用图"""
    global _CALL_GRAPH
    if _CALL_GRAPH is not None:
        return _CALL_GRAPH
    try:
        sys.path.insert(0, PROJECT_ROOT)
        from semantic_scanner import build_call_graph
        _CALL_GRAPH = build_call_graph()
        return _CALL_GRAPH
    except Exception as e:
        return {"error": str(e)}


def get_modified_files() -> list:
    """获取 git diff 修改的文件列表（无 git 则返回空）"""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--name-only"],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=10
        )
        if result.returncode == 0:
            files = [f.strip() for f in result.stdout.split("\n") if f.strip().endswith(".py")]
            # 过滤临时文件/测试文件/非核心文件
            filtered = [f for f in files if not f.startswith("_") and not f.startswith(".")]
            # 如果 diff 出太多文件（首次运行），降级为全量模式
            if len(filtered) > 10:
                return ["__full_scan__"]  # 全量标记
            return filtered
    except:
        pass
    return []


def get_affected_functions(modified_files: list) -> list:
    """从修改文件推导被影响的函数"""
    call_graph = _load_call_graph()
    if "error" in call_graph:
        return []
    
    affected = []
    for fname in modified_files:
        basename = os.path.basename(fname).replace(".py", "")
        # 从调用图中找到这个文件相关的函数
        for fn, info in call_graph.get("functions", {}).items():
            fn_file = info.get("file", "")
            if basename in fn_file:
                affected.append({"function": fn, "file": fn_file, "reason": "directly modified"})
            # 也找在这个文件里被调用的外部函数
            for caller in info.get("callers", []):
                if basename in caller.get("file", ""):
                    affected.append({"function": fn, "file": fn_file, 
                                    "called_by": caller.get("name"), "reason": "affected_by_caller"})
    
    # 去重
    seen = set()
    unique = []
    for a in affected:
        key = a["function"]
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


def get_affected_test_files(modified_files: list) -> list:
    """从修改文件推导应优先跑的测试"""
    call_graph = _load_call_graph()
    if "error" in call_graph:
        return list(modified_files)
    
    affected_tests = []
    test_function_map = call_graph.get("test_function_map", {})
    
    for fname in modified_files:
        basename = os.path.basename(fname).replace(".py", "")
        # 反向查找：哪个测试用到了这个文件中的函数
        for test_name, test_info in test_function_map.items():
            if not isinstance(test_info, dict):
                continue
            for func_ref in test_info.get("functions_used", []):
                if basename in func_ref.get("file", ""):
                    affected_tests.append({
                        "test": test_name,
                        "test_file": test_info.get("file", ""),
                        "reason": f"uses functions from {basename}",
                    })
    
    # 去重
    seen = set()
    unique_tests = []
    for t in affected_tests:
        key = t.get("test", t.get("test_file", ""))
        if key not in seen:
            seen.add(key)
            unique_tests.append(t)
    return unique_tests


def run_diff_regression(full_gate_result: dict) -> dict:
    """
    门禁失败时调用。
    返回退化热区报告，让后续门禁只跑相关用例。
    """
    modified = get_modified_files()
    
    if not modified:
        return {"type": "no_diff", "recommendation": "run_full", 
                "note": "无git diff信息，建议全量回归"}
    
    affected = get_affected_functions(modified)
    affected_tests = get_affected_test_files(modified)
    
    # 从门禁结果找出失败的测试
    failed_tests = []
    for tc in full_gate_result.get("results", {}).get("l0", {}).get("tests", []):
        if not tc.get("pass", True):
            failed_tests.append(tc)
    
    report = {
        "type": "differential",
        "timestamp": datetime.now().isoformat(),
        "modified_files": modified,
        "affected_functions": affected[:20],  # 只输出最新20条
        "affected_test_files": affected_tests[:20],
        "failed_tests": failed_tests,
        "recommendation": "run_focused",
        # 交叉分析：失败测试是否关联到修改文件
        "cross_analysis": _cross_analyze(modified, failed_tests),
        "total": {
            "modified": len(modified),
            "affected_functions": len(affected),
            "affected_tests": len(affected_tests),
            "failed": len(failed_tests),
        }
    }
    
    return report


def _cross_analyze(modified_files: list, failed_tests: list) -> dict:
    """交叉分析：失败测试是否确实跟修改文件相关"""
    if not modified_files or not failed_tests:
        return {"relevant": False, "reason": "missing data"}
    
    # 检查失败测试的名称是否跟修改文件有关联
    modified_names = [os.path.basename(f).replace(".py", "").replace("_", "").lower() 
                      for f in modified_files]
    
    relevant_count = 0
    for tc in failed_tests:
        tc_name = tc.get("name", tc.get("id", "")).lower().replace("_", "")
        if any(mn in tc_name for mn in modified_names):
            relevant_count += 1
    
    return {
        "relevant": relevant_count > 0,
        "relevant_count": relevant_count,
        "total_failed": len(failed_tests),
        "verdict": "failure_likely_caused_by_changes" if relevant_count > 0 else "failure_unrelated_to_changes"
    }


def print_report(report: dict):
    """打印退化热区报告"""
    print(f"\n  === 差分回归分析 ===", flush=True)
    print(f"  修改文件: {report['total']['modified']}", flush=True)
    if report["modified_files"]:
        for f in report["modified_files"][:5]:
            print(f"    ~ {f}", flush=True)
        if len(report["modified_files"]) > 5:
            print(f"    ... 还有{len(report['modified_files'])-5}个", flush=True)
    
    if report["failed_tests"]:
        print(f"  失败测试: {report['total']['failed']}", flush=True)
        for tc in report["failed_tests"]:
            print(f"    ❌ {tc.get('name', tc.get('id', '?'))}", flush=True)
        
        ca = report.get("cross_analysis", {})
        if ca.get("relevant"):
            print(f"  ⚠️  失败与修改文件相关 → 建议优先审查相关代码", flush=True)
        else:
            print(f"  ℹ️  失败可能与未修改的模块有关", flush=True)
    
    print(f"  受影响测试: {report['total']['affected_tests']}", flush=True)
    for t in report.get("affected_test_files", [])[:3]:
        print(f"    → {t.get('test', t.get('test_file', '?'))}", flush=True)


def status() -> dict:
    """查看状态"""
    modified = get_modified_files()
    cg = _load_call_graph()
    return {
        "modified_files": len(modified) if modified else 0,
        "call_graph_loaded": "error" not in cg,
        "call_graph_functions": len(cg.get("functions", {})) if "error" not in cg else 0,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        s = status()
        print(f"Modified files: {s['modified_files']}")
        print(f"Call graph: {'loaded' if s['call_graph_loaded'] else 'NOT loaded'} ({s['call_graph_functions']} functions)")
    else:
        result = run_diff_regression({})
        print_report(result)
