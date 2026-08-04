"""
live_capture.py — 从生产日志捕获真实异常请求 → 自动生长测试用例

零侵入：不修改 deepseek_proxy.py 一行代码
原理：监控服务器日志文件（aisleepgen.log, proxy_nohup.log），
      解析 Error/Exception 日志行 → 提取上下文 → 生成新测试用例
"""
import os, json, re, time
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CAPTURE_DIR = os.path.join(PROJECT_ROOT, "data", "quality_baseline", "capture_queue")
HISTORY_LOG = os.path.join(PROJECT_ROOT, "data", "quality_baseline", "capture_history.json")
TEST_CASES_PATH = os.path.join(PROJECT_ROOT, "data", "quality_baseline", "test_cases.json")

# 日志文件列表（按优先级排列）
LOG_FILES = [
    os.path.join(PROJECT_ROOT, "aisleepgen.log"),
    os.path.join(PROJECT_ROOT, "proxy_nohup.log"),
]

# 匹配异常行模式
ERROR_PATTERNS = [
    re.compile(r"ERROR|Error|Exception|Traceback|500|crash|崩溃|failed|fail"),
    re.compile(r"wfile\.write.*Error|wfile\.write.*BrokenPipe"),
    re.compile(r"timeout|Timeout|超时"),
]

# 已知无害模式（日志噪声过滤）
SKIP_PATTERNS = [
    re.compile(r"except.*pass.*"),  # 安全 except: pass
    re.compile(r"static.*file.*not found"),  # 静态文件缺失
    re.compile(r"\[Profile"),  # 用户画像调试日志
    re.compile(r".*self_evolve.*"),  # 质量引擎自身日志
    re.compile(r".*post_edit_hook.*"),
]


def _ensure_dir():
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(HISTORY_LOG), exist_ok=True)


def _load_history() -> dict:
    """加载已捕获记录（去重用）"""
    if os.path.exists(HISTORY_LOG):
        try:
            with open(HISTORY_LOG, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"captures": [], "generated_cases": 0, "last_scan": ""}


