"""
sleep_stage_analyzer.py — 轻量睡眠阶段分析器

MIT SleepStage Transformer 启示:
  从时序心率+体动数据推断 N1/N2/N3/REM 比例
  不需要 PSG，只需要手表/手环的 30 秒窗口数据

实现:
  用启发式规则近似（纯 Python，不依赖外部模型）
  输出: N1%, N2%, N3%, REM%, 总时长, 推断置信度

输入:
  hr_series: [60, 62, 58, ...] 心率时间序列（每30秒一个点）
  motion_series: [0, 0, 1, 0, ...] 体动标记（每30秒是否有动作）

备注:
  真正的睡眠分期需要 PPG 数据训练模型
  这里用 3 个世界公认的启发式特征做近似:
  1. HRV 高频功率 (HF) → REM 标记
  2. 心率趋势 (brady/tachy) → N3 标记
  3. 体动密度 → 觉醒/N1 标记
"""
import json, os
from datetime import datetime
from math import sqrt

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 正常睡眠阶段占比参考范围（WHO/USDHS）
NORMAL_RANGES = {
    "N1": {"min": 2, "max": 10, "label": "浅睡-过渡期"},
    "N2": {"min": 40, "max": 60, "label": "浅睡-稳定期"},
    "N3": {"min": 10, "max": 25, "label": "深睡-修复期"},
    "REM": {"min": 15, "max": 25, "label": "快速眼动-记忆期"},
}


