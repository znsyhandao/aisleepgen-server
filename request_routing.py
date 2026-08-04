"""
request_routing.py — Self-Healing Tool Routing（arXiv 2603.01474 启示）

核心逻辑:
  不是每个 POST 都走 DeepSeek API（贵+慢）。
  简单请求（评分查询、状态检查）→ 本地规则引擎。
  复杂推理（个性化分析、情绪建议）→ 走 DeepSeek。

路由决策树:
  1. 健康检查 /health → 直接返回 {"status": "ok"}
  2. 简单评分查询（含 device_data 但不含 message）→ 本地 comprehensive_analysis
  3. 纯设备数据更新 → 本地存储 + 返回简单确认
  4. 含自然语言消息的复杂请求 → 走 DeepSeek
  5. OCR 请求 → 走 EasyOCR（已做）
"""
import json, os, sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
API_COST_THRESHOLD = 500  # 字符数 < 此值视为简单请求

def classify_request(path: str, data: dict) -> str:
    """
    对请求分类:
      "health" — 健康检查
      "local"  — 本地处理（不调 DeepSeek）
      "api"    — 需要 DeepSeek API
      "device" — 纯设备数据
    """
    if path == "/health":
        return "health"
    
    # OCR 不走 DeepSeek
    if "ocr" in path.lower() or "device-ocr" in path:
        return "device"
    
    # 纯设备数据更新
    if "device-data" in path:
        return "device"
    
    # 评分查询（有 device_data 但无 message）
    message = data.get("message", "") if isinstance(data, dict) else ""
    has_device = bool(data.get("device_data", {}) or data.get("heart_rate_series", [])) if isinstance(data, dict) else False
    
    if not message and has_device:
        return "local"  # 有设备数据无文本→本地评估
    
    if isinstance(data, dict) and data.get("is_long_haul_test"):
        return "local"  # 长程测试跳过API
    
    # 复杂请求
    return "api"


def handle_local(path: str, data: dict) -> dict:
    """本地处理简单评分请求"""
    try:
        sys.path.insert(0, PROJECT_ROOT)
        from sleep_world_model import WorldModelEngine
        
        # 提取 sleep_data
        sleep_data = {
            "stress_level": data.get("stress_level", 5),
            "awake_times": data.get("awake_times", 1),
            "sleep_latency": data.get("sleep_latency", 30),
            "total_sleep_min": data.get("total_sleep_min", 360),
            "feeling": data.get("feeling", ""),
        }
        
        wm = WorldModelEngine()
        result = wm.comprehensive_analysis(sleep_data)
        
        # 标记为本地处理
        if isinstance(result, dict):
            result["_routed_locally"] = True
            result["_routing_reason"] = "simple_query_no_deepseek"
        
        return result
    except Exception as e:
        return {"error": str(e), "_routed_locally": True, "_routing_error": True}


def stat_cost_saved(data: dict) -> int:
    """估算 DeepSeek API 调用节省的字符数"""
    message = data.get("message", "") if isinstance(data, dict) else ""
    if isinstance(data, dict):
        msg_len = len(data.get("message", "")) + len(data.get("device_data", {}).get("heart_rate", ""))
    else:
        msg_len = 0
    return msg_len


def routing_hook(path: str, data: dict) -> dict:
    """
    主路由钩子——在 deepseek_proxy 的 do_POST 入口调用。
    返回 {"action": "continue"}—走DeepSeek
         {"action": "local", "result": {...}}—本地处理
         {"action": "health"}—健康检查
    """
    classification = classify_request(path, data)
    
    if classification == "health":
        return {"action": "health"}
    
    if classification in ("local", "device"):
        result = handle_local(path, data)
        return {"action": "local", "result": result, "saved_chars": stat_cost_saved(data)}
    
    return {"action": "continue"}