def _save_history(history: dict):
    with open(HISTORY_LOG, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _get_log_positions() -> dict:
    """记录每个日志文件上次读取位置"""
    pos_path = os.path.join(PROJECT_ROOT, "data", "quality_baseline", "log_positions.json")
    if os.path.exists(pos_path):
        try:
            with open(pos_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    positions = {}
    for lf in LOG_FILES:
        if os.path.exists(lf):
            try:
                positions[lf] = os.path.getsize(lf)
            except:
                positions[lf] = 0
        else:
            positions[lf] = 0
    return positions


def _save_log_positions(positions: dict):
    pos_path = os.path.join(PROJECT_ROOT, "data", "quality_baseline", "log_positions.json")
    with open(pos_path, "w", encoding="utf-8") as f:
        json.dump(positions, f, ensure_ascii=False, indent=2)


def _extract_context_from_log(line: str) -> dict:
    """从日志行提取请求上下文"""
    # 尝试提取 openid (通常格式: [openid_hash]...)
    openid_match = re.search(r"\[(\w{8,})\]", line)
    openid = openid_match.group(1) if openid_match else "unknown"

    # 尝试提取路径
    path_match = re.search(r"(/api/\w[-\w]*)", line)
    path = path_match.group(1) if path_match else "unknown"

    # 提取错误类型
    error_type = "Exception"
    if "Timeout" in line or "timeout" in line:
        error_type = "Timeout"
    elif "BrokenPipe" in line:
        error_type = "BrokenPipe"
    elif "500" in line or "crash" in line.lower() or "崩溃" in line:
        error_type = "ServerError"

    return {
        "openid": openid,
        "path": path,
        "error_type": error_type,
        "raw_line": line[:200],
        "captured_at": datetime.now().isoformat(),
    }


def _is_relevant_error(line: str) -> bool:
    """判断日志行是否值得捕获"""
    # 必须匹配至少一个错误模式
    matched = any(p.search(line) for p in ERROR_PATTERNS)
    if not matched:
        return False
    # 过滤已知无害
    if any(p.search(line) for p in SKIP_PATTERNS):
        return False
    return True


def _generate_test_case_from_capture(capture: dict) -> dict:
    """从捕获的异常生成测试用例"""
    openid = capture.get("openid", "unknown")
    path = capture.get("path", "unknown")
    error_type = capture.get("error_type", "Exception")

    # 根据路径选择测试类型的消息
    if "chat" in path or "world-step" in path:
        message = f"异常路径测试: {path} (来自{openid})"
    elif "device" in path or "ocr" in path:
        message = f"设备数据异常测试: {path} (来自{openid})"
    elif "compliance" in path:
        message = f"合规路径测试: {path}"
    else:
        message = f"通用异常测试: {path}"

    return {
        "name": f"LiveCapture: {error_type} on {path}",
        "id": f"live_{openid[:8]}_{path.replace('/','_')}_{datetime.now().strftime('%H%M%S')}",
        "messages": [{"role": "user", "content": message}],
        "expected": {
            "score_range": [0, 99],
            "quality_any": True,
        },
        "category": f"live_capture_{error_type.lower()}",
        "source": f"live_capture_{path.replace('/','_')}",
        "severity": "HIGH" if error_type in ("ServerError", "BrokenPipe") else "MEDIUM",
    }


def scan_and_capture() -> int:
    """扫描日志文件，捕获新异常，返回新捕获数"""
    _ensure_dir()
    history = _load_history()
    existing = set(c["raw_line"] for c in history.get("captures", []))

    positions = _get_log_positions()
    new_captures = 0

    for log_file in LOG_FILES:
        if not os.path.exists(log_file):
            continue

        try:
            last_pos = positions.get(log_file, 0)
            current_size = os.path.getsize(log_file)

            if current_size <= last_pos:
                continue

            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                f.seek(last_pos)
                for line in f:
                    line = line.strip()
                    if line and _is_relevant_error(line):
                        if line not in existing:
                            capture = _extract_context_from_log(line)
                            history["captures"].append(capture)
                            existing.add(line)
                            new_captures += 1

            positions[log_file] = current_size
        except Exception as e:
            print(f"[LiveCapture] 扫描 {log_file} 失败: {e}")

    _save_log_positions(positions)

    # 有新捕获 → 生成测试用例
    if new_captures > 0:
        new_cases = _add_test_cases_from_captures(history["captures"][-new_captures:])
        history["generated_cases"] += new_cases

    history["last_scan"] = datetime.now().isoformat()
    _save_history(history)
    return new_captures


def _add_test_cases_from_captures(captures: list) -> int:
    """从捕获列表生成并追加新测试用例"""
    if not os.path.exists(TEST_CASES_PATH):
        return 0

    try:
        with open(TEST_CASES_PATH, "r", encoding="utf-8") as f:
            test_cases = json.load(f)
    except:
        return 0

    if not isinstance(test_cases, list):
        return 0

    existing_ids = {tc.get("id") for tc in test_cases if isinstance(tc, dict)}
    added = 0

    for capture in captures:
        tc = _generate_test_case_from_capture(capture)
        if tc["id"] not in existing_ids:
            test_cases.append(tc)
            existing_ids.add(tc["id"])
            added += 1
            print(f"[LiveCapture] 新测试: {tc['id']} ({tc['source']})")

    if added > 0:
        with open(TEST_CASES_PATH, "w", encoding="utf-8") as f:
            json.dump(test_cases, f, ensure_ascii=False, indent=2)

    return added


def run_once() -> dict:
    """外部入口：一次扫描循环"""
    count = scan_and_capture()
    return {
        "new_captures": count,
        "capture_dir": CAPTURE_DIR,
        "timestamp": datetime.now().isoformat(),
    }


def status() -> dict:
    """查看捕获状态"""
    history = _load_history()
    return {
        "total_captures": len(history.get("captures", [])),
        "generated_cases": history.get("generated_cases", 0),
        "last_scan": history.get("last_scan", "never"),
        "capture_dir": CAPTURE_DIR,
        "test_cases_file": TEST_CASES_PATH,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        s = status()
        print(f"Total captures: {s['total_captures']}")
        print(f"Generated cases: {s['generated_cases']}")
        print(f"Last scan: {s['last_scan']}")
    else:
        r = run_once()
        print(f"Scan: {r['new_captures']} new captures")
