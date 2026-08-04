"""
sleep_math_bridge.py — AISleepGen ↔ Math Core 桥接
====================================================
Tier 0 (Math Core) → Tier 1 (Sleep Domain) 连接器。

使用:
  from sleep_math_bridge import enhance_sleep_analysis, get_math_core

工作原理:
  1. AISleepGen 收集到睡眠数据后
  2. 调用 enhance_sleep_analysis() 传入原始评分
  3. Math Core (DFA + MAGI + POMDP) 计算深度分析
  4. 返回增强版评分 + 分形指标 + 复杂度健康评估
"""
import sys, os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger("sleep_math_bridge")

# 注册 Math Core 路径
MATH_CORE_PATH = r"D:\super_frontier_radar"
if MATH_CORE_PATH not in sys.path:
    sys.path.insert(0, MATH_CORE_PATH)

_math_core = None

def get_math_core():
    """懒加载 Math Core"""
    global _math_core
    if _math_core is None:
        try:
            from nexus_math_core import (
                pomdp_update, mab_select, PredictionTracker,
                FractalModule, MagiModule,
                analyze_complexity, sleep_quality, health_eval, cross_compare,
            )
            _math_core = {
                "pomdp_update": pomdp_update,
                "mab_select": mab_select,
                "PredictionTracker": PredictionTracker,
                "fractal": FractalModule(),
                "magi": MagiModule(),
                "analyze_complexity": analyze_complexity,
                "sleep_quality": sleep_quality,
                "health_eval": health_eval,
                "cross_compare": cross_compare,
            }
            logger.info("Math Core loaded successfully")
        except ImportError as e:
            logger.warning(f"Math Core not available: {e}")
            _math_core = None
    return _math_core


