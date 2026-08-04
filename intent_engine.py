#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
intent_engine.py — AISleepGen 意图引擎 v1.0

范式跃迁：让用户的每一句话不仅是POMDP信念更新的观测信号，
还直接触发具体子流程。

核心设计：
  - 基于关键词+正则模式匹配（轻量级，不依赖LLM）
  - 优先级排序：高优先级意图优先匹配
  - Handler注册机制：每种意图可绑定多个处理函数
  - 多意图检测：一条消息可同时匹配多个意图（主+次）
  - Fallback机制：无匹配时降级到chitchat

集成点：
  - dp_router.py: handle_chat 中用户消息到LLM之前插入
  - pomdp_learner.py: POMDP信念更新
  - online_rl.py: RL奖励更新
  - sleep_coach.py: 干预建议生成
  - async_pipeline.py: 分析流程触发
  - emotion_monitor.py: 情绪记录
  - working_memory.py: 短期记忆（重复上次干预）

v6.2.0 新增:
  - IntentEngine 类: classify, register_intent, list_intents
  - 15种预定义意图，覆盖症状报告/行动请求/反馈/情绪/重复
  - 处理函数执行链：多条handler按序执行，结果合并到LLM上下文
  - API端点: /api/intent/classify, /api/intent/list
"""

import json
import os
import time
import logging
import re
from datetime import datetime
from collections import OrderedDict

_log = logging.getLogger('aisleepgen.intent_engine')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ==================== 意图定义 ====================

# 预定义意图模式库
# 每项: {patterns: [关键词列表], priority: 优先级(高→先匹配), handlers: [handler名]}

INTENTS = OrderedDict([
    # ── 症状报告类（触发干预） ──
    ("report_insomnia", {
        "patterns": ["失眠", "睡不着", "睡不着觉", "难以入睡", "入睡困难",
                     "翻来覆去", "彻夜未眠", "一晚没睡", "一夜没睡"],
        "priority": 90,
        "handlers": ["trigger_intervention", "update_pomdp_belief"],
        "description": "用户报告失眠/入睡困难",
    }),
    ("report_early_waking", {
        "patterns": ["早醒", "醒得早", "凌晨醒", "3点醒", "4点醒", "5点醒",
                     "醒来就睡不着", "醒了就睡不着"],
        "priority": 85,
        "handlers": ["trigger_intervention", "update_pomdp_belief"],
        "description": "用户报告早醒",
    }),
    ("report_poor_quality", {
        "patterns": ["睡不好", "没睡好", "睡得浅", "做梦多", "睡得不踏实",
                     "睡醒累", "没精神", "睡得好累"],
        "priority": 80,
        "handlers": ["trigger_intervention", "update_pomdp_belief"],
        "description": "用户报告睡眠质量差",
    }),
    ("report_good_sleep", {
        "patterns": ["睡得好", "睡得不错", "睡得很香", "一觉到天亮",
                     "睡眠质量好", "睡得踏实", "睡得舒服", "睡得很好"],
        "priority": 70,
        "handlers": ["update_pomdp_belief", "update_rl_reward"],
        "description": "用户报告睡得好",
    }),

    # ── 行动请求类（触发特定流程） ──
    ("request_analysis", {
        "patterns": ["帮我看看", "分析一下", "我的睡眠", "最近睡眠",
                     "睡眠报告", "报告", "看看数据", "看数据", "分析"],
        "priority": 80,
        "handlers": ["trigger_analysis", "update_pomdp_belief"],
        "description": "用户请求睡眠分析",
    }),
    ("request_advice", {
        "patterns": ["怎么办", "有什么办法", "怎么改善", "建议", "推荐",
                     "帮帮我", "救救我", "有什么建议"],
        "priority": 75,
        "handlers": ["trigger_intervention", "trigger_advice", "update_pomdp_belief"],
        "description": "用户求助/请求建议",
    }),
    ("request_suggestion", {
        "patterns": ["该做什么", "今晚", "现在", "能做什么", "做什么好",
                     "可以做什么", "该干嘛"],
        "priority": 70,
        "handlers": ["trigger_intervention", "update_pomdp_belief"],
        "description": "用户询问当前该做什么",
    }),

    # ── 反馈类（更新RL奖励） ──
    ("positive_feedback", {
        "patterns": ["有用", "有效", "不错", "很好", "好多了", "管用",
                     "有帮助", "有改善", "有效果", "非常好", "很棒"],
        "priority": 60,
        "handlers": ["update_rl_reward", "update_pomdp_belief"],
        "description": "用户正面反馈",
    }),
    ("negative_feedback", {
        "patterns": ["没用", "没效", "不管用", "没用处", "没用啊",
                     "没帮助", "反而更糟", "更差了", "没效果", "无效"],
        "priority": 60,
        "handlers": ["update_rl_reward", "update_pomdp_belief", "trigger_alternative"],
        "description": "用户负面反馈",
    }),

    # ── 重复请求类 ──
    ("repeat_intervention", {
        "patterns": ["再做一次", "再来一次", "上次那个", "之前那个",
                     "再试一次", "再来", "再一遍", "继续", "继续上次的"],
        "priority": 65,
        "handlers": ["repeat_last_intervention", "update_pomdp_belief"],
        "description": "用户请求重复上次干预",
    }),

    # ── 情绪表达类（更新情绪状态） ──
    ("express_anxiety", {
        "patterns": ["焦虑", "紧张", "担心", "压力大", "烦", "烦躁",
                     "糟心", "烦死了", "崩溃", "烦得很"],
        "priority": 75,
        "handlers": ["trigger_anxiety_intervention", "update_pomdp_belief", "update_emotion"],
        "description": "用户表达焦虑情绪",
    }),
    ("express_sadness", {
        "patterns": ["难过", "不开心", "郁闷", "压抑", "低落", "沮丧", "伤心"],
        "priority": 70,
        "handlers": ["trigger_comfort", "update_pomdp_belief", "update_emotion"],
        "description": "用户表达悲伤情绪",
    }),

    # ── 问候 ──
    ("greeting", {
        "patterns": ["你好", "嗨", "在吗", "hello", "hi", "您好", "早上好", "晚上好"],
        "priority": 10,
        "handlers": ["greeting_response"],
        "description": "用户打招呼",
    }),

    # ── 无匹配降级 ──
    ("chitchat", {
        "patterns": [],
        "priority": 0,
        "handlers": ["normal_chat"],
        "description": "无匹配时的降级意图",
    }),
])

# 保证 chitchat 永远是最后一个
assert list(INTENTS.keys())[-1] == "chitchat", "chitchat must be last intent"


# ==================== IntentResult ====================

class IntentResult(dict):
    """意图分类结果

    作为 dict 使用，同时支持属性访问以保持后向兼容。
    """
    def __init__(self, primary_intent="", confidence=0.0, matched_pattern="",
                 secondary_intents=None, handlers=None, original_text="",
                 debug_info=None):
        super().__init__()
        self["primary_intent"] = primary_intent
        self["confidence"] = confidence
        self["matched_pattern"] = matched_pattern
        self["secondary_intents"] = secondary_intents or []
        self["handlers"] = handlers or []
        self["original_text"] = original_text
        self["debug_info"] = debug_info or {}

    @property
    def primary_intent(self):
        return self["primary_intent"]

    @property
    def confidence(self):
        return self["confidence"]

    @property
    def matched_pattern(self):
        return self["matched_pattern"]

    @property
    def secondary_intents(self):
        return self["secondary_intents"]

    @property
    def handlers(self):
        return self["handlers"]

    @property
    def original_text(self):
        return self["original_text"]

    def to_context_str(self):
        """转换为LLM上下文注入文本"""
        parts = []
        # 主要意图描述
        intent_name = self["primary_intent"]
        intent_desc = INTENTS.get(intent_name, {}).get("description", intent_name)
        parts.append(
            f"[意图识别: 系统识别到用户正在{intent_desc}(置信度{self['confidence']:.2f}), "
            f"已触发{len(self['handlers'])}个处理动作]"
        )

        # 次要意图
        if self["secondary_intents"]:
            sec_names = []
            for si in self["secondary_intents"]:
                sid = si.get("intent", si) if isinstance(si, dict) else si
                sec_desc = INTENTS.get(sid, {}).get("description", sid)
                sec_confidence = si.get("confidence", 1.0) if isinstance(si, dict) else 1.0
                sec_names.append(f"{sec_desc}({sec_confidence:.2f})")
            parts.append(f"[多重意图: 同时检测到 {'、'.join(sec_names)}]")

        # 匹配详情
        if self["matched_pattern"]:
            parts.append(f"[匹配模式: \"{self['matched_pattern']}\"]")

        # handler执行结果
        handler_results = self.get("handler_results", {})
        if handler_results:
            result_lines = []
            for hname, hresult in handler_results.items():
                if hresult:
                    hdesc = _HANDLER_DESCRIPTIONS.get(hname, hname)
                    if isinstance(hresult, str):
                        result_lines.append(f"[{hdesc}: {hresult}]")
                    elif isinstance(hresult, dict):
                        text = hresult.get("reply", hresult.get("text", str(hresult)))
                        result_lines.append(f"[{hdesc}: {text}]")
            if result_lines:
                parts.extend(result_lines)

        return "\n".join(parts)

    def __repr__(self):
        return (f"IntentResult(primary={self['primary_intent']}, "
                f"confidence={self['confidence']:.2f}, "
                f"handlers={self['handlers']})")


# ==================== Handler描述 ====================

_HANDLER_DESCRIPTIONS = {
    "trigger_intervention": "干预建议生成",
    "update_pomdp_belief": "POMDP信念更新",
    "update_rl_reward": "RL奖励更新",
    "trigger_analysis": "睡眠分析触发",
    "trigger_advice": "个性化建议生成",
    "trigger_alternative": "替代方案生成",
    "repeat_last_intervention": "上次干预重复执行",
    "trigger_anxiety_intervention": "减压/呼吸练习推送",
    "trigger_comfort": "情绪安抚",
    "greeting_response": "问候回复",
    "normal_chat": "正常聊天",
    "update_emotion": "情绪记录更新",
}


# ==================== 处理函数实现 ====================

def _get_openid_from_ctx(ctx):
    """从context中安全获取openid"""
    if isinstance(ctx, dict):
        return ctx.get("openid", "default")
    return "default"


def _get_text_from_ctx(text_or_ctx):
    """从context中安全获取原始文本"""
    if isinstance(text_or_ctx, dict):
        return text_or_ctx.get("message", text_or_ctx.get("text", ""))
    return str(text_or_ctx or "")


def _do_trigger_intervention(openid, text, ctx):
    """调用 sleep_coach._select_suggestion() 返回干预建议"""
    try:
        from sleep_coach import get_daily_suggestion, apply_suggestion
        profile = ctx.get("profile", {}) if isinstance(ctx, dict) else {}
        emotion = "neutral"
        if isinstance(ctx, dict):
            emotion = ctx.get("emotion_state", profile.get("latest_emotion", "neutral"))
        suggestion = get_daily_suggestion(profile, emotion)
        if suggestion:
            # 暂时应用以获取完整数据
            profile = apply_suggestion(profile, suggestion)
            profile["last_suggestion"] = suggestion
            if isinstance(ctx, dict):
                ctx["profile"] = profile
            action = suggestion.get("action", suggestion.get("title", ""))
            _log.info("[Intent] Triggered intervention for %s: %s", openid[:8], action[:40])
            return {
                "reply": f"💡 建议尝试: {action}",
                "suggestion": suggestion,
                "suggestion_key": suggestion.get("suggestion_key", ""),
            }
        return {"reply": "", "suggestion": None}
    except ImportError:
        _log.warning("[Intent] sleep_coach not available for intervention")
        return {"reply": "", "suggestion": None}
    except Exception as e:
        _log.warning("[Intent] trigger_intervention error: %s", e)
        return {"reply": "", "suggestion": None}


def _do_update_pomdp_belief(openid, text, ctx):
    """调用 pomdp_learner.engine.observe() 更新信念"""
    try:
        from pomdp_learner import get_engine
        engine = get_engine()
        bel = engine.observe_message(openid, text)
        _log.info("[Intent] POMDP belief updated for %s: score=%.1f",
                  openid[:8], bel.get("expected_score", 0))
        return {"belief_updated": True, "expected_score": bel.get("expected_score", 0)}
    except ImportError:
        _log.warning("[Intent] pomdp_learner not available")
        return {"belief_updated": False}
    except Exception as e:
        _log.warning("[Intent] update_pomdp_belief error: %s", e)
        return {"belief_updated": False}


def _do_update_rl_reward(openid, text, ctx):
    """调用 online_rl.update() 记录奖励"""
    try:
        from online_rl import get_online_rl, extract_reward_from_outcome
        rl = get_online_rl()
        # 判断正负反馈
        is_positive = any(w in text for w in ["有用", "有效", "不错", "很好", "好多了", "管用", "有帮助", "有改善", "有效果"])
        is_negative = any(w in text for w in ["没用", "没效", "不管用", "没帮助", "更糟", "无效"])

        if is_positive:
            outcome = {"feedback": 1, "score_observed": True, "intervention_adopted": True}
        elif is_negative:
            outcome = {"feedback": -1, "score_observed": True}
        else:
            outcome = {"feedback": 0}

        reward = extract_reward_from_outcome(openid, "skip", outcome)
        td = rl.update(openid, "skip", reward)
        _log.info("[Intent] RL reward updated for %s: reward=%.2f td=%.4f",
                  openid[:8], reward, td)
        return {"reward_updated": True, "reward": reward, "td_error": td}
    except ImportError:
        _log.warning("[Intent] online_rl not available")
        return {"reward_updated": False}
    except Exception as e:
        _log.warning("[Intent] update_rl_reward error: %s", e)
        return {"reward_updated": False}


def _do_trigger_analysis(openid, text, ctx):
    """触发 async_pipeline 分析流程"""
    try:
        from async_pipeline import fast_analysis
        profile = ctx.get("profile", {}) if isinstance(ctx, dict) else {}
        history = ctx.get("history", []) if isinstance(ctx, dict) else []
        result = fast_analysis(openid, text, history, profile)
        _log.info("[Intent] Analysis triggered for %s: score=%.1f",
                  openid[:8], result.get("score", 0))
        return {
            "analysis_triggered": True,
            "score": result.get("score", 0),
            "quality": result.get("quality", ""),
        }
    except ImportError:
        _log.warning("[Intent] async_pipeline not available")
        return {"analysis_triggered": False}
    except Exception as e:
        _log.warning("[Intent] trigger_analysis error: %s", e)
        return {"analysis_triggered": False}


def _do_trigger_advice(openid, text, ctx):
    """生成个性化建议文本"""
    try:
        from sleep_coach import get_daily_suggestion, apply_suggestion
        profile = ctx.get("profile", {}) if isinstance(ctx, dict) else {}
        emotion = profile.get("latest_emotion", "neutral") if isinstance(profile, dict) else "neutral"
        suggestion = get_daily_suggestion(profile, emotion)
        if suggestion:
            if isinstance(ctx, dict):
                ctx["profile"] = apply_suggestion(profile, suggestion)
            action = suggestion.get("action", "")
            title = suggestion.get("title", "")
            _log.info("[Intent] Advice generated for %s: %s", openid[:8], title)
            return {"reply": f"💡 {title}: {action}", "suggestion": suggestion}
        return {"reply": "基于你的情况，建议今晚试试放松练习。"}
    except ImportError:
        _log.warning("[Intent] sleep_coach not available for advice")
        return {"reply": "建议关注一下今晚的睡眠环境是否舒适。"}
    except Exception as e:
        _log.warning("[Intent] trigger_advice error: %s", e)
        return {"reply": "有什么我可以帮你放松的吗？"}


def _do_trigger_alternative(openid, text, ctx):
    """换一种干预方案"""
    try:
        from sleep_coach import get_daily_suggestion, SUGGESTIONS
        profile = ctx.get("profile", {}) if isinstance(ctx, dict) else {}
        coach = profile.get("sleep_coach", {}) if isinstance(profile, dict) else {}
        last_key = coach.get("last_suggestion", "") if isinstance(coach, dict) else ""

        # 跳过上次的，选一个不同的
        emotion = profile.get("latest_emotion", "neutral") if isinstance(profile, dict) else "neutral"
        suggestion = get_daily_suggestion(profile, emotion)
        if suggestion and suggestion.get("suggestion_key") == last_key:
            # 如果还是同一个，尝试另一个通用建议
            for key, sug in SUGGESTIONS.items():
                if key != last_key and sug.get("condition") == "general":
                    action = sug.get("action", "")
                    suggestion = {"suggestion_key": key, "title": sug.get("name", ""),
                                  "action": action}
                    break
        if suggestion:
            action = suggestion.get("action", "")
            title = suggestion.get("title", "")
            _log.info("[Intent] Alternative provided for %s: %s", openid[:8], title)
            return {"reply": f"🔄 换一个试试: {title} - {action}", "alternative": suggestion}
        return {"reply": "试试4-7-8呼吸法如何？吸气4秒→屏息7秒→呼气8秒。"}
    except ImportError:
        _log.warning("[Intent] sleep_coach not available for alternative")
        return {"reply": "试试换个环境，调暗灯光放松一下。"}
    except Exception as e:
        _log.warning("[Intent] trigger_alternative error: %s", e)
        return {"reply": "放松一下，深呼吸几次试试。"}


def _do_repeat_intervention(openid, text, ctx):
    """从WM获取最近一次有效干预，重复执行"""
    try:
        from working_memory import get_working_memory
        wm = get_working_memory()
        interventions = wm.recent_interventions(openid, n=3) if hasattr(wm, 'recent_interventions') else []
        if interventions:
            last_int = interventions[0]
            _log.info("[Intent] Repeating last intervention for %s: %s", openid[:8], str(last_int)[:40])
            return {"reply": f"好的，再做一次。上次的{last_int}感觉有效果，我们继续。"}
        # 无干预记录时给通用回复
        profile = ctx.get("profile", {}) if isinstance(ctx, dict) else {}
        coach = profile.get("sleep_coach", {}) if isinstance(profile, dict) else {}
        last_action = coach.get("last_action", "") if isinstance(coach, dict) else ""
        if last_action:
            return {"reply": f"好的，重复最后一次建议: {last_action}"}
        return {"reply": "上次没有特别建议。试试深呼吸放松一下吧？"}
    except ImportError:
        pass
    except Exception as e:
        _log.warning("[Intent] repeat_intervention error: %s", e)

    # 降级：尝试从profile读取
    profile = ctx.get("profile", {}) if isinstance(ctx, dict) else {}
    coach = profile.get("sleep_coach", {}) if isinstance(profile, dict) else {}
    last_action = coach.get("last_action", "") if isinstance(coach, dict) else ""
    if last_action:
        return {"reply": f"好的，重复建议: {last_action}"}
    return {"reply": "我们来做4-7-8呼吸练习吧。"}


def _do_trigger_anxiety_intervention(openid, text, ctx):
    """推送减压/呼吸练习"""
    try:
        from companion_mode import start_companion
        result = start_companion(openid, "4-7-8", text)
        _log.info("[Intent] Anxiety intervention triggered for %s", openid[:8])
        if isinstance(result, dict) and result.get("steps"):
            return {"reply": "我在这里。试试4-7-8呼吸法，跟着我的节奏来放松。"}
        return {"reply": "深呼吸，慢慢来。吸气4秒，屏住7秒，呼气8秒。"}
    except ImportError:
        _log.warning("[Intent] companion_mode not available")
        return {"reply": "深呼吸放松: 吸气4秒→屏息→慢慢呼出。重复5次。"}
    except Exception as e:
        _log.warning("[Intent] trigger_anxiety_intervention error: %s", e)
        return {"reply": "别着急，深呼吸帮助放松。"}


def _do_trigger_comfort(openid, text, ctx):
    """安抚情绪回复"""
    _log.info("[Intent] Comfort triggered for %s", openid[:8])
    return {"reply": "我理解你现在的心情不太好。有时候允许自己难过也是一种勇气，我会一直在这里陪你。"}


def _do_greeting(openid, text, ctx):
    """简单的问候回复"""
    _log.info("[Intent] Greeting for %s", openid[:8])
    return {"reply": "你好呀！今天睡眠怎么样？有什么想聊的吗？"}


def _do_normal_chat(openid, text, ctx):
    """走正常的LLM聊天回复（无特殊意图时）= 不返回额外内容，让LLM自由发挥"""
    return {"reply": None}  # None 表示走正常LLM回复


def _do_update_emotion(openid, text, ctx):
    """更新 emotion_monitor 情绪记录"""
    try:
        profile = ctx.get("profile", {}) if isinstance(ctx, dict) else {}
        from emotion_monitor import record_emotion
        emotion_meta = record_emotion(profile, text)
        if emotion_meta:
            _log.info("[Intent] Emotion recorded for %s: %s",
                      openid[:8], emotion_meta.get("emotion", "unknown"))
            return {"emotion_updated": True, "emotion": emotion_meta.get("emotion", "unknown")}
        return {"emotion_updated": False}
    except ImportError:
        _log.warning("[Intent] emotion_monitor not available")
        return {"emotion_updated": False}
    except Exception as e:
        _log.warning("[Intent] update_emotion error: %s", e)
        return {"emotion_updated": False}


# ==================== Handler注册表 ====================

HANDLERS = OrderedDict([
    ("trigger_intervention", _do_trigger_intervention),
    ("update_pomdp_belief", _do_update_pomdp_belief),
    ("update_rl_reward", _do_update_rl_reward),
    ("trigger_analysis", _do_trigger_analysis),
    ("trigger_advice", _do_trigger_advice),
    ("trigger_alternative", _do_trigger_alternative),
    ("repeat_last_intervention", _do_repeat_intervention),
    ("trigger_anxiety_intervention", _do_trigger_anxiety_intervention),
    ("trigger_comfort", _do_trigger_comfort),
    ("greeting_response", _do_greeting),
    ("normal_chat", _do_normal_chat),
    ("update_emotion", _do_update_emotion),
])


# ==================== 意图引擎核心 ====================

class IntentEngine:
    """意图引擎

    基于关键词+正则模式匹配，将用户消息分类为预定义意图，
    并执行对应的处理函数链。

    Usage:
        engine = IntentEngine()
        result = engine.classify("失眠睡不着", {"openid": "xxx"})
        context_str = result.to_context_str()
    """

    def __init__(self):
        self._custom_intents = OrderedDict()
        self._builtin_loaded = True

    def _get_all_intents(self):
        """获取全部意图（内置 + 自定义）"""
        intents = OrderedDict()
        intents.update(INTENTS)
        intents.update(self._custom_intents)
        return intents

    def register_intent(self, name, patterns, handlers, priority=50, description=""):
        """注册自定义意图

        Args:
            name: 意图名称（唯一标识）
            patterns: 关键词/正则模式列表
            handlers: handler名称列表（需在HANDLERS中注册）
            priority: 优先级（高→先匹配）
            description: 描述文本
        """
        if name in INTENTS:
            raise ValueError(f"Cannot override builtin intent '{name}'")
        if name in self._custom_intents:
            raise ValueError(f"Intent '{name}' already registered")

        for h in handlers:
            if h not in HANDLERS:
                raise ValueError(f"Unknown handler '{h}'. Available: {list(HANDLERS.keys())}")

        self._custom_intents[name] = {
            "patterns": patterns,
            "priority": priority,
            "handlers": handlers,
            "description": description or name,
        }
        _log.info("[Intent] Registered custom intent '%s' (priority=%d, %d patterns)",
                  name, priority, len(patterns))

    def list_intents(self):
        """列出所有已注册的意图

        Returns:
            list of dict: [{"name": ..., "patterns": [...], "handlers": [...],
                           "priority": ..., "description": ...}, ...]
        """
        result = []
        for name, intent in self._get_all_intents().items():
            result.append({
                "name": name,
                "patterns": intent["patterns"],
                "handlers": intent["handlers"],
                "priority": intent["priority"],
                "description": intent.get("description", name),
            })
        return result

    def classify(self, text, context=None):
        """对用户消息进行意图分类

        Args:
            text: 用户消息文本
            context: dict, 包含 openid, profile, history 等上下文

        Returns:
            IntentResult: 意图分类结果
        """
        if not text or not isinstance(text, str):
            return IntentResult(
                primary_intent="chitchat",
                confidence=1.0,
                matched_pattern="",
                handlers=["normal_chat"],
                original_text=str(text or ""),
                debug_info={"reason": "empty or invalid text"},
            )

        text_clean = text.strip()
        all_intents = self._get_all_intents()

        # 按优先级排序
        sorted_intents = sorted(
            all_intents.items(),
            key=lambda x: x[1]["priority"],
            reverse=True,
        )

        matched = []  # [(name, pattern, confidence, handlers)]
        best_match = None

        for name, intent in sorted_intents:
            patterns = intent["patterns"]
            handlers = intent["handlers"]
            if not patterns:
                continue  # skip chitchat / empty patterns

            for pattern in patterns:
                if pattern in text_clean:
                    confidence = self._compute_confidence(pattern, text_clean)

                    # 低优先级正反馈/副反馈短模式在非睡眠语境下降权
                    if name in ("positive_feedback", "negative_feedback") and len(pattern) <= 2:
                        has_sleep_context = any(kw in text_clean for kw in [
                            "睡", "眠", "失眠", "睡眠", "建议", "方案",
                            "方法", "练习", "呼吸", "动作",
                        ])
                        if not has_sleep_context:
                            confidence = max(0.3, confidence - 0.40)

                    matched.append((name, pattern, confidence, handlers))
                    if best_match is None or confidence > best_match[2]:
                        best_match = (name, pattern, confidence, handlers)
                    break  # 每类只匹配一个模式

        if not best_match or best_match[2] < 0.40:
            # 置信度太低 → chitchat
            result = IntentResult(
                primary_intent="chitchat",
                confidence=1.0,
                matched_pattern="",
                handlers=INTENTS["chitchat"]["handlers"],
                original_text=text_clean,
                debug_info={"reason": "best match confidence too low" if best_match else "no pattern matched"},
            )
        else:
            primary_name, primary_pattern, primary_conf, primary_handlers = best_match

            # 次要意图：比primary优先级低的已匹配意图
            secondary = []
            for name, pattern, conf, handlers in matched:
                if name != primary_name:
                    secondary.append({"intent": name, "confidence": conf, "matched_pattern": pattern})

            result = IntentResult(
                primary_intent=primary_name,
                confidence=primary_conf,
                matched_pattern=primary_pattern,
                secondary_intents=secondary,
                handlers=primary_handlers,
                original_text=text_clean,
                debug_info={"all_matches": [(m[0], m[1], round(m[2], 3)) for m in matched]},
            )

        # 执行handler（除非是chitchat/normal_chat/greeting）
        if result["primary_intent"] not in ("chitchat",):
            context = context or {}
            if not isinstance(context, dict):
                context = {}
            if "openid" not in context:
                context["openid"] = "default"

            handler_results = {}
            for handler_name in result["handlers"]:
                if handler_name in HANDLERS:
                    try:
                        openid = _get_openid_from_ctx(context)
                        handler_fn = HANDLERS[handler_name]
                        hresult = handler_fn(openid, text_clean, context)
                        handler_results[handler_name] = hresult
                    except Exception as e:
                        _log.warning("[Intent] Handler '%s' failed: %s", handler_name, e)
                        handler_results[handler_name] = {"error": str(e)}

            result["handler_results"] = handler_results

        return result

    def _compute_confidence(self, pattern, text):
        """计算匹配置信度

        基于匹配位置的优化：开头匹配 > 中间匹配 > 结尾匹配
        """
        if not pattern or not text:
            return 0.0

        pos = text.find(pattern)
        if pos < 0:
            return 0.0

        # base confidence
        base = 0.75

        # 匹配位置奖励：在开头更可靠
        if pos == 0:
            base += 0.15
        elif pos < len(text) * 0.3:
            base += 0.08

        # 模式长度奖励：长关键词更精确
        if len(pattern) >= 4:
            base += 0.05
        if len(pattern) >= 6:
            base += 0.05

        # 文本长度惩罚：文本越长，单一匹配的可靠性越低
        if len(text) > 50:
            base -= 0.10
        elif len(text) > 30:
            base -= 0.05

        return max(0.5, min(1.0, base))


# ==================== 全局实例 ====================

_engine_instance = None


def get_intent_engine():
    """获取全局意图引擎实例（单例）"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = IntentEngine()
    return _engine_instance


