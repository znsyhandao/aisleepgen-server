#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MultiChannelAction v1.0 — 统一渲染指令标准化
# DEPLOY_v1_20260610

功能:
  将 RenderInstruction (P0实时输出) + InterventionPrediction (枚举器+推演输出)
  整编为统一的 MultiChannelAction，作为 API 最终返回的"执行命令"

三通道:
  audio      — 音频播放 (引用 audio_library.json 的86条内容库)
  breathing  — 呼吸引导 (包含指令文字、节奏)
  environment — 环境控制 (光照、温度、预留IoT)

兼容性:
  - 不修改已有的 RenderInstruction 类
  - 不修改 biofeedback_renderer.py 的渲染策略表
  - 只在 coordinator.step() 返回前合并输出
  - 旧 render/candidates/predictions 字段继续保留

使用:
  action = MultiChannelAction.build(
      render_instruction=render_instr,       # RenderInstruction 实例
      best_prediction=prediction_result,     # PredictionResult 实例 (可选)
      audio_library_path="/static/audio/",   # 音频库URL前缀
      user_id="default",
  )
"""

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from datetime import datetime


# ============================================================
# 干预→音频映射表
# 将 INTERVENTION_CATALOG 中的 action_id 映射到 audio_library.json 的实际路径
# ============================================================

# Key: intervention action_id → audio file path (relative to server root)
# 映射策略:
#   breath_*      → 引导呼吸 (已有32个WAV)
#   rain_sound    → 白噪音 雨声
#   stream_sound  → 白噪音 溪流
#   progressive_  → 冥想引导 (眠小兔原创)
#   cool_down     → 无音频 (环境动作)
#   do_nothing    → 无
AUDIO_MAP = {
    "rain_sound": "static/audio/meditation/whitenoise/rain.mp3",
    "stream_sound": "static/audio/meditation/whitenoise/stream.mp3",
    "progressive_relaxation": "static/audio/meditation/meditation_guided/progressive_relaxation.mp3",
}

# 广义白噪音 → 从 whitenoise 目录自动选择
WHITENOISE_DIR = "static/audio/meditation/whitenoise/"

# 呼吸引导WAV (已有32个)
BREATH_GUIDE = {
    "breath_4_7_8": {
        "guide_audio": "static/audio/breath_in.wav",
        "silence_audio": "static/audio/breath_out.wav",
    },
    "breath_box": {
        "guide_audio": "static/audio/breath_in.wav",
        "silence_audio": "static/audio/breath_out.wav",
    },
}

# 能量成本 → timeout映射 (超过此时间自动切换到更低一级)
ENERGY_TIMEOUT_MAP = {
    "none": 300,    # 被动收听: 5分钟
    "low": 240,     # 呼吸法: 4分钟
    "medium": 180,  # 主动配合: 3分钟
}


# ============================================================
# MultiChannelAction 数据类
# ============================================================

@dataclass
class AudioChannel:
    """音频通道"""
    source: str = ""                    # audio, recording, synthesized
    file: str = ""                      # 相对路径
    stream: str = ""                    # 流式ID (可选)
    volume: Dict = field(default_factory=lambda: {"db": -3.0, "duty_cycle": 0.3})
    fade: Dict = field(default_factory=lambda: {"in_s": 5.0, "out_s": 30.0})
    modulation: Dict = field(default_factory=lambda: {"freq_hz": 0.0, "depth": 0.0})
    loop: bool = True

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "file": self.file,
            "stream": self.stream,
            "volume": {k: round(v, 2) if isinstance(v, float) else v for k, v in self.volume.items()},
            "fade": self.fade,
            "modulation": self.modulation,
            "loop": self.loop,
        }


@dataclass
class BreathingChannel:
    """呼吸引导通道"""
    pattern: str = "4-7-8"             # 呼吸模式名
    tempo_bpm: float = 6.0
    in_s: float = 4.0
    hold_s: float = 0.0
    out_s: float = 8.0
    guide: Dict = field(default_factory=lambda: {
        "text_speed": 0.75,
        "silence_s": 4.0,
        "script": "跟随呼吸引导...",
        "audio_guide": "",
    })

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "tempo_bpm": round(self.tempo_bpm, 1),
            "in_s": self.in_s,
            "hold_s": self.hold_s,
            "out_s": self.out_s,
            "ratio": f"1:{self.out_s/self.in_s:.0f}" if self.in_s > 0 else "0",
            "guide": self.guide,
        }


@dataclass
class EnvironmentChannel:
    """环境控制通道 (含IoT预留)"""
    temperature: Dict = field(default_factory=lambda: {
        "target_delta": 0.0,
        "fade_in_min": 10,
        "iot_supported": False,   # True 表示有硬件可用
    })
    light: Dict = field(default_factory=lambda: {
        "kelvin": 2700,
        "brightness_pct": 2,
        "fade_out_s": 600,
        "iot_supported": False,
    })

    def to_dict(self) -> dict:
        return {
            "temperature": self.temperature,
            "light": self.light,
        }


@dataclass
class InterventionMeta:
    """干预元信息 — 来自推演评估器"""
    action_id: str = ""
    category: str = ""
    energy_cost: str = "low"
    priority: str = "normal"
    predicted_state: str = "calm"
    confidence: float = 0.5
    score: float = 0.0
    hrv_delta: float = 0.0
    stress_delta: float = 0.0
    timeout_s: int = 300
    reasoning: str = ""

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "category": self.category,
            "energy_cost": self.energy_cost,
            "priority": self.priority,
            "predicted_state": self.predicted_state,
            "confidence": round(self.confidence, 3),
            "score": round(self.score, 3),
            "hrv_delta": round(self.hrv_delta, 3),
            "stress_delta": round(self.stress_delta, 3),
            "timeout_s": self.timeout_s,
            "reasoning": self.reasoning,
        }


@dataclass
class MultiChannelAction:
    """
    统一渲染指令 — API 最终输出

    将 P0 渲染器 + 枚举器(1.1) + 推演器(1.2) 合并为一个结构
    小程序前端直接消费
    """
    version: str = "1.0"
    timestamp: str = ""
    audio: AudioChannel = field(default_factory=AudioChannel)
    breathing: BreathingChannel = field(default_factory=BreathingChannel)
    environment: EnvironmentChannel = field(default_factory=EnvironmentChannel)
    meta: InterventionMeta = field(default_factory=InterventionMeta)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "timestamp": self.timestamp or datetime.fromtimestamp(time.time()).isoformat(),
            "audio": self.audio.to_dict(),
            "breathing": self.breathing.to_dict(),
            "environment": self.environment.to_dict(),
            "meta": self.meta.to_dict(),
        }

    @classmethod
    def build(
        cls,
        render_instruction: object = None,    # RenderInstruction 实例
        best_prediction: object = None,       # PredictionResult 实例 (可选)
        audio_library_path: str = "",
        user_id: str = "default",
    ) -> "MultiChannelAction":
        """
        从渲染指令+推演结果构建 MultiChannelAction

        整合逻辑:
          1. 从 render_instruction 取基础参数 (tempo_bpm, volume_db, etc.)
          2. 从 best_prediction.predicted_state 取目标觉醒状态
          3. 从 best_prediction.action_id 选音频源
          4. 填充三通道
        """
        action = cls()
        action.timestamp = datetime.fromtimestamp(time.time()).isoformat()

        # --- 从 RenderInstruction 提取基础参数 ---
        ri = render_instruction
        if ri is not None:
            try:
                ri_dict = ri.to_dict() if hasattr(ri, 'to_dict') else {}
            except Exception:
                ri_dict = {}
        else:
            ri_dict = {}

        # --- 从推演结果提取干预参数 ---
        pred_dict = {}
        intervention_id = ""
        arousal_target = "calm"
        if best_prediction is not None:
            try:
                pred_dict = best_prediction.to_dict() if hasattr(best_prediction, 'to_dict') else {}
                intervention_id = pred_dict.get("id", "")
                arousal_target = pred_dict.get("predicted_state", "calm")
                action.meta.score = pred_dict.get("score", 0.0)
                action.meta.confidence = pred_dict.get("confidence", 0.5)
                action.meta.hrv_delta = pred_dict.get("hrv_delta", 0.0)
                action.meta.stress_delta = pred_dict.get("stress_delta", 0.0)
            except Exception:
                pass

        # --- 从枚举器目录拿元信息 ---
        try:
            from intervention_enumerator import INTERVENTION_CATALOG
            catalog = INTERVENTION_CATALOG.get(intervention_id, {})
            action.meta.action_id = intervention_id
            action.meta.category = catalog.get("category", "")
            action.meta.energy_cost = catalog.get("energy_cost", "low")
        except Exception:
            pass

        # --- 填充音频通道 ---
        # 策略: 优先用 mapped audio > 白噪音兜底
        audio_file = AUDIO_MAP.get(intervention_id, "")
        if audio_file:
            action.audio.file = audio_file
            action.audio.source = "recording"
        elif intervention_id.startswith("breath_"):
            break_guide = BREATH_GUIDE.get(intervention_id, {})
            action.audio.file = break_guide.get("guide_audio", "")
            action.audio.source = "guide"
        elif intervention_id in ("do_nothing", "cool_down"):
            action.audio.loop = False
        else:
            # 兜底: 无音频
            action.audio.loop = False

        # 音量从 RenderInstruction 继承
        if ri_dict.get("volume_db") is not None:
            action.audio.volume["db"] = ri_dict["volume_db"]
        if ri_dict.get("modulation") is not None:
            m = ri_dict["modulation"]
            action.audio.modulation["freq_hz"] = m.get("freq_hz", 0.0)
            action.audio.modulation["depth"] = m.get("depth", 0.0)
        if ri_dict.get("fade_in_s") is not None:
            action.audio.fade["in_s"] = ri_dict["fade_in_s"]
        if ri_dict.get("fade_out_s") is not None:
            action.audio.fade["out_s"] = ri_dict["fade_out_s"]

        # --- 填充呼吸引导通道 ---
        try:
            from intervention_enumerator import INTERVENTION_CATALOG
            cat = INTERVENTION_CATALOG.get(intervention_id, {})
            action.breathing.pattern = intervention_id.replace("breath_", "").replace("_", "-")
            action.breathing.tempo_bpm = cat.get("tempo_bpm", ri_dict.get("tempo_bpm", 6.0))
            action.breathing.in_s = cat.get("breathing_in_s", ri_dict.get("breathing", {}).get("in_s", 4.0))
            action.breathing.out_s = cat.get("breathing_out_s", ri_dict.get("breathing", {}).get("out_s", 8.0))
            action.breathing.hold_s = {"4-7-8": 7.0, "box": 4.0}.get(action.breathing.pattern, 0.0)
            action.breathing.guide["text_speed"] = cat.get("text_speed", ri_dict.get("text_speed", 0.75))
            action.breathing.guide["silence_s"] = cat.get("silence_s", ri_dict.get("silence_s", 4.0))
        except Exception:
            pass

        # --- 填充环境通道 (IoT预留) ---
        if intervention_id == "cool_down":
            action.environment.temperature["target_delta"] = -0.5
        if arousal_target in ("drowsy", "sleeping"):
            action.environment.light["brightness_pct"] = 1

        # --- 元信息 ---
        try:
            from intervention_enumerator import INTERVENTION_CATALOG
            cat = INTERVENTION_CATALOG.get(intervention_id, {})
        except Exception:
            cat = {}
        action.meta.action_id = intervention_id
        action.meta.category = cat.get("category", "")
        action.meta.energy_cost = cat.get("energy_cost", "low")
        action.meta.priority = "high" if action.meta.score > 0.7 else "normal"
        action.meta.predicted_state = arousal_target
        action.meta.timeout_s = ENERGY_TIMEOUT_MAP.get(cat.get("energy_cost", "low"), 300)
        action.meta.reasoning = (
            f"{cat.get('name', intervention_id)} → {arousal_target} "
            f"(conf={action.meta.confidence:.0%})"
        )

        # 时间戳
        action.timestamp = datetime.fromtimestamp(time.time()).isoformat()

        return action


# ============================================================
# 集成点 — 在 coordinator.step() 返回前调用
# ============================================================

def build_action(
    render_instruction: object,
    best_prediction: object = None,
    audio_library_path: str = "",
    user_id: str = "default",
) -> dict:
    """
    在 coordinator.step() 返回前调用，生成统一的 action 输出

    Args:
        render_instruction: P0渲染器的 RenderInstruction 实例
        best_prediction: 推演评估器的最优结果 (PredictionResult)
        audio_library_path: 音频库URL前缀

    Returns:
        MultiChannelAction.to_dict()
    """
    action = MultiChannelAction.build(
        render_instruction=render_instruction,
        best_prediction=best_prediction,
        audio_library_path=audio_library_path,
        user_id=user_id,
    )
    return action.to_dict()


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    # 模拟 RenderInstruction
    class MockInstruction:
        def to_dict(self):
            return {
                "tempo_bpm": 5.0,
                "text_speed": 0.72,
                "silence_s": 5.0,
                "volume_db": -3.0,
                "modulation": {"freq_hz": 0.05, "depth": 0.25},
                "fade_in_s": 8.0,
                "fade_out_s": 60.0,
                "breathing": {"in_s": 4.0, "out_s": 8.0},
            }

    # 模拟 PredictionResult
    class MockPrediction:
        def to_dict(self):
            return {
                "id": "rain_sound",
                "name": "雨声白噪音",
                "predicted_state": "drowsy",
                "score": 0.85,
                "confidence": 0.65,
                "hrv_delta": 0.3,
                "stress_delta": -0.8,
            }

    instr = MockInstruction()
    pred = MockPrediction()

    action = MultiChannelAction.build(
        render_instruction=instr,
        best_prediction=pred,
    )
    print("=== MultiChannelAction v1.0 自测 ===")
    print(json.dumps(action.to_dict(), ensure_ascii=False, indent=2))

    # 测试 do_nothing
    class NothingPrediction:
        def to_dict(self):
            return {
                "id": "do_nothing",
                "name": "继续观察",
                "predicted_state": "sleeping",
                "score": 0.3,
                "confidence": 0.9,
                "hrv_delta": 0.0,
                "stress_delta": 0.0,
            }
    action2 = MultiChannelAction.build(
        render_instruction=MockInstruction(),
        best_prediction=NothingPrediction(),
    )
    print("\n=== do_nothing 测试 ===")
    print(json.dumps(action2.to_dict(), ensure_ascii=False, indent=2))
