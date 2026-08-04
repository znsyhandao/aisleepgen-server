"""
device_data_injector.py — 手环/设备数据统一注入器

统一入口：OCR截图提取 + 手动键盘输入 → 结构化数据 → 世界模型

使用路径:
  1. OCR截图: upload_image → extract_with_easyocr → inject_to_world
  2. 手动输入: POST /api/sleep/handring-data → inject_to_world
"""

import os, re, json, time
from datetime import datetime, timedelta
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEVICE_RECORD_DIR = os.path.join(PROJECT_ROOT, "data", "device_data")

# 确保目录存在
os.makedirs(DEVICE_RECORD_DIR, exist_ok=True)


def _get_user_record_path(openid: str) -> str:
    """用户设备数据持久化路径"""
    return os.path.join(DEVICE_RECORD_DIR, f"{openid}.json")


def load_device_data(openid: str) -> dict:
    """加载用户已保存的设备数据"""
    path = _get_user_record_path(openid)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"records": []}
    return {"records": []}


def save_device_data(openid: str, data: dict):
    """保存设备数据"""
    path = _get_user_record_path(openid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def normalize_device_data(raw: dict) -> dict:
    """规范化设备数据，补全缺失字段
    
    OCR或手动输入进来的数据可能缺字段，这里统一补全/推算
    同时做输入验证，防止异常值穿透。
    """
    result = dict(raw)

    # === 输入验证 ===
    _range = {
        'sleep_score': (0, 100),
        'total_sleep_min': (0, 720),
        'deep_sleep_min': (0, 500),
        'light_sleep_min': (0, 500),
        'rem_min': (0, 360),
        'awake_count': (0, 30),
        'heart_rate_avg': (30, 200),
        'hrv': (10, 200),
        'spo2': (80, 100),
        'respiratory_rate': (8, 30),
        'deep_continuity': (0, 120),
    }
    for key, (lo, hi) in _range.items():
        if key in result and result[key] is not None:
            try:
                val = float(result[key])
                if val < lo or val > hi:
                    print(f'[DeviceData] 输入验证: {key}={val} 超出范围[{lo}, {hi}], 已忽略')
                    del result[key]
            except (ValueError, TypeError):
                print(f'[DeviceData] 输入验证: {key}={result[key]} 类型错误, 已忽略')
                del result[key]
    # === end 输入验证 ===

    
    # 补日期
    if "date" not in result or not result.get("date"):
        result["date"] = datetime.now().strftime("%Y-%m-%d")
    
    # 如果总时长缺失但从各阶段可推算
    if not result.get("total_sleep_min"):
        total = 0
        for key in ["deep_sleep_min", "light_sleep_min", "rem_min"]:
            if result.get(key):
                total += result[key]
        if total > 0:
            result["total_sleep_min"] = total
    
    # 如果各阶段缺失但总时长有，做合理分配（极端保守）
    if result.get("total_sleep_min") and not (
        result.get("deep_sleep_min") and result.get("light_sleep_min") and result.get("rem_min")
    ):
        total = result["total_sleep_min"]
        if not result.get("deep_sleep_min"):
            result["deep_sleep_min"] = int(total * 0.25)  # 默认25%深睡
        if not result.get("light_sleep_min"):
            result["light_sleep_min"] = int(total * 0.45)  # 默认45%浅睡
        if not result.get("rem_min"):
            result["rem_min"] = total - result["deep_sleep_min"] - result["light_sleep_min"]
    
    # 来源标记
    result.setdefault("source", "unknown")
    result.setdefault("synced_at", datetime.now().isoformat())
    
    return result


def build_prompt_block(device_data: dict) -> str:
    """构建注入世界模型的prompt块
    
    格式化为给世界模型可读的结构化文本
    """
    d = device_data
    parts = ["[手环/设备数据]"]
    
    if d.get("sleep_score"):
        parts.append(f"睡眠评分{d['sleep_score']}分")
    if d.get("bedtime"):
        parts.append(f"入睡{d['bedtime']}")
    if d.get("waketime"):
        parts.append(f"起床{d['waketime']}")
    if d.get("total_sleep_min"):
        h, m = divmod(d['total_sleep_min'], 60)
        parts.append(f"总睡眠{h}h{m}m")
    if d.get("deep_sleep_min"):
        h, m = divmod(d['deep_sleep_min'], 60)
        parts.append(f"深睡{h}h{m}m")
    if d.get("light_sleep_min"):
        h, m = divmod(d['light_sleep_min'], 60)
        parts.append(f"浅睡{h}h{m}m")
    if d.get("rem_min"):
        h, m = divmod(d['rem_min'], 60)
        parts.append(f"REM{h}h{m}m")
    if d.get("awake_count") is not None:
        parts.append(f"清醒{d['awake_count']}次")
    if d.get("heart_rate_avg"):
        parts.append(f"心率{d['heart_rate_avg']}bpm")
    if d.get("hrv"):
        parts.append(f"HRV{d['hrv']}ms")
    if d.get("spo2"):
        parts.append(f"血氧{d['spo2']}%")
    if d.get("respiratory_rate"):
        parts.append(f"呼吸率{d['respiratory_rate']}次/分")
    if d.get("deep_continuity"):
        parts.append(f"深睡连续性{d['deep_continuity']}分")
    
    return "，".join(parts)


def inject_to_world(openid: str, device_data: dict) -> dict:
    """设备数据 → 保存 + 注入世界模型
    
    Args:
        openid: 用户ID
        device_data: 规范化后的设备数据
    
    Returns:
        dict: 注入结果
    """
    normalized = normalize_device_data(device_data)
    
    # 保存到用户记录
    records = load_device_data(openid)
    normalized["recorded_at"] = datetime.now().isoformat()
    records.setdefault("records", []).append(normalized)
    # 只保留最近30条
    records["records"] = records["records"][-30:]
    records["latest"] = normalized
    save_device_data(openid, records)
    
    # 构建prompt块
    prompt_block = build_prompt_block(normalized)
    
    print(f"[DeviceData] Injected for {openid[:12]}: {prompt_block[:120]}")
    
    return {
        "status": "injected",
        "prompt_block": prompt_block,
        "data": normalized,
    }


def ocr_and_inject(openid: str, image_input) -> dict:
    """OCR识别 + 注入世界模型（一键完成）
    
    Args:
        openid: 用户ID
        image_input: 图片路径(str) 或字节(bytes)
    
    Returns:
        dict: 注入结果（包含OCR状态）
    """
    from ring_ocr import RingDataExtractor
    
    ext = RingDataExtractor()
    ocr_result = ext.extract_with_easyocr(image_input)
    
    if ocr_result.get("status") != "parsed":
        return {"status": "ocr_failed", "ocr_result": ocr_result}
    
    # 检查是否提取到足够的数据
    extracted_fields = [k for k in ["sleep_score", "deep_sleep_min", "total_sleep_min", "heart_rate_avg"] if k in ocr_result]
    if len(extracted_fields) < 1:
        return {"status": "insufficient_data", "ocr_result": ocr_result}
    
    # 注入
    inject_result = inject_to_world(openid, ocr_result)
    inject_result["ocr_fields_found"] = extracted_fields
    inject_result["ocr_raw_texts"] = ocr_result.get("_raw_texts", [])
    return inject_result


def get_latest_for_prompt(openid: str) -> str:
    """获取用户最近的设备数据，格式化为prompt块
    
    由 _handle_chat 在构建世界模型prompt时调用
    """
    records = load_device_data(openid)
    latest = records.get("latest")
    if not latest:
        return ""
    
    prompt = build_prompt_block(latest)
    
    # 如果还有更多历史记录，加一句趋势
    all_records = records.get("records", [])
    if len(all_records) >= 2:
        recent = all_records[-3:]
        scores = [r.get("sleep_score") for r in recent if r.get("sleep_score")]
        if len(scores) >= 2:
            trend = "↑" if scores[-1] > scores[0] else ("↓" if scores[-1] < scores[0] else "→")
            prompt += f"。近{len(recent)}次评分趋势{trend}"
    
    return prompt
