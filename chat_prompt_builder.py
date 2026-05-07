#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chat_prompt_builder.py — AISleepGen 聊天提示词构建器

职责：从 dp_router 中分离所有 prompt 构建逻辑。
核心改变 v2.3：在 prompt 底部增加 "=== 数据仪表盘 ===" 块，
将趋势、评分、RL闭环洞察、干预提示等结构化数据统一用键值对格式呈现，
减少 AI 从自然语言中"猜"结构化信息的认知负担。
"""

import json
from datetime import datetime


def build_system_content(
    correction_note='',
    score_calibration_hint='',
    today_str='',
    history_context='',
    wm_context='',
    evidence_context='',
    scene_context='',
    pending_review_prompt='',
    intervention_mode=False,
    intervention_prompt_extra='',
    has_quantitative_now=False,
    tone_adjust_inject='',
    recommendation_insights='',
    persona_config=None,
    emotion_prefix='',
    intervention_hint='',
    body_context='',
):
    """构建 system_content 提示词

    v2.3 新增字段: persona_config, emotion_prefix, intervention_hint
    """
    from persona_profiles import PERSONAS, DEFAULT_PERSONA
    if persona_config is None:
        persona_config = PERSONAS[DEFAULT_PERSONA]

    persona_name = persona_config.get('name', '眠小兔')
    persona_style = persona_config.get('style_instruction', '')
    persona_analysis = persona_config.get('analysis_style', '')
    persona_suggest = persona_config.get('suggest_style', '')
    persona_tagline = persona_config.get('tagline', '')

    # ===== 下半段：结构化仪表盘 =====
    dashboard_parts = []

    if wm_context and 'score' in str(wm_context):
        try:
            wm_data = json.loads(wm_context) if isinstance(wm_context, str) else wm_context
            if wm_data.get('score'):
                dashboard_parts.append(f'score={wm_data["score"]}')
            if wm_data.get('quality'):
                dashboard_parts.append(f'quality={wm_data["quality"]}')
        except (json.JSONDecodeError, TypeError):
            pass

    if score_calibration_hint:
        dashboard_parts.append(f'calibration={score_calibration_hint}')

    if recommendation_insights and '建议效果追踪' in recommendation_insights:
        for l in recommendation_insights.strip().split('\n'):
            ll = l.strip()
            if ll.startswith('  \u2705') or ll.startswith('  \u274c') or ll.startswith('  \u2795'):
                dashboard_parts.append(ll)
            elif '策略参考' in ll:
                dashboard_parts.append(ll)

    if intervention_hint:
        dashboard_parts.append(f'intervention={intervention_hint}')

    if scene_context and scene_context != '{"scene": "general"}':
        try:
            sc = json.loads(scene_context) if isinstance(scene_context, str) else scene_context
            if sc.get('alerts'):
                for a in sc['alerts'].split('\n'):
                    a = a.strip()
                    if a:
                        dashboard_parts.append(a)
        except (json.JSONDecodeError, TypeError):
            pass

    dashboard_section = ''
    if dashboard_parts:
        dashboard_section = '\n\n=== \u6570\u636e\u4eea\u8868\u76d8 ===\n' + '\n'.join(dashboard_parts)

    system_content = f"""\u4f60\u662f{persona_name}\uff0c{persona_tagline}

【人设风格】
{persona_style}

{persona_analysis}

{persona_suggest}

{emotion_prefix}

【推理约束规则 - 必须遵守】
规则1: 只有当用户当前消息中出现了具体的睡眠数据时，才用评分模板展示当前评分。
规则2: 当前消息没有数据 -> 不展示评分。历史评分可引用回顾，但不作为当前评分。
规则3: 用户纠正时以最新说法为准。{correction_note}

【评分校准 - 用户个性化调校】
{score_calibration_hint}
如果有校准记录，请参考用户的感受倾向调整当前评分的评价语气。
如果用户曾多次反馈评分偏高，不要简单地"把分打低"，而是在评价时更谨慎、多从用户自身感受出发。
如果没有校准记录（为空），不要编造。

{tone_adjust_inject}

【数据可信度规则 - 必须遵守】
规则A: 根据用户提供的数据点数量决定推理深度：
  - 数据不足(<=2个字段): 只展示1-2个有数据支撑的维度
  - 数据一般(3-4个字段): 可展示有数据支撑的维度，标注估算项
  - 数据充分(>=5个字段): 可展示全部维度，标注估算项
规则B: 每条结论标注可信度: "可信度高" / "基于估算" / "推测"
规则C: 不知道就说不知道，不要编造。
规则D: 评分展示要克制。不要让人感觉"随便说两句就出了7个评分"。

当前日期是 {today_str}。