def analyze_heart_rate(hr_series: list, motion_series: list = None) -> dict:
    """
    从心率序列推断睡眠阶段比例
    
    返回 {
        "stages": {"N1": 15.0, "N2": 45.0, "N3": 18.0, "REM": 22.0},  # 百分比
        "total_minutes": 420,
        "n3_deficit": -5.0,          # 深睡缺乏 %（负值=缺）
        "rem_deficit": 0.0,
        "confidence": 0.7,           # 0-1 置信度
        "flags": ["HRV不足提示"],      # 标记
    }
    """
    n = len(hr_series)
    if n < 10:
        return {"error": "太短无法分析", "confidence": 0}
    
    # 默认每点 = 30 秒
    total_minutes = n * 0.5
    
    # ===== 特征提取 =====
    
    # 1. 心率趋势: 深睡时心率最低（连续下降>5bpm）
    hr_mean = sum(hr_series) / n
    
    # 滑动平均找趋势
    window = max(n // 10, 5)
    trend_down = 0
    trend_up = 0
    for i in range(window, n - window):
        early = sum(hr_series[i-window:i]) / window
        late = sum(hr_series[i:i+window]) / window
        if late < early - 3:
            trend_down += 1  # 心率下降段 → 可能 N3
        elif late > early + 3:
            trend_up += 1    # 心率上升段 → 可能 REM
    
    trend_ratio = trend_down / max(trend_down + trend_up, 1)
    
    # 2. HRV 代理: 心率变异性 (RMSSD)
    diffs = [abs(hr_series[i] - hr_series[i-1]) for i in range(1, n)]
    rmssd = sqrt(sum(d*d for d in diffs) / max(len(diffs), 1)) if diffs else 0
    
    # HRV 高 → REM 候选
    hrv_high = sum(1 for d in diffs if d > 5)
    hrv_ratio = hrv_high / max(len(diffs), 1)
    
    # 3. 体动: 如果有体动数据
    motion_density = 0
    if motion_series and len(motion_series) >= n // 2:
        valid_m = sum(motion_series[:n]) / max(n, 1)
        motion_density = valid_m
    else:
        # 无体动数据时: HRV波动大→可能体动
        motion_density = hrv_ratio * 0.3  # 保守估计
    
    # ===== 阶段比例估算 =====
    
    # N1: 高体动+中等HRV → 浅睡/觉醒过渡
    n1_pct = min(20, motion_density * 100 * 0.4)
    if n1_pct < 3:
        n1_pct = 5  # 最小估值
    
    # N3: 低心率+低HRV+低体动 → 深睡
    n3_base = trend_ratio * 25
    n3_hrv_penalty = max(0, (hrv_ratio - 0.3) * 15)
    n3_pct = max(5, min(30, n3_base - n3_hrv_penalty))
    
    # REM: 高HRV+心率波动
    rem_pct = hrv_ratio * 40
    if rem_pct < 8:
        rem_pct = 12  # REM 最小不会太低
    
    # N2: 剩余
    remaining = 100 - n1_pct - n3_pct - rem_pct
    n2_pct = max(30, min(65, remaining))
    
    # 重新归一化
    total_pct = n1_pct + n2_pct + n3_pct + rem_pct
    n1_pct = round(n1_pct / total_pct * 100, 1)
    n2_pct = round(n2_pct / total_pct * 100, 1)
    n3_pct = round(n3_pct / total_pct * 100, 1)
    rem_pct = round(rem_pct / total_pct * 100, 1)
    
    # ===== 偏差分析 =====
    n3_deficit = round(n3_pct - NORMAL_RANGES["N3"]["min"], 1)
    rem_deficit = round(rem_pct - NORMAL_RANGES["REM"]["min"], 1)
    
    flags = []
    if n3_deficit < -3:
        flags.append(f"深睡不足: 比最低标准低{abs(n3_deficit):.0f}%")
    if rem_deficit < -3:
        flags.append(f"REM不足: 比最低标准低{abs(rem_deficit):.0f}%")
    if n1_pct > 15:
        flags.append(f"浅睡偏多: {n1_pct}% (正常<10%)")
    if motion_density > 0.3 and n >= 120:
        flags.append("体动频繁，可能有未察觉的觉醒")
    
    # 置信度: 有体动数据+长序列 更高
    confidence = round(0.5 + (n / 240) * 0.2 + (0.2 if motion_series else 0), 2)
    confidence = min(0.9, max(0.3, confidence))
    
    return {
        "stages": {"N1": n1_pct, "N2": n2_pct, "N3": n3_pct, "REM": rem_pct},
        "total_minutes": round(total_minutes, 1),
        "n3_deficit": n3_deficit,
        "rem_deficit": rem_deficit,
        "confidence": confidence,
        "flags": flags,
        "features": {
            "hr_mean": round(hr_mean, 1),
            "rmssd": round(rmssd, 1),
            "trend_down_ratio": round(trend_ratio, 2),
            "motion_density": round(motion_density, 2),
        }
    }


def format_stage_comment(result: dict) -> str:
    """将分析结果格式化为自然语言（适合注入 prompt）"""
    if "error" in result:
        return ""
    
    stages = result.get("stages", {})
    s = []
    s.append(f"【睡眠阶段推理】总时长{result['total_minutes']:.0f}分")
    s.append(f"  N1(浅睡-过渡): {stages.get('N1',0)}%")
    s.append(f"  N2(浅睡-稳定): {stages.get('N2',0)}%")
    s.append(f"  N3(深睡-修复): {stages.get('N3',0)}%")
    s.append(f"  REM(快速眼动): {stages.get('REM',0)}%")
    s.append(f"  置信度: {result.get('confidence', 0)*100:.0f}%")
    
    for flag in result.get("flags", []):
        s.append(f"  ⚠ {flag}")
    
    return "\n".join(s)


def analyze_from_user_profile(openid: str = "default") -> dict:
    """从用户画像中的心率/体动数据做分析"""
    profile_path = os.path.join(PROJECT_ROOT, "data", "user_profile.json")
    if not os.path.exists(profile_path):
        return {"error": "no profile"}
    
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            profiles = json.load(f)
    except:
        return {"error": "profile unreadable"}
    
    profile = profiles.get(openid, {})
    device_data = profile.get("device_data", {})
    
    # 找心率数据
    hr_sessions = device_data.get("heart_rate_sessions", [])
    if not hr_sessions:
        return {"error": "no heart rate data"}
    
    latest = hr_sessions[-1]
    hr_series = latest.get("readings", []) if isinstance(latest, dict) else latest
    
    if not hr_series or not isinstance(hr_series, list):
        return {"error": "invalid HR data"}
    
    motion_series = None
    if isinstance(latest, dict):
        motion_series = latest.get("motion", None)
    
    return analyze_heart_rate(hr_series, motion_series)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        r = analyze_from_user_profile()
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        # Demo with simulated data
        import random
        hr_series = [random.randint(55, 75) for _ in range(480)]  # 4 hours
        # Add some deep sleep pattern (gradual decline)
        for i in range(120, 240):
            hr_series[i] = int(60 - (i-120) * 0.08)
        # Add some REM (HRV spikes)
        for i in range(300, 360):
            hr_series[i] = hr_series[i] + random.randint(-8, 8)
        
        motion = [1 if random.random() < 0.05 else 0 for _ in range(480)]
        
        result = analyze_heart_rate(hr_series, motion)
        print(f"Stages: {result['stages']}")
        print(f"Total: {result['total_minutes']}min")
        print(f"Confidence: {result['confidence']}")
        print(f"Flags: {result['flags']}")
        print(f"Features: {result['features']}")
        print()
        print(f"Formatted:\n{format_stage_comment(result)}")