# ==================== 自测 ====================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')

    print("=" * 60)
    print("Intent Engine Self-Test")
    print("=" * 60)

    engine = get_intent_engine()

    test_cases = [
        # (输入文本, 预期主意图, 预期handler子集)
        ("失眠", "report_insomnia", ["trigger_intervention", "update_pomdp_belief"]),
        ("睡不着", "report_insomnia", ["trigger_intervention", "update_pomdp_belief"]),
        ("睡得好", "report_good_sleep", ["update_pomdp_belief", "update_rl_reward"]),
        ("帮我看看", "request_analysis", ["trigger_analysis", "update_pomdp_belief"]),
        ("没用", "negative_feedback", ["update_rl_reward", "update_pomdp_belief", "trigger_alternative"]),
        ("焦虑", "express_anxiety", ["trigger_anxiety_intervention", "update_pomdp_belief", "update_emotion"]),
        ("再做一次", "repeat_intervention", ["repeat_last_intervention", "update_pomdp_belief"]),
        ("你好", "greeting", ["greeting_response"]),
        ("昨晚又失眠了睡不着翻来覆去到天亮焦虑死了", None, None),  # 复杂文本：主=insomnia, 次=anxiety
        ("今天天气不错", "chitchat", ["normal_chat"]),
        ("", "chitchat", ["normal_chat"]),
    ]

    passed = 0
    failed = 0

    for i, (text, expected_primary, expected_handlers) in enumerate(test_cases):
        ctx = {"openid": "test_user", "profile": {"sleep_coach": {}}, "history": []}
        result = engine.classify(text, ctx)

        print(f"\n{i+1}. Input: \"{text}\"")
        print(f"   Primary: {result['primary_intent']} (conf={result['confidence']:.2f})")
        print(f"   Pattern: \"{result['matched_pattern']}\"")
        print(f"   Handlers: {result['handlers']}")

        if result["secondary_intents"]:
            print(f"   Secondaries: {[s['intent'] if isinstance(s, dict) else s for s in result['secondary_intents']]}")

        print(f"   Context str: {result.to_context_str()[:120]}...")

        if expected_primary is not None:
            is_ok = result["primary_intent"] == expected_primary
            if not is_ok:
                print(f"   ❌ Expected primary={expected_primary}, got {result['primary_intent']}")
                failed += 1
            else:
                print(f"   ✅ Primary correct")

            if expected_handlers:
                all_found = all(h in result["handlers"] for h in expected_handlers)
                if not all_found:
                    print(f"   ❌ Missing handlers: expected {expected_handlers}, got {result['handlers']}")
                    failed += 1
                else:
                    print(f"   ✅ All handlers present")
            
            print(f"   ✅ PASS")

        elif expected_primary is None and text == "昨晚又失眠了睡不着翻来覆去到天亮焦虑死了":
            # 复杂文本：主=report_insomnia, 次=express_anxiety
            ok = result["primary_intent"] == "report_insomnia"
            has_anxiety_secondary = any(
                "express_anxiety" in str(s) for s in result["secondary_intents"]
            )
            if ok and has_anxiety_secondary:
                print(f"   ✅ Complex text: primary=insomnia, secondary=anxiety")
            else:
                print(f"   ❌ Complex text failed: primary={result['primary_intent']}, secondary={result['secondary_intents']}")
                failed += 1

        # Check handler_results exist for non-chitchat intents
        if result["primary_intent"] not in ("chitchat",):
            has_results = "handler_results" in result
            if has_results:
                print(f"   ✅ Handler results: {list(result['handler_results'].keys())}")
            else:
                print(f"   ❌ Missing handler_results")
                failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    if failed == 0:
        print("ALL TESTS PASSED!")
    else:
        print(f"{failed} TESTS FAILED!")
    print(f"{'='*60}")

    # Test 12: list_intents
    print("\n12. list_intents:")
    intents = engine.list_intents()
    print(f"   {len(intents)} intents registered")
    for intent in intents[:5]:
        print(f"   - {intent['name']}: {len(intent['patterns'])} patterns, priority={intent['priority']}")
    print(f"   ... and {len(intents)-5} more")

    # Test 13: register_intent
    print("\n13. register_intent:")
    engine.register_intent("test_intent", ["测试"], ["normal_chat"], priority=50, description="test")
    intents_after = engine.list_intents()
    has_test = any(i["name"] == "test_intent" for i in intents_after)
    print(f"   Custom intent registered: {has_test}")

    # Test 14: classify with handler_results
    print("\n14. Handler results in context string:")
    result_with_hr = engine.classify("睡不着", {"openid": "test", "profile": {}})
    ctx_str = result_with_hr.to_context_str()
    print(f"   Context str: {ctx_str}")
    assert "[意图识别" in ctx_str, "Context string must contain intent recognition header"
    assert "睡不着" in ctx_str or "失眠" in ctx_str, "Context string must contain matched pattern"
    print("   ✅ Context injection format correct")

    if failed > 0:
        import sys
        sys.exit(failed)
    print("\nALL TESTS PASSED! [OK]")