回复结构：
1. 共情（一句足够）
2. 基于数据做分析
3. 明确标注哪些是确定结论、哪些是推测
4. 2-3条具体可执行的建议（参照仪表盘中的数据）
5. 就医提示：只适用连续失眠超3周或伴严重身体不适

格式规范：
- 评分区用"📊 7维评估"开头，每个维度一行
- 不用Markdown符号做粗体，纯Unicode
- 建议用数字列表 1. 2. 3.
- 段落之间空行
- 注意时间线：今天是 {today_str}

纠正处理：
- 用户指出你记错了 -> 立即承认并更正
- 纠正比历史记录更重要

{history_context}

{dashboard_section}"""

    # ===== 具身上下文注入（SCAN启示：身体状态作为认知背景） =====
    if body_context:
        system_content += f'\n\n【身体状态感知】\n{body_context}\n'

    # ===== 干预模式覆盖 =====
    if intervention_mode and intervention_prompt_extra:
        review_section = f"\n{pending_review_prompt}\n" if pending_review_prompt else ""
        system_content = f"\u4f60\u662f\u7720\u5c0f\u5154\uff0c\u4e00\u540d\u4e13\u6ce8\u4e8e\u51cf\u538b\u548c\u7761\u7720\u5065\u5eb7\u7684AI\u52a9\u624b\u3002\n\n\u4f60\u7684\u89d2\u8272\u4e0d\u662f\u5206\u6790\u6216\u8bc4\u5206\uff0c\u800c\u662f\u966a\u4f34\u7528\u6237\u5b8c\u6210\u4e00\u6b21\u5373\u65f6\u7684\u51cf\u538b\u5e72\u9884\u3002\n\n{intervention_prompt_extra}{review_section}\n\n\u5f53\u524d\u65e5\u671f\u662f {today_str}\u3002\u5bf9\u8bdd\u8bed\u8a00\u81ea\u7136\u6e29\u6696\uff0c\u4e0d\u505a\u4f5c\u3002\n"
    elif pending_review_prompt and not intervention_mode:
        system_content += f"\n\n{pending_review_prompt}\n"

    # ===== 数据不足时追加引导规则 =====
    if not intervention_mode and not dashboard_section:
        system_content += """

【数据不足时的互动规则】
用户描述睡眠问题但缺少关键数据时，不要急着给建议：

第一轮：先共情，然后问1个最关键的跟进问题
- "半夜醒来" -> 问：是每晚这样还是偶尔？醒来后多久能再睡着？
- "睡不着" -> 问：躺床上多久能睡着？
- "睡眠浅" -> 问：几点睡、几点起？
- "压力大" -> 问：什么时间段压力最大？

第二轮：根据回答追问第2个关键问题

第三轮：有2-3个数据后才能做初步分析。

