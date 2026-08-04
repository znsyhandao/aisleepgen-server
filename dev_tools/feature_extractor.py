"""
统一特征提取器 — 所有ML模型统一特征源

核心: 原始feedback → 特征向量(15维) + 用户嵌入(64维) = 79维
"""

import os, json
import numpy as np

AISLEEP = r"D:\AISleepGen_Optimized"
CAL_PATH = os.path.join(AISLEEP, "data", "calibration.json")

# 延迟导入 user_embedding (避免循环)
_emb_engine = None
def _get_emb():
    global _emb_engine
    if _emb_engine is None:
        from dev_tools.user_embedding import UserEmbeddingEngine
        _emb_engine = UserEmbeddingEngine()
    return _emb_engine


def extract_base_features(fb: dict) -> list:
    """从单条feedback提取基础15维特征"""
    cal = json.load(open(CAL_PATH, "r", encoding="utf-8"))
    coefs = cal.get("_regression_coefs", {})
    
    return [
        fb.get("wm_score_at_time", 50) / 100.0,
        fb.get("sleep_latency", 30) / 120.0,
        fb.get("awake_times", 1) / 10.0,
        fb.get("total_duration", 7) / 10.0,
        fb.get("stress_level", 5) / 10.0,
        1.0 if fb.get("pain") else 0.0,
        coefs.get("wm_score", 0),
        coefs.get("latency", 0),
        coefs.get("awake", 0),
        coefs.get("duration", 0),
        coefs.get("stress", 0),
        coefs.get("pain_flag", 0),
        fb.get("happy_ratio", 0.5),
        fb.get("pain_penalty_base", 0.1),
        1.0 if fb.get("awake_times", 0) >= 3 else 0.0,
    ]


def extract_embedding(fb: dict) -> list:
    """提取用户嵌入 (64维)"""
    uid = fb.get("openid", "default")
    emb = _get_emb().get_embedding(uid)
    return emb.tolist()


def extract_all_features(fb: dict) -> list:
    """79维: 15基础 + 64嵌入"""
    base = extract_base_features(fb)
    emb = extract_embedding(fb)
    return base + emb


def feature_dim() -> int:
    """总特征维度"""
    return 15 + 64