def enhance_sleep_analysis(
    sleep_data: Dict[str, Any],
    original_scores: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    用 Math Core 增强睡眠分析。
    
    Args:
        sleep_data: {
            "stages": ["awake","light","deep","rem",...],  # 睡眠阶段序列
            "heart_rate": [72,71,68,...],                   # 可选心率序列
            "duration_min": 420,                            # 总时长(分钟)
            "hrv": 45,                                      # 可选HRV
            ...
        }
        original_scores: AISleepGen 原有的评分 dict
    
    Returns:
        增强后的分析结果，包含:
        - 原始评分（如有）
        - fractal_metrics: 分形分析结果
        - magi_assessment: 复杂度健康评估
        - enhanced_score: 综合增强分
        - confidence: 置信度
    """
    math = get_math_core()
    if math is None:
        return _fallback_enhance(sleep_data, original_scores)
    
    result = {
        "enhanced": True,
        "math_core_version": "v1.0",
        "timestamp": datetime.now().isoformat(),
    }
    
    # 保留原始分数
    if original_scores:
        result["original_scores"] = original_scores
    
    stages = sleep_data.get("stages", [])
    heart_rate = sleep_data.get("heart_rate", [])
    
    # 1. 分形分析
    try:
        if stages:
            fractal_result = math["sleep_quality"](stages, heart_rate)
            result["fractal_metrics"] = fractal_result
        else:
            result["fractal_metrics"] = {"quality_score": 50, "stability": 0.5}
    except Exception as e:
        logger.warning(f"Fractal analysis failed: {e}")
        result["fractal_metrics"] = {"quality_score": 50, "error": str(e)}
    
    # 2. DFA 复杂度
    try:
        if heart_rate and len(heart_rate) > 50:
            complexity = math["analyze_complexity"](heart_rate)
            result["complexity_analysis"] = complexity
        elif stages:
            # 对睡眠阶段编码序列做 DFA
            stage_map = {"awake": 0, "wake": 0, "light": 1, "deep": 2, "rem": 3, "REM": 3}
            encoded = [stage_map.get(str(s).lower(), 0) for s in stages]
            complexity = math["analyze_complexity"](encoded)
            result["complexity_analysis"] = complexity
        else:
            result["complexity_analysis"] = {"hurst": 0.5, "regime": "unknown"}
    except Exception as e:
        logger.warning(f"Complexity analysis failed: {e}")
    
    # 3. MAGI 健康评估
    try:
        hurst = result.get("complexity_analysis", {}).get("hurst", 0.5)
        metrics = {
            "hurst": hurst,
            "entropy": result.get("entropy", 0.5),
            "variability": abs(hurst - 0.5),
        }
        magi_result = math["health_eval"](metrics, "sleep")
        result["magi_assessment"] = magi_result
    except Exception as e:
        logger.warning(f"MAGI assessment failed: {e}")
        result["magi_assessment"] = {"health_score": 50}
    
    # 4. 增强综合分
    try:
        frag_score = result.get("fractal_metrics", {}).get("quality_score", 50)
        magi_score = result.get("magi_assessment", {}).get("health_score", 50)
        orig_score = original_scores.get("overall_score", 50) if original_scores else 50
        
        # 加权融合: 原始分50% + 分形25% + MAGI 25%
        enhanced = orig_score * 0.50 + frag_score * 0.25 + magi_score * 0.25
        result["enhanced_score"] = round(enhanced)
        result["confidence"] = result.get("complexity_analysis", {}).get("confidence", 0.5)
    except Exception:
        result["enhanced_score"] = original_scores.get("overall_score", 50) if original_scores else 50
    
    return result


def _fallback_enhance(sleep_data, original_scores=None):
    """Math Core 不可用时的降级分析"""
    result = {
        "enhanced": False,
        "reason": "math_core_unavailable",
        "timestamp": datetime.now().isoformat(),
    }
    if original_scores:
        result["original_scores"] = original_scores
        result["enhanced_score"] = original_scores.get("overall_score", 50)
    return result


def analyze_sleep_with_math(user_id: str, sleep_data: Dict) -> Dict:
    """
    一站式数学增强分析入口。
    供 external API (如 8090 的 /api/analyze) 调用。
    """
    result = {
        "user_id": user_id,
        "analyzed_at": datetime.now().isoformat(),
        "math_enhanced": False,
    }
    
    # 基础分析
    result["data_summary"] = {
        "stages_count": len(sleep_data.get("stages", [])),
        "has_heart_rate": len(sleep_data.get("heart_rate", [])) > 0,
        "duration_min": sleep_data.get("duration_min", 0),
    }
    
    # 数学增强
    try:
        enhanced = enhance_sleep_analysis(sleep_data)
        result.update({
            "math_enhanced": enhanced.get("enhanced", False),
            "fractal_analysis": enhanced.get("fractal_metrics"),
            "complexity": enhanced.get("complexity_analysis"),
            "health_assessment": enhanced.get("magi_assessment"),
            "enhanced_score": enhanced.get("enhanced_score", 50),
            "confidence": enhanced.get("confidence", 0.5),
        })
    except Exception as e:
        logger.error(f"Math enhancement failed: {e}")
        result["error"] = str(e)
    
    return result


# ============================================================
# 跨域桥接 (Sleep ↔ Skin)
# ============================================================

def bridge_sleep_to_skin(sleep_analysis: Dict) -> Dict:
    """
    将睡眠分析结果映射为护肤建议。
    这是 POMDP sleep→skin 的实际执行者。
    """
    math = get_math_core()
    result = {
        "source": "sleep_analysis",
        "target": "skin_recommendation",
        "mappings": [],
    }
    
    hurst = sleep_analysis.get("hurst", 0.5)
    regime = sleep_analysis.get("regime", "unknown")
    health = sleep_analysis.get("health_score", 50)
    
    # 睡眠质量 → 皮肤状态映射
    if health < 30:
        result["mappings"].append({
            "skin_concern": "炎症风险升高",
            "reason": "睡眠质量极低(health<30)，皮质醇持续升高",
            "recommendation": "加强抗氧化+修复类产品",
            "priority": "high",
        })
    elif health < 50:
        result["mappings"].append({
            "skin_concern": "修复能力下降",
            "reason": f"睡眠质量偏低(health={health})",
            "recommendation": "增加修复精华使用频率",
            "priority": "medium",
        })
    
    if regime == "chaotic" or hurst < 0.35:
        result["mappings"].append({
            "skin_concern": "肤质波动",
            "reason": f"睡眠结构紊乱(H={hurst:.2f})",
            "recommendation": "减少护肤品更换频率，建立稳定基础护理",
            "priority": "medium",
        })
    
    if math:
        try:
            cross = math["magi"].cross_domain_compare(
                {"hurst": hurst, "health_score": health},
                None, None
            )
            result["cross_domain_score"] = cross
        except: pass
    
    return result


# ============================================================
# 便捷测试
# ============================================================

if __name__ == "__main__":
    # 模拟睡眠数据
    test_data = {
        "stages": ["awake"]*5 + ["light"]*30 + ["deep"]*20 + ["rem"]*15 + ["light"]*20 + ["deep"]*15 + ["rem"]*10,
        "heart_rate": [72]*20 + [68]*30 + [65]*40 + [62]*30 + [66]*20,
        "duration_min": 420,
    }
    
    print("=== AISleepGen Math Bridge Test ===")
    result = enhance_sleep_analysis(test_data)
    print(f"Enhanced: {result.get('enhanced')}")
    print(f"Enhanced Score: {result.get('enhanced_score')}")
    print(f"Fractal: {json.dumps(result.get('fractal_metrics',{}), ensure_ascii=False)}")
    print(f"MAGI: {json.dumps(result.get('magi_assessment',{}), ensure_ascii=False)}")
    print(f"Complexity: {json.dumps(result.get('complexity_analysis',{}), ensure_ascii=False)}")
    
    print("\n=== Sleep → Skin Bridge ===")
    bridge = bridge_sleep_to_skin(result)
    for m in bridge["mappings"]:
        print(f"  [{m['priority']}] {m['skin_concern']}: {m['recommendation']}")