数据不足时不要多次道歉或说"数据不足"。自然过渡引导即可。
"""

    return system_content


# ==================== POMDP 信念上下文注入 ====================

def build_pomdp_context(openid):
    """从POMDP引擎构建信念上下文文本，注入LLM prompt

    让LLM知道系统对用户睡眠状态的"信念"——
    不仅仅是"历史记录"，而是POMDP概率分布的直觉总结。

    如果POMDP引擎不可用，返回空字符串。

    v3.19: 在长期POMDP信念后追加短期记忆信息
    v3.20: 追加行为预测信息
    """
    try:
        from pomdp_learner import get_engine
        engine = get_engine()
        belief = engine.get_belief(openid)
        score = belief.get('expected_score', 0)
        entropy = belief.get('normalized_entropy', 1.0)

        parts = []
        has_pomdp = score != 0 and entropy < 0.99

        if has_pomdp:
            parts.append(f'POMDP对{openid[:8]}的信念:')
            parts.append(f'  - 评分估计: {score:.0f}分')
            parts.append(f'  - 判断确定度: {("高" if entropy < 0.3 else "中" if entropy < 0.7 else "低")}({entropy:.2f})')

            # 提取趋势方向（最近几次观测）
            stats = engine.get_learner_stats(openid)
            if stats.get('total_obs', 0) > 2:
                if entropy > 0.7:
                    parts.append('  - 系统判断: 用户数据不足或矛盾，需要更多信息')
                elif entropy < 0.3:
                    parts.append('  - 系统判断: 对用户状态较确信')
                else:
                    parts.append('  - 系统判断: 对用户状态有初步把握')

        # v3.19: 追加短期记忆信息
        try:
            short_term = engine._get_short_term_context(openid)
            if short_term:
                parts.append(f'  - {short_term}')
        except Exception:
            pass

        # v3.20: 追加行为预测信息
        try:
            if engine.behavior_predictor is not None:
                pred_ctx = engine.behavior_predictor.format_prediction_context(openid)
                if pred_ctx:
                    parts.append(f'  - {pred_ctx}')
        except Exception:
            pass

        # v3.21: 追加时序深度描述
        try:
            from working_memory import get_working_memory as _gwm3
            _wm3 = _gwm3()
            if _wm3 is not None:
                state = _wm3.state_context(openid)
                sig = _wm3.temporal_signature(openid)
                if sig.get('velocity', 0) != 0 or sig.get('volatility', 0) > 0:
                    parts.append(
                        f'  - [时序: 状态={state}, '
                        f'速度={sig["velocity"]}分/天, '
                        f'加速度={sig["acceleration"]}, '
                        f'波动={sig["volatility"]}]'
                    )
        except Exception:
            pass

        if not parts:
            ctx = ''
        else:
            ctx = '\n'.join(parts)

        # v5.0: 独立注入RL策略信息（不受POMDP有无数据影响）
        rl_text = ''
        try:
            from online_rl import get_online_rl
            rl = get_online_rl()
            summary = rl.get_policy_summary(openid)
            if summary.get('total_updates', 0) > 0:
                best = summary.get('best_action', 'skip')
                best_q = summary.get('best_q', 0)
                action_stats = summary.get('action_stats', {})
                sorted_acts = sorted(action_stats.items(),
                                     key=lambda x: x[1].get('avg_reward', 0),
                                     reverse=True)
                second = sorted_acts[1][0] if len(sorted_acts) > 1 else 'skip'
                second_q = sorted_acts[1][1].get('avg_reward', 0) if len(sorted_acts) > 1 else 0
                eps = summary.get('epsilon', 0.2)
                rl_text = (
                    f'[RL策略: 当前最优={best}(Q={best_q:.2f}), '
                    f'次优={second}(Q={second_q:.2f}), '
                    f'探索率={eps:.2f}]'
                )
        except Exception:
            pass

        # v3.21: 追加认知信念
        try:
            from cognitive_belief import profile_summary as _cog_summary
            _cog_text = _cog_summary(openid)
            if _cog_text:
                parts.append(f'  - {_cog_text}')
        except:
            pass

        if not ctx and not rl_text:
            return ''

        return f'\n\n【内部信念状态】\n{ctx}\n{rl_text}\n' if rl_text else f'\n\n【内部信念状态】\n{ctx}\n'
    except Exception:
        return ''


def build_messages(system_content, history, user_message):
    """构建 messages 列表"""
    messages = [{'role': 'system', 'content': system_content}]
    for msg in history:
        messages.append(msg)
    messages.append({'role': 'user', 'content': user_message})
    return messages


# ==================== 睡眠故事注入 (v6.3.0) ====================

def build_narrative_context(openid, context=None):
    """生成睡眠故事上下文文本，供LLM prompt注入

    在pomdp_context后追加 [睡眠故事: ...] 格式。
    故事由narrative_engine生成，LLM自行决定如何使用。
    不同场景输出不同长度：
      - chat: 简短版
      - analyze: 完整4段

    Args:
        openid: 用户ID
        context: dict, 可选mode ('chat'/'analyze')

    Returns:
        str: 格式化的故事上下文文本
    """
    try:
        from narrative_engine import get_narrative_engine
        ne = get_narrative_engine()
        mode = 'chat' if (context and context.get('mode') == 'chat') else 'analyze'
        result = ne.generate_story(openid, {'mode': mode})
        story = result.get('story', '')
        if story and result.get('has_data'):
            # 用方括号包裹注入LLM prompt
            return f'\n[睡眠故事: {story}]\n'
    except ImportError:
        pass
    except Exception:
        pass
    return ''

# ==================== 决策解释注入 (v6.4.0) ====================

def build_decision_context(openid, decision_result=None):
    """生成决策解释上下文文本，供LLM prompt注入

    Args:
        openid: 用户ID
        decision_result: dict, 可选最近的决策结果

    Returns:
        str: 格式化的决策解释文本
    """
    try:
        from decision_explainer import get_decision_explainer
        de = get_decision_explainer()
        if decision_result:
            exp = de.explain(openid, decision_result)
            summary = exp.get('summary', '')
            if summary:
                return f'\n[决策解释: {summary}]\n'
        else:
            exp = de.explain(openid, {'action': 'skip', 'reason': 'analyze', 'confidence': 0.5})
            summary = exp.get('summary', '')
            if summary:
                return f'\n[决策解释: {summary}]\n'
    except ImportError:
        pass
    except Exception:
        pass
    return ''


def load_calibration():
    """加载校准参数（保留兼容）"""
    path = __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'data', 'calibration.json')
    try:
        if __import__('os').path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return __import__('json').load(f)
    except Exception:
        pass
    return {}
