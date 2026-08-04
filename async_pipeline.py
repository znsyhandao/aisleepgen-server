#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
async_pipeline.py — 异步管道层

核心：把用户请求拆为"快速本地答案"+"后台深度分析"。
让用户感知延迟从 5-8s 降至 <100ms。

流程：
  1. 快速通道：本地规则分析（世界模型 3ms）+ 缓存检查
  2. 立即回复用户（利用缓存或模板）
  3. 后台线程：调 DeepSeek API
  4. 结果存 buffer，下次用户发消息时合并上下文
"""

import json
import time
import threading
import logging
from collections import OrderedDict
from datetime import datetime

_log = logging.getLogger('aisleepgen.async_pipeline')
_ap_log = _log


def _inject_llm_context_to_pomdp(openid, message, wm_result, profile):
    """从LLM分析结果提取结构化观测注入POMDP"""
    try:
        from pomdp_learner import get_engine
        engine = get_engine()

        score = wm_result.get('total_score', 0)
        risk_flags = wm_result.get('risk_flags', '')
        debate = wm_result.get('expert_debate', {})

        # 1. 评分观测
        if score > 0:
            engine.observe_survey(openid, score=score, time_of_day='night', feedback=1)

        # 2. 压力检测
        stress_kw = ['焦虑', '压力', '紧张', '抑郁', '疲劳']
        stress = any(k in risk_flags for k in stress_kw)
        if not stress and isinstance(debate, dict):
            for v in debate.values():
                t = str(v.get('text', ''))
                if any(k in t for k in stress_kw):
                    stress = True
                    break
        if stress:
            engine.observe(openid, text='压力大 LLM标记')

        # 3. 低置信度→负反馈
        cf = wm_result.get('confidence', 0.5)
        if 0 < cf < 0.3:
            engine.observe_survey(openid, score=score, time_of_day='night', feedback=0)
    except ImportError:
        pass
    except Exception as e:
        _log.warning('[POMDP inj] %s', e)

# ===== 结果缓冲区 =====
# {openid: {result, ts, consumed}}
_DEEP_BUFFER = {}
_DEEP_LOCK = threading.RLock()
_DEEP_BUFFER_TTL = 3600  # 1小时过期


# ===== 快速通道（本地分析，不调 API）=====

def fast_analysis(openid, message, history, profile):
    """快速本地分析，不调DeepSeek API

    在 <100ms 内完成所有本地计算并返回结果。
    世界模型本身只花 3ms，这里做完整本地管道。

    v7.2: 集成 neural_extractor，让快速回复也基于提取数据

    Returns:
        dict: {reply, score, quality, debate, has_deep_result}
    """
    t0 = time.time()

    # 1. 检查是否有后台深度分析结果
    deep_result = _consume_deep_result(openid)
    has_deep = deep_result is not None

    # 2. 世界模型（本地，3ms）
    from sleep_world_model import WorldModelEngine
    wm = WorldModelEngine()
    wm_result = wm.comprehensive_analysis(message) if isinstance(message, str) else wm.comprehensive_analysis(message)
    score = wm_result.get('total_score', 0)
    quality = wm_result.get('quality', '')
    debate = wm_result.get('expert_debate', {})

    # ===== v3.13: LLM分析结果 → POMDP结构化观测注入 =====
    _inject_llm_context_to_pomdp(openid, message, wm_result, profile)

    # 3. 睡眠教练建议
    coach_suggestion = None
    try:
        from sleep_coach import get_daily_suggestion, apply_suggestion
        coach_sug = get_daily_suggestion(profile)
        if coach_sug:
            profile = apply_suggestion(profile, coach_sug)
            coach_suggestion = coach_sug
    except Exception:
        pass

    # ===== v7.2: 从提取数据生成快速回复 =====
    # 注意：快速路径中 neural_extractor 不走 DeepSeek（避免延迟）
    # DeepSeek 由 dp_router 的 _sync_deepseek_call 单独调
    _extracted = None
    try:
        from neural_extractor import NeuralExtractor
        _ne = NeuralExtractor(prefer_llm=False)
        _extracted = _ne.extract(str(message))
    except Exception:
        pass

    # 4. 生成快速回复
    reply = _build_fast_reply(openid, message, score, quality, coach_suggestion, has_deep, deep_result, extracted_fields=_extracted)

    elapsed = (time.time() - t0) * 1000
    _log.info('[AsyncPipeline] Fast reply for %s: %.1fms (has_deep=%s)',
              openid[:8], elapsed, has_deep)

    return {
        'reply': reply,
        'score': score,
        'quality': quality,
        'debate': debate,
        'expert_detail': wm_result.get('expert_detail', {}) if isinstance(wm_result, dict) else {},
        'coach_suggestion': coach_suggestion,
        'has_deep_result': has_deep,
        'elapsed_ms': round(elapsed, 1),
        'local_only': True,
    }


def _build_fast_reply(openid, message, score, quality, coach_sug, has_deep, deep_result, extracted_fields=None):
    """构建快速回复

    策略：
      - 有后台 DeepSeek 结果 → 用它（最好情况）
      - 有缓存 → 返回缓存的完整回复
      - 有 neural_extractor 提取数据 → 用它生成精准回复（v7.2）
      - 只有本地分析 → 生成精简版回复 + 告知后台分析中
    """
    # 最好情况：后台分析已完成
    if has_deep and deep_result and deep_result.get('deep_reply'):
        reply = deep_result['deep_reply']
        if coach_sug:
            reply += '\n\n💡 **今晚小建议**：' + coach_sug['action']
        return reply

    # 次好：有 DeepSeek 缓存
    try:
        from cache_layer import get_ds_cache
        cached = get_ds_cache(openid, message)
        if cached:
            if coach_sug:
                cached += '\n\n💡 **今晚小建议**：' + coach_sug['action']
            return cached
    except Exception:
        pass

    # ===== v7.2: Neural Extractor 精准回复 =====
    if extracted_fields:
        info = {k: v for k, v in extracted_fields.items()
                if v is not None and v is not False and k not in ('determined', 'confidence', 'key_complaint')}
        if len(info) >= 2:
            # 用 fallback 引擎走数据驱动回复
            try:
                from fallback_replies import generate_fallback_reply
                fallback_msg = str(message)
                fallback = generate_fallback_reply(
                    message=fallback_msg,
                    wm_result={'total_score': score, 'quality': quality},
                    fields=extracted_fields,
                    persona=None,
                )
                if fallback and len(fallback) > 10:
                    if coach_sug:
                        fallback += '\n\n💡 **今晚小建议**：' + coach_sug['action']
                    _log.info('[AsyncPipeline] NeuralExtract fast reply for %s (%d fields)',
                              openid[:8], len(info))
                    return fallback
            except Exception as e:
                _log.warning('[AsyncPipeline] NeuralExtract reply failed: %s', e)

    # 本地模式：用世界模型评分生成简短回复
    raw_msg = message or ''

    # 1. 先检测是否质疑/纠正评分
    import re as _re
    is_score_dispute = bool(_re.search(
        r'评分.*(?:不对|错|怎么|什么|才|就|太低|太高|不准)|'
        r'(?:不对|错|准不准|有误).*评分|'
        r'分数.*(?:不对|错|有误|太低|太高)|'
        r'这个分|那个分|'
        r'分给.*(?:错|低|高)|'
        r'才.*分|就.*分|'
        r'评分.*(?:质疑|怀疑|奇怪|奇怪)',
        raw_msg
    ))

    if is_score_dispute:
        from sleep_world_model import comprehensive_analysis as _wm_analyze
        _wm = _wm_analyze(profile) if isinstance(profile, dict) else None
        if _wm and isinstance(_wm, dict):
            _debate = _wm.get('debate', {})
            _consensus = _debate.get('consensus_confidence', 0) if isinstance(_debate, dict) else 0
            _disagreement = _debate.get('disagreement_gap', 0) if isinstance(_debate, dict) else 0
        else:
            _consensus = 0
            _disagreement = 0

        base = '你说得对，我来解释一下这个评分是怎么来的'
        if _consensus > 0.3:
            base += '。10位专家的共识度较高（{}%），评分主要基于{}'.format(
                round(_consensus * 100), '你填的睡眠数据'
            )
        else:
            base += '。几位专家之间存在分歧（差距{}分），主要是因为当前数据还不够完整'.format(
                round(_disagreement, 1)
            )
        base += '。如果你觉得评分和你的实际感受不符，可以补充更多细节（比如入睡时间、醒来次数），我会重新分析。'
    else:
        # 2. 检测 how-to 问题
        howto_keywords = ['怎么提高', '怎么改善', '如何提高', '如何改善', '怎样提高', '怎样改善',
                          '怎么提升', '如何提升', '怎么让', '怎么睡', '怎么快速',
                          '睡不好怎么办', '总是醒怎么办', '怎么做',
                          '怎么增加深睡', '怎么减少浅睡', '深睡太少了',
                          'how to improve', 'how to sleep']
        is_howto = any(kw in raw_msg for kw in howto_keywords)
        score_int = int(score) if isinstance(score, (int, float)) else 0

        if is_howto:
            base = '关于如何改善睡眠'
            if score_int < 60:
                base += '，当前评分偏低（{}分），以下是具体的改善方向'.format(score_int)
            elif score_int < 80:
                base += '，当前评分{}分，还有改善空间'.format(score_int)
            else:
                base += '，当前评分{}分，以下建议帮你更优'.format(score_int)
        elif score_int > 75:
            base = '今晚看起来不错呢。'
        elif score_int > 50:
            base = '今晚状态还行，有点小波动。'
        else:
            base = '今晚有点不太理想呢。'


    if coach_sug:
        base += '\n\n💡 **今晚小建议**：' + coach_sug['action']

    base += '\n\n〰️ 先看看以上分析，深度解读马上就来'
    return base


# ===== 后台深度分析 =====

def _run_deep_analysis(openid, message, history, profile):
    """后台运行深度分析（在独立线程中）

    调的 DeepSeek API + 完整决策引擎。
    结果存到 _DEEP_BUFFER，下次用户请求时取出。
    """
    try:
        t0 = time.time()

        # 1. DeepSeek API 调用
        from dp_data import call_deepseek_api
        from chat_prompt_builder import build_system_content, build_messages
        from safeguards import validate_reply, record_api_call

        # 构建 prompt
        sc = build_system_content(openid, profile)
        messages = build_messages(sc, history, message)
        reply = call_deepseek_api(messages)

        # 用真实 openid 覆盖 token 追踪
        if reply:
            from ai_client import track_usage_with_openid, load_tier_config, get_tier_from_profile
            _tier = load_tier_config(get_tier_from_profile(profile))
            track_usage_with_openid(openid, _tier.get('model', 'deepseek-chat'),
                                    len(str(messages)) // 2, len(reply) // 2,
                                    (len(str(messages)) + len(reply)) // 2)

        # 投毒校验
        if reply:
            valid, _ = validate_reply(reply)
            if not valid:
                reply = None

        # 记录 API
        record_api_call(success=True)

        # 2. 写缓存
        if reply and len(reply) > 20:
            from cache_layer import set_ds_cache
            set_ds_cache(openid, message, reply)

        # 3. 情绪+决策引擎
        try:
            from emotion_monitor import record_emotion
            from push_decision import decide_interaction
            record_emotion(openid, reply or message)
            profile['_pending_review'] = True
            decide_interaction(openid, 'score_update', {'total_score': 0}, profile)
        except Exception:
            pass

        elapsed = (time.time() - t0)
        _log.info('[AsyncPipeline] Deep analysis complete for %s: %.1fs (reply=%d chars)',
                  openid[:8], elapsed, len(reply or ''))

        # 存到缓冲区
        with _DEEP_LOCK:
            _DEEP_BUFFER[openid] = {
                'deep_reply': reply,
                'reply': reply,
                'ts': time.time(),
                'consumed': False,
                'elapsed': elapsed,
            }

    except Exception as e:
        _log.warning('[AsyncPipeline] Deep analysis failed for %s: %s', openid[:8], e)


def schedule_deep_analysis(openid, message, history, profile):
    """调度后台深度分析（非阻塞）"""
    t = threading.Thread(
        target=_run_deep_analysis,
        args=(openid, message, history, profile),
        daemon=True,
        name='deep-%s' % openid[:8],
    )
    t.start()
    _log.info('[AsyncPipeline] Scheduled deep analysis for %s', openid[:8])
    return t


def _consume_deep_result(openid):
    """获取并消费用户的深度分析结果"""
    with _DEEP_LOCK:
        entry = _DEEP_BUFFER.pop(openid, None)
    if entry:
        entry['consumed'] = True
        # 检查是否过期
        if time.time() - entry['ts'] > _DEEP_BUFFER_TTL:
            _log.info('[AsyncPipeline] Deep result for %s expired (%.1fs old)',
                      openid[:8], time.time() - entry['ts'])
            return None
        return entry
    return None


# ===== 集成接口 =====

def process_chat(openid, message, history, profile):
    """处理聊天请求：快速回复 + 后台深度分析

    替代 dp_router.handle_chat 中的完整链路。
    主线程只做快速本地分析返回，后台线程调 DeepSeek。

    Returns:
        dict: 给前端的回复
    """
    # 1. 快速本地分析
    fast = fast_analysis(openid, message, history, profile)

    # 2. 调度后台深度分析（如果有需要）
    if not fast.get('has_deep_result'):
        # 检查缓存层有没有
        try:
            from cache_layer import get_ds_cache
            cached = get_ds_cache(openid, message)
            if not cached:
                schedule_deep_analysis(openid, message, history, profile)
        except Exception:
            schedule_deep_analysis(openid, message, history, profile)

    return {
        'reply': fast['reply'],
        'score': fast['score'],
        'quality': fast['quality'],
        'debate': fast['debate'],
        'expert_detail': fast.get('expert_detail', {}),
        'local_only': fast['local_only'],
        'elapsed_ms': fast['elapsed_ms'],
        'async_pipeline': True,
    }


def reset():
    """重置缓冲区（用于测试）"""
    global _DEEP_BUFFER
    with _DEEP_LOCK:
        _DEEP_BUFFER = {}


# ===== 自测 =====
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    # 模拟用户
    t0 = time.time()
    result = fast_analysis('test_pipe', '昨晚睡得还行', [], {})
    elapsed = (time.time() - t0) * 1000
    print('Fast analysis: %.1fms' % elapsed)
    print('  reply: %s...' % result['reply'][:50])
    print('  score: %s' % result['score'])
    print('  has_deep: %s' % result['has_deep_result'])

    # 调度后台
    t = schedule_deep_analysis('test_pipe', '昨晚睡得还行', [], {})
    t.join(timeout=15)
    if t.is_alive():
        print('  Deep analysis still running')
    else:
        print('  Deep analysis completed')

    # 消费结果
    entry = _consume_deep_result('test_pipe')
    print('  Consumed: %s' % ('reply=%d chars' % len(entry['deep_reply']) if entry and entry.get('deep_reply') else 'None'))

    print('OK')
