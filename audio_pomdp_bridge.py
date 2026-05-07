"""
audio_pomdp_bridge.py — 音频分析结果 → POMDP观测桥接

将 sleep_audio_analyzer 的分析结果作为POMDP额外观测注入。
"""
import os, json
from sleep_audio_analyzer import SleepAudioAnalyzer, get_analyzer, SLEEP_RECORD_DIR, _dummy_ring_measurement

AUDIO_OBS_JSON = os.path.join(SLEEP_RECORD_DIR, "audio_analysis_results.json")

def get_latest_audio_observation(openid: str = "default") -> dict:
    """
    读取最近的音频分析结果，转换为POMDP观测格式
    返回 dict 可直接传递给 pomdp_learner.observe()
    """
    ana = get_analyzer()
    wav_results = ana.analyze_all_wavs()
    
    if not wav_results:
        return {}
    
    # 取最新一次
    latest = wav_results[-1]
    
    # 构建观测参数
    # POMDP observe() 接受: text, score, bedtime, mood, time_of_day, feedback, effect
    obs = ana.audio_to_pomdp_observation(wav_results, _dummy_ring_measurement)
    
    # 从音频特征推断评分调整
    score_adjustment = _compute_score_adjustment(obs)
    
    # 生成描述文本
    description = _build_audio_description(obs)
    
    return {
        "text": f"[音频传感器] {description}",
        "score": score_adjustment,
        "effect": "positive" if score_adjustment > 0 else "neutral" if score_adjustment == 0 else "negative",
        "_raw_audio_obs": obs
    }

def _compute_score_adjustment(obs: dict) -> int:
    """从音频特征计算评分调整值（-20 ~ +10）"""
    adjustment = 0
    
    # 睡眠效率高 → 加分
    eff = obs.get("sleep_efficiency", 50)
    if eff > 85:
        adjustment += 5
    elif eff < 60:
        adjustment -= 5
    
    # 稳定性高 → 加分
    stability = obs.get("stability", 50)
    if stability > 70:
        adjustment += 5
    elif stability < 40:
        adjustment -= 5
    
    # 鼾声占比高 → 减分
    snore = obs.get("snore_pct", 30)
    if snore > 60:
        adjustment -= 3
    elif snore < 20:
        adjustment += 2
    
    # 体动多 → 减分
    movement = obs.get("movement_min", 30)
    if movement > 60:
        adjustment -= 3
    elif movement < 15:
        adjustment += 2
    
    # 手环数据
    if obs.get("ring_sleep_score", 0) > 0:
        ring_score = obs["ring_sleep_score"]
        if ring_score > 85:
            adjustment += 3
        elif ring_score < 60:
            adjustment -= 3
    
    return max(-20, min(10, adjustment))

def _build_audio_description(obs: dict) -> str:
    parts = []
    if "duration_hours" in obs:
        parts.append(f"时长{obs['duration_hours']:.1f}h")
    if "sleep_efficiency" in obs:
        parts.append(f"效率{obs['sleep_efficiency']:.0f}%")
    if "stability" in obs:
        parts.append(f"稳定性{obs['stability']}/100")
    if "snore_pct" in obs:
        parts.append(f"鼾声{obs['snore_pct']:.0f}%")
    if "movement_min" in obs:
        parts.append(f"体动{obs['movement_min']:.0f}分钟")
    if "breath_rate" in obs and obs["breath_rate"]:
        parts.append(f"呼吸{obs['breath_rate']}/min")
    if "ring_sleep_score" in obs:
        parts.append(f"手环评分{obs['ring_sleep_score']}")
    return "; ".join(parts)

def inject_audio_to_pomdp(openid: str = "default"):
    """
    完整流程：提取音频特征 → 生成观测 → 注入POMDP
    
    返回POMDP更新后的信念状态
    """
    from pomdp_learner import get_engine
    
    audio_obs = get_latest_audio_observation(openid)
    if not audio_obs:
        return {"status": "no_audio_data"}
    
    engine = get_engine()
    belief = engine.observe(
        openid=openid,
        text=audio_obs["text"],
        score=audio_obs["score"],
        effect=audio_obs["effect"]
    )
    
    return {
        "status": "injected",
        "text": audio_obs["text"],
        "score_adjustment": audio_obs["score"],
        "new_belief_score": belief.get("expected_score"),
        "new_entropy": belief.get("normalized_entropy")
    }

if __name__ == "__main__":
    result = inject_audio_to_pomdp("test_audio_user")
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
