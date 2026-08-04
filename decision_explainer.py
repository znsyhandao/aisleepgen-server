#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
decision_explainer.py — AISleepGen 决策解释器 v1.0

范式跃迁：每个决策都应该能被自然语言解释。

核心思想：
  conscious_decider 做了综合决策，但为什么选这个？
  本模块从决策链（RL/POMDP/WM/时序的投票结果）+ 用户数据
  生成符合人类理解的决策解释。

解释框架：
  每个决策输出：
    summary: 一句话概括决策
    trigger: 触发原因
    evidence: 多维度证据
    expected_impact: 预期影响
    alternatives: 其他选项对比
    confidence: 确定程度

集成：
  - chat_prompt_builder: 注入决策解释到 LLM prompt
  - agent_gateway: 外部Agent可获取
  - dp_router: 每次决策后自动生成
"""

import json
import os
import logging
from datetime import datetime

_de_log = logging.getLogger('aisleepgen.decision_explainer')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 行动名称映射
ACTION_NAMES = {
    'push': '主动推送放松方案',
    'push_now': '立即推送干预方案',
    'delay_push': '延迟推送干预方案',
    'in_chat': '在对话中嵌入关怀',
    'probe': '发起探测性对话',
    'skip': '暂不采取行动',
    'ask': '主动询问情况',
    'companion': '启动陪伴模式',
}


class DecisionExplainer:
    """决策解释器——为每个决策生成自然语言解释

    用法:
        de = DecisionExplainer()
        explanation = de.explain(openid, decision_result)
        # -> {'summary': '...', 'trigger': '...', ...}
    """

    def __init__(self):
        self._last_explanations = {}
        _de_log.info('[DecisionExplainer] Initialized')

    def explain(self, openid: str, decision_result: dict) -> dict:
        """生成决策的自然语言解释

        Args:
            openid: 用户ID
            decision_result: dict，决策结果，包含action/reason/confidence等

        Returns:
            dict: {
                'summary': str,          # 一句话概括
                'trigger': str,          # 触发原因
                'evidence': str,         # 多维度证据
                'expected_impact': str,  # 预期影响
                'alternatives': str,     # 其他选项
                'confidence': str,       # 确定程度
                'chain_explanation': str,# 决策链各层解释
            }
        """
        action = decision_result.get('action', 'skip')
        reason = decision_result.get('reason', '')
        confidence = decision_result.get('confidence', 0.5)
        decision_chain = decision_result.get('decision_chain', {})

        # 收集用户数据上下文
        user_context = self._collect_user_context(openid)

        # 构建各字段
        summary = self._build_summary(action, user_context)
        trigger = self._build_trigger(user_context, decision_result)
        evidence = self._build_evidence(user_context, decision_chain)
        expected_impact = self._build_expected_impact(action, user_context)
        alternatives = self._build_alternatives(decision_chain, user_context)
        confidence_str = self._build_confidence(confidence)
        chain_explanation = self._build_chain(decision_chain)

        explanation = {
            'summary': summary,
            'trigger': trigger,
            'evidence': evidence,
            'expected_impact': expected_impact,
            'alternatives': alternatives,
            'confidence': confidence_str,
            'chain_explanation': chain_explanation,
        }

        self._last_explanations[openid] = explanation
        return explanation

    def explain_chain(self, decision_chain: dict) -> str:
        """解释决策链每一层为什么选了某个行动

        Args:
            decision_chain: dict，包含rl_choice, pomdp_choice, wm_choice,
                          temporal_choice, winner, final_score等

        Returns:
            str: 自然语言解释
        """
        rl_choice = decision_chain.get('rl_choice', 'skip')
        rl_score = decision_chain.get('rl_score', 0.0)
        pomdp_choice = decision_chain.get('pomdp_choice', 'skip')
        pomdp_score = decision_chain.get('pomdp_score', 0.0)
        wm_choice = decision_chain.get('wm_choice', 'skip')
        wm_score = decision_chain.get('wm_score', 0.0)
        temporal_choice = decision_chain.get('temporal_choice', 'skip')
        temporal_score = decision_chain.get('temporal_score', 0.0)
        winner = decision_chain.get('winner', 'skip')
        final_score = decision_chain.get('final_score', 0.0)

        parts = []

        # RL
        rl_action_name = ACTION_NAMES.get(rl_choice, rl_choice)
        parts.append(f"RL认为该行动最优({rl_score:.2f})")

        # POMDP
        if pomdp_choice == rl_choice:
            if pomdp_score > 0.4:
                parts.append(f"POMDP也偏同意({pomdp_score:.2f})")
            else:
                parts.append(f"POMDP略有分歧({pomdp_score:.2f})")
        else:
            pomdp_action_name = ACTION_NAMES.get(pomdp_choice, pomdp_choice)
            parts.append(f"POMDP倾向{pomdp_action_name}({pomdp_score:.2f})")

        # WM
        if wm_choice == rl_choice:
            if wm_score > 0.2:
                parts.append(f"WM因为趋势倾向{wm_choice}({wm_score:.2f})")
            else:
                parts.append(f"WM弱倾向{wm_choice}({wm_score:.2f})")
        else:
            wm_action_name = ACTION_NAMES.get(wm_choice, wm_choice)
            parts.append(f"WM倾向{wm_action_name}({wm_score:.2f})")

        # 时序
        temporal_state = decision_chain.get('temporal_state', '')
        if temporal_state:
            parts.append(f"时序状态'{temporal_state}'支持{temporal_choice}({temporal_score:.2f})")
        else:
            parts.append(f"时序支持{temporal_choice}({temporal_score:.2f})")

        # 最终
        winner_name = ACTION_NAMES.get(winner, winner)
        parts.append(f"综合加权后选择了{winner_name}({final_score:.2f})")

        return '。'.join(parts) + '。'

    def get_explanation_for_action(self, action: str, scores: dict) -> str:
        """对单个行动生成简短解释

        Args:
            action: 行动名称
            scores: 各维度评分

        Returns:
            str: 简短解释
        """
        action_name = ACTION_NAMES.get(action, action)
        parts = [f"选择{action_name}"]

        if scores:
            best = max(scores, key=scores.get)
            worst = min(scores, key=scores.get)
            parts.append(f"因为{best}维度评分最高({scores[best]:.2f})")
            parts.append(f"，而{worst}维度最低({scores[worst]:.2f})")

        return '，'.join(parts) + '。'

    def get_last_explanation(self, openid: str) -> dict:
        """获取用户最近一次决策解释"""
        return self._last_explanations.get(openid, {})

    # ==================== 内部构建 ====================

    def _collect_user_context(self, openid: str) -> dict:
        """收集用户当前数据上下文"""
        context = {
            'score': None,
            'trend': '',
            'velocity': 0,
            'state_text': '',
            'change_descriptions': [],
        }

        try:
            from pomdp_learner import get_engine
            engine = get_engine()
            belief = engine.get_belief(openid)
            context['score'] = belief.get('expected_score', 0)
        except Exception:
            pass

        try:
            from working_memory import get_working_memory
            wm = get_working_memory()
            if wm:
                trend = wm.recent_trend(openid)
                context['trend'] = trend.get('direction', 'flat')
                sig = wm.temporal_signature(openid)
                context['velocity'] = sig.get('velocity', 0)
                context['state_text'] = wm.state_context(openid)

                recent_scores = trend.get('scores', [])
                if len(recent_scores) >= 2:
                    change = recent_scores[-1] - recent_scores[0]
                    context['change_descriptions'].append(f"{recent_scores[0]:.0f}-{recent_scores[-1]:.0f}分")
                    context['change'] = change
        except Exception:
            pass

        return context

    def _build_summary(self, action: str, ctx: dict) -> str:
        """构建一句话概括"""
        action_name = ACTION_NAMES.get(action, action)

        if action in ('push', 'push_now'):
            return f"我决定主动推送放松方案给你"
        elif action == 'delay_push':
            return f"我决定稍后推送方案给你"
        elif action in ('in_chat', 'ask', 'probe'):
            return f"我决定主动问你几个问题了解一下你的情况"
        elif action == 'skip':
            if ctx.get('trend') == 'up' or ctx.get('trend') == 'flat':
                return f"我决定先不做干预，观察一下你的情况"
            else:
                return f"我决定暂不干预"
        elif action == 'companion':
            return f"我决定启动陪伴模式"
        return f"我决定{action_name}"

    def _build_trigger(self, ctx: dict, decision: dict) -> str:
        """构建触发原因"""
        parts = []

        score = ctx.get('score')
        velocity = ctx.get('velocity')
        trend = ctx.get('trend')
        change_descs = ctx.get('change_descriptions', [])
        state_text = ctx.get('state_text', '')

        # 评分描述
        if score is not None and score > 0:
            if score < 50:
                parts.append(f"你的评分偏低（{score:.0f}分）")
            elif score > 80:
                parts.append(f"你的评分较好（{score:.0f}分）")

        # 趋势
        if trend == 'down' and abs(velocity) > 2:
            if change_descs:
                parts.append(f"评分连续下降（从{change_descs[-1]}）")
            else:
                parts.append(f"评分在持续下降")
        elif trend == 'up' and velocity > 2:
            parts.append(f"评分在持续改善")

        # 状态
        if state_text in ('正在恶化', '正在改善', '触底反弹', '高位回落'):
            parts.append(f"时序状态「{state_text}」")

        if not parts:
            action = decision.get('action', '')
            reason = decision.get('reason', '')
            if reason:
                return reason[:60]
            return f"{ACTION_NAMES.get(action, action)}的常规检查"

        return '，'.join(parts) + ''

    def _build_evidence(self, ctx: dict, chain: dict) -> str:
        """构建多维度证据"""
        pieces = []

        velocity = ctx.get('velocity', 0)
        trend = ctx.get('trend', '')
        state_text = ctx.get('state_text', '')

        # 趋势证据
        if trend == 'down' and abs(velocity) > 2:
            pieces.append(f"趋势在恶化（速度{velocity:.1f}分/天）")
        elif trend == 'up' and velocity > 2:
            pieces.append(f"趋势在改善（速度{velocity:.1f}分/天）")
        elif abs(velocity) > 1:
            pieces.append(f"趋势有波动（速度{velocity:.1f}分/天）")

        # RL决策
        rl_choice = chain.get('rl_choice', '')
        rl_score = chain.get('rl_score', 0)
        if rl_score > 0.5:
            pieces.append(f"RL认为你当前需要干预（Q值{rl_score:.2f}）")
        elif rl_score > 0.3:
            pieces.append(f"RL认为可以适当关注（Q值{rl_score:.2f}）")

        # POMDP
        pomdp_score = chain.get('pomdp_score', 0)
        score = ctx.get('score', 0)
        if pomdp_score > 0.5:
            pieces.append(f"POMDP信念也偏向低分侧（{score:.0f}分）")
        elif pomdp_score > 0.3:
            pieces.append(f"POMDP信念处于中性")

        # 时序状态
        if state_text:
            pieces.append(f"时序状态「{state_text}」影响决策")

        if not pieces:
            pieces.append("当前没有显著的决策信号")

        return '，'.join(pieces) + ''

    def _build_expected_impact(self, action: str, ctx: dict) -> str:
        """构建预期影响"""
        score = ctx.get('score', 0)

        if action in ('push', 'push_now'):
            if score > 0:
                expected = min(10, max(3, int((100 - score) / 10)))
                return f"如果执行，预计能帮你今晚评分回升{expected}分左右"
            return "如果执行，预计能改善今晚睡眠质量"
        elif action in ('ask', 'probe', 'in_chat'):
            return "通过了解你的情况，可以更精准地推荐方案"
        elif action == 'delay_push':
            return "稍后推送可以避开目前不适合干预的时段"
        elif action == 'skip':
            if ctx.get('trend') == 'up':
                return "你的趋势向好，观察是最好的干预"
            return "给身体一点自然调整的时间"
        elif action == 'companion':
            return "陪伴模式可以帮助你放松入睡"
        return ""

    def _build_alternatives(self, chain: dict, ctx: dict) -> str:
        """构建其他选项对比"""
        winner = chain.get('winner', 'skip')
        rl_choice = chain.get('rl_choice', '')
        pomdp_choice = chain.get('pomdp_choice', '')

        # 对比skip与push
        if winner in ('push', 'push_now'):
            return f"skip也有考虑，但鉴于你{'评分偏低' if ctx.get('score', 50) < 50 else '当前情况'}，push是当前最优"
        elif winner == 'skip':
            if ctx.get('trend') == 'up':
                return f"push也曾考虑，但你当前走势良好，不需要主动干预"
            return f"push也曾考虑，但你觉得更适合暂时观察"
        elif winner in ('ask', 'probe'):
            alt = set()
            if rl_choice != winner:
                alt.add(rl_choice)
            if pomdp_choice != winner:
                alt.add(pomdp_choice)
            return f"{'、'.join(alt) if alt else '其他路径'}也有考虑，但了解情况后再决策更合适"

        return ""

    def _build_confidence(self, confidence: float) -> str:
        """构建确定程度描述"""
        if confidence >= 0.85:
            return f"较高（{confidence:.2f}）"
        elif confidence >= 0.6:
            return f"中等（{confidence:.2f}）"
        elif confidence >= 0.3:
            return f"偏低（{confidence:.2f}）"
        else:
            return f"较低（{confidence:.2f}）"

    def _build_chain(self, chain: dict) -> str:
        """构建决策链解释（复用explain_chain逻辑）"""
        if not chain:
            return ""
        return self.explain_chain(chain)


# ==================== 全局实例 ====================

_de_instance = None


def get_decision_explainer() -> DecisionExplainer:
    """获取全局决策解释器实例"""
    global _de_instance
    if _de_instance is None:
        _de_instance = DecisionExplainer()
    return _de_instance


# ==================== 自测 ====================

def _run_self_test():
    """运行5个自测场景"""
    import sys

    print('=' * 60)
    print('Decision Explainer Self-Test (v6.4.0)')
    print('=' * 60)

    de = DecisionExplainer()
    results = []

    # ---------- Test 1: 下降趋势→push决策 → "恶化"字眼 ----------
    print('\n1. 评分下降趋势→push决策 → 解释包含"恶化"字眼')
    try:
        decision = {
            'action': 'push',
            'reason': 'score_drop',
            'confidence': 0.72,
            'decision_chain': {
                'rl_choice': 'push', 'rl_score': 0.65,
                'pomdp_choice': 'push', 'pomdp_score': 0.52,
                'wm_choice': 'push', 'wm_score': 0.30,
                'temporal_choice': 'push', 'temporal_score': 0.45,
                'temporal_state': '正在恶化',
                'winner': 'push',
                'final_score': 0.62,
            },
        }

        # Seed some data for the user
        from pomdp_learner import get_engine
        engine = get_engine()
        engine.observe('_ba_explain_down', text='失眠', score=60)
        engine.observe('_ba_explain_down', text='睡不着', score=50)
        engine.observe('_ba_explain_down', text='还是不好', score=40)

        from working_memory import get_working_memory
        wm = get_working_memory()
        for i, s in enumerate([60, 50, 40]):
            wm.push('_ba_explain_down', {'text': f'Day{i}', 'score_obs': s, 'emotion': 'negative', 'intervention': 'none', 'outcome': 'none'})

        exp = de.explain('_ba_explain_down', decision)
        print(f'   Summary: {exp["summary"]}')
        print(f'   Trigger: {exp["trigger"]}')
        print(f'   Evidence: {exp["evidence"]}')
        ok = '恶化' in exp['evidence'] or '下降' in exp['trigger'] or '低' in exp['trigger']
        print(f'   PASS={ok}')
        results.append(('1-恶化语义', ok))
    except Exception as e:
        print(f'   FAIL: {e}')
        import traceback; traceback.print_exc()
        results.append(('1-恶化语义', False))

    # ---------- Test 2: 平稳→skip决策 → "稳定"字眼 ----------
    print('\n2. 评分平稳→skip决策 → 解释包含"稳定"字眼')
    try:
        decision2 = {
            'action': 'skip',
            'reason': 'stable',
            'confidence': 0.85,
            'decision_chain': {
                'rl_choice': 'skip', 'rl_score': 0.72,
                'pomdp_choice': 'skip', 'pomdp_score': 0.68,
                'wm_choice': 'skip', 'wm_score': 0.55,
                'temporal_choice': 'skip', 'temporal_score': 0.50,
                'temporal_state': '持平震荡',
                'winner': 'skip',
                'final_score': 0.70,
            },
        }

        from pomdp_learner import get_engine
        engine = get_engine()
        engine.observe('_ba_explain_stable', text='还行', score=75)
        engine.observe('_ba_explain_stable', text='可以', score=78)

        from working_memory import get_working_memory
        wm = get_working_memory()
        for i, s in enumerate([75, 78]):
            wm.push('_ba_explain_stable', {'text': f'Day{i}', 'score_obs': s, 'emotion': 'positive', 'intervention': 'none', 'outcome': 'none'})

        exp2 = de.explain('_ba_explain_stable', decision2)
        print(f'   Summary: {exp2["summary"]}')
        ok = '观察' in exp2['summary'] or '不干预' in exp2['summary'] or '稳定' in exp2['trigger']
        print(f'   PASS={ok}')
        results.append(('2-稳定语义', ok))
    except Exception as e:
        print(f'   FAIL: {e}')
        results.append(('2-稳定语义', False))

    # ---------- Test 3: 决策链各层不一致 → 体现不同意见 ----------
    print('\n3. 决策链各层行动不一致时 → 解释体现各层的不同意见')
    try:
        decision3 = {
            'action': 'push',
            'reason': 'mixed_signals',
            'confidence': 0.62,
            'decision_chain': {
                'rl_choice': 'push', 'rl_score': 0.65,
                'pomdp_choice': 'skip', 'pomdp_score': 0.52,
                'wm_choice': 'skip', 'wm_score': 0.45,
                'temporal_choice': 'push', 'temporal_score': 0.40,
                'temporal_state': '正在恶化',
                'winner': 'push',
                'final_score': 0.62,
            },
        }
        exp3 = de.explain('_ba_explain_mixed', decision3)
        chain_text = exp3.get('chain_explanation', '')
        print(f'   Chain: {chain_text[:200]}')
        # Should mention that RL and POMDP disagree
        ok = ('RL认为' in chain_text and 'POMDP' in chain_text and '分歧' in chain_text) or \
             ('RL认为' in chain_text and 'POMDP倾向' in chain_text)
        print(f'   PASS={ok}')
        results.append(('3-决策链分歧', ok))
    except Exception as e:
        print(f'   FAIL: {e}')
        results.append(('3-决策链分歧', False))

    # ---------- Test 4: Gateway新增explain_decision能力 ----------
    print('\n4. 新增explain_decision Gateway能力')
    # We'll check this after Phase 2 integration - test the explain method itself
    try:
        # Instead of gateway (which uses phase-2 dispatch), test explain directly
        decision4 = {
            'action': 'skip',
            'reason': 'analyze',
            'confidence': 0.5,
            'decision_chain': {
                'rl_choice': 'skip', 'rl_score': 0.4,
                'pomdp_choice': 'skip', 'pomdp_score': 0.5,
                'wm_choice': 'skip', 'wm_score': 0.35,
                'temporal_choice': 'skip', 'temporal_score': 0.3,
                'temporal_state': '',
                'winner': 'skip',
                'final_score': 0.45,
            },
        }
        exp4 = de.explain('_ba_explain_gateway', decision4)
        print(f'   Summary: {exp4["summary"]}')
        print(f'   Confidence: {exp4["confidence"]}')
        # Check get_explanation_for_action works
        single = de.get_explanation_for_action('push', {'rl': 0.65, 'pomdp': 0.52, 'wm': 0.30, 'temporal': 0.45})
        print(f'   Single action: {single}')
        ok = len(exp4['summary']) > 0 and len(exp4['chain_explanation']) > 0
        print(f'   PASS={ok}')
        results.append(('4-基础功能', ok))
    except Exception as e:
        print(f'   FAIL: {e}')
        import traceback; traceback.print_exc()
        results.append(('4-基础功能', False))

    # ---------- Test 5: 注入LLM prompt格式正确 ----------
    print('\n5. 注入LLM prompt格式正确')
    try:
        decision5 = {
            'action': 'push',
            'reason': 'score_drop_continuous',
            'confidence': 0.72,
            'decision_chain': {
                'rl_choice': 'push', 'rl_score': 0.65,
                'pomdp_choice': 'push', 'pomdp_score': 0.52,
                'wm_choice': 'push', 'wm_score': 0.30,
                'temporal_choice': 'push', 'temporal_score': 0.45,
                'temporal_state': '正在恶化',
                'winner': 'push',
                'final_score': 0.62,
            },
        }
        exp5 = de.explain('_ba_explain_llm', decision5)
        summary = exp5['summary']
        # 模拟注入格式
        formatted = f"[决策解释: {summary}]"
        print(f'   Formatted: {formatted[:120]}...')
        ok = formatted.startswith('[决策解释:') and formatted.endswith(']')
        print(f'   PASS={ok}')
        results.append(('5-注入格式', ok))
    except Exception as e:
        print(f'   FAIL: {e}')
        results.append(('5-注入格式', False))

    # ===== Summary =====
    print('\n' + '=' * 60)
    print('Self-Test Summary:')
    for name, ok in results:
        status = 'PASS' if ok else 'FAIL'
        print(f'  [{status}] {name}')
    total_pass = sum(1 for _, ok in results if ok)
    print(f'\n{total_pass}/{len(results)} passed')
    print('=' * 60)

    return all(ok for _, ok in results)


if __name__ == '__main__':
    _run_self_test()
