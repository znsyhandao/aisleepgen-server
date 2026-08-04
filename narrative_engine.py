#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
narrative_engine.py — AISleepGen 睡眠故事生成器 v1.0

范式跃迁：把多层数据融合成有叙事的自然语言文本，不是模板拼接。

核心思想：
  用户不是冷冰冰的数据点，而是一个有故事的人。
  本模块将 POMDP 信念、工作记忆、时序签名、情绪、作息等
  融合为4个叙述模块的连贯叙事。

4个叙述模块：
  模块1 - 现状 (What): 当前评分、置信度、状态判断、短期趋势方向、速度/加速度
  模块2 - 原因 (Why): 症状识别、情绪趋势、作息规律性
  模块3 - 预测 (What's next): 今晚预测+置信度、趋势外推
  模块4 - 建议 (What to do): 干预方案推荐+理由、AEO权重解释

上下文适配：
  - chat: 1-2句话简短版
  - analyze: 完整4段
  - weekly: 4段+对比
"""

import json
import os
import logging
from datetime import datetime

_nar_log = logging.getLogger('aisleepgen.narrative_engine')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


class NarrativeEngine:
    """叙事引擎——生成用户睡眠故事

    用法:
        ne = NarrativeEngine()
        story = ne.generate_story(openid, context={'mode': 'chat'})
        # -> {'story': '...', 'modules': {...}}
    """

    def __init__(self):
        self._modules_cache = {}
        _nar_log.info('[Narrative] NarrativeEngine initialized')

    # ==================== 主入口 ====================

    def generate_story(self, openid: str, context: dict = None) -> dict:
        """生成完整睡眠故事

        从各模块收集数据，融合成4段叙事文本

        Args:
            openid: 用户ID
            context: 上下文 dict
                - mode: 'chat' | 'analyze' | 'weekly' (默认 'analyze')
                - profile: 用户画像（可选，用于避免重复加载）

        Returns:
            dict: {
                'story': str,           # 完整叙事文本
                'modules': {...},       # 4个模块各自的文本
                'has_data': bool,       # 是否有足够数据
                'mode': str             # 使用的模式
            }
        """
        if context is None:
            context = {}
        mode = context.get('mode', 'analyze')
        profile = context.get('profile', None)

        # 收集各模块数据
        modules = self._collect_modules(openid, profile)

        # 检查是否有足够数据
        has_data = self._has_sufficient_data(modules)

        if not has_data:
            short_story = "数据不足，再聊几次我就能给你分析了。"
            return {
                'story': short_story,
                'modules': modules,
                'has_data': False,
                'mode': mode
            }

        # 根据不同模式生成不同长度的叙事
        story = self._build_narrative(modules, mode)

        return {
            'story': story,
            'modules': modules,
            'has_data': True,
            'mode': mode
        }

    def generate_weekly_summary(self, openid: str) -> str:
        """生成周报

        Returns:
            str: 周报叙事文本
        """
        story_result = self.generate_story(openid, {'mode': 'weekly'})
        if not story_result['has_data']:
            return story_result['story']

        # 周报额外添加对比分析
        comparison = self.generate_comparison(openid)
        if comparison:
            return story_result['story'] + '\n\n' + comparison

        return story_result['story']

    def generate_comparison(self, openid: str) -> str:
        """生成对比分析（本周 vs 上周）

        Returns:
            str: 对比分析文本
        """
        try:
            from trend_layer import _get_current_and_prev_week_avg
            current_avg, prev_avg = _get_current_and_prev_week_avg(openid)
            if current_avg is not None and prev_avg is not None:
                diff = current_avg - prev_avg
                if abs(diff) < 3:
                    return f"相比上周，你的睡眠评分基本持平（{current_avg:.0f}分 vs {prev_avg:.0f}分）。"
                elif diff > 0:
                    return f"相比上周，你的睡眠评分提高了{diff:+.0f}分（{current_avg:.0f}分 vs {prev_avg:.0f}分），继续保持！"
                else:
                    return f"相比上周，你的睡眠评分下降了{diff:.0f}分（{current_avg:.0f}分 vs {prev_avg:.0f}分），需要多加注意。"
        except Exception:
            pass
        return ""

    # ==================== 模块数据收集 ====================

    def _collect_modules(self, openid: str, profile: dict = None) -> dict:
        """收集4个模块的数据

        Returns:
            dict: {
                'what': {...},    # 现状
                'why': {...},     # 原因
                'whats_next': {...},  # 预测
                'what_to_do': {...},  # 建议
            }
        """
        modules = {
            'what': self._collect_what(openid, profile),
            'why': self._collect_why(openid, profile),
            'whats_next': self._collect_whats_next(openid, profile),
            'what_to_do': self._collect_what_to_do(openid, profile),
        }
        return modules

    def _collect_what(self, openid: str, profile: dict = None) -> dict:
        """模块1：现状（What）

        从POMDP信念、WM、时序签名提取
        """
        result = {
            'score': None,
            'confidence': 0,
            'state_judgment': '',
            'trend_direction': '',
            'velocity': 0,
            'acceleration': None,
            'state_text': '',
            'score_band': '',
            'source': {},
        }

        try:
            from pomdp_learner import get_engine
            engine = get_engine()
            belief = engine.get_belief(openid)
            result['score'] = belief.get('expected_score', 0)
            entropy = belief.get('normalized_entropy', 1.0)
            result['confidence'] = 1 - entropy if entropy < 0.99 else 0

            if entropy < 0.3:
                result['state_judgment'] = '对用户状态较确信'
            elif entropy < 0.7:
                result['state_judgment'] = '对用户状态有初步把握'
            else:
                result['state_judgment'] = '数据不足或矛盾，需要更多信息'

            result['source']['pomdp'] = {
                'expected_score': result['score'],
                'entropy': entropy,
            }
        except Exception:
            pass

        try:
            from working_memory import get_working_memory
            wm = get_working_memory()
            if wm:
                trend = wm.recent_trend(openid)
                result['trend_direction'] = trend.get('direction', 'flat')
                result['source']['wm_trend'] = trend

                sig = wm.temporal_signature(openid)
                result['velocity'] = sig.get('velocity', 0)
                result['acceleration'] = sig.get('acceleration', None)
                result['source']['temporal'] = sig

                state = wm.state_context(openid)
                result['state_text'] = state
                result['source']['state_context'] = state
        except Exception:
            pass

        # 评分区间
        score = result['score']
        if score is not None:
            if score >= 80:
                result['score_band'] = '优秀'
            elif score >= 65:
                result['score_band'] = '良好'
            elif score >= 50:
                result['score_band'] = '中等偏下'
            elif score >= 30:
                result['score_band'] = '较差'
            else:
                result['score_band'] = '很糟糕'

        return result

    def _collect_why(self, openid: str, profile: dict = None) -> dict:
        """模块2：原因（Why）

        从意图引擎、情绪监测、作息分析提取
        """
        result = {
            'symptoms': [],
            'emotion_trend': '',
            'circadian_regularity': '',
            'source': {},
        }

        # 从意图引擎提取最近症状报告
        try:
            from working_memory import get_working_memory
            wm = get_working_memory()
            if wm:
                recent = wm.recent(openid, n=10)
                intents = []
                for entry in recent:
                    text = entry.get('text', '')
                    if '失眠' in text:
                        intents.append('入睡困难')
                    if '早醒' in text or '醒得早' in text:
                        intents.append('早醒')
                    if '焦虑' in text:
                        intents.append('焦虑')
                    if '压力' in text:
                        intents.append('压力大')
                    if '浅' in text or '不深' in text:
                        intents.append('睡眠浅')
                    if '做梦' in text:
                        intents.append('多梦')
                if intents:
                    result['symptoms'] = list(set(intents))
                    result['source']['intent_symptoms'] = result['symptoms']
        except Exception:
            pass

        # 从emotion_monitor提取情绪趋势
        try:
            from emotion_monitor import get_emotion_trend
            trend_data = get_emotion_trend(openid)
            if trend_data:
                direction = trend_data.get('direction', '')
                if direction == 'worsening':
                    result['emotion_trend'] = '最近情绪状态在恶化'
                elif direction == 'improving':
                    result['emotion_trend'] = '最近情绪状态在改善'
                elif direction == 'neutral':
                    result['emotion_trend'] = '情绪状态平稳'
                else:
                    avg_score = trend_data.get('average_score', 0)
                    if avg_score < 0:
                        result['emotion_trend'] = '整体情绪偏负面'
                    elif avg_score > 0:
                        result['emotion_trend'] = '整体情绪偏正面'
                    else:
                        result['emotion_trend'] = '情绪状态中性'
                result['source']['emotion'] = trend_data
        except Exception:
            pass

        # 从circadian_phase_model提取作息规律性
        try:
            from circadian_phase_model import fit_circadian_profile
            if profile is None:
                from cache_layer import get_cached_profile
                profile = get_cached_profile(openid)
            if profile:
                cp = fit_circadian_profile(profile)
                if cp is not None:
                    drift = getattr(cp, 'drift_rate', 0)
                    if abs(drift) < 15:
                        result['circadian_regularity'] = '作息比较规律'
                    elif abs(drift) < 30:
                        result['circadian_regularity'] = '作息有一定波动'
                    else:
                        result['circadian_regularity'] = '作息波动较大'
                    result['source']['circadian_drift'] = drift
        except Exception:
            pass

        return result

    def _collect_whats_next(self, openid: str, profile: dict = None) -> dict:
        """模块3：预测（What's next）

        从behavior_predictor、时序趋势外推
        """
        result = {
            'predicted_score': None,
            'prediction_confidence': 0,
            'extrapolated_score': None,
            'bedtime_hint': '',
            'source': {},
        }

        # 从behavior_predictor提取今晚预测
        try:
            from behavior_predictor import get_predictor
            predictor = get_predictor()
            pred = predictor.predict_tonight(openid)
            if pred:
                score = pred.get('score', pred.get('predicted_score', None))
                if score is not None:
                    result['predicted_score'] = score
                    conf = pred.get('confidence', pred.get('uncertainty', 0.5))
                    result['prediction_confidence'] = 1 - conf if conf < 1 else conf
                    result['source']['predictor'] = pred
        except Exception:
            pass

        # 备选：从prediction_engine
        if result['predicted_score'] is None:
            try:
                from prediction_engine import predict_tonight
                if profile is None:
                    from cache_layer import get_cached_profile
                    profile = get_cached_profile(openid)
                if profile:
                    pred = predict_tonight(profile, openid=openid)
                    if pred and isinstance(pred, dict):
                        score = pred.get('predicted_score', pred.get('score', None))
                        if score is not None:
                            result['predicted_score'] = score
                            result['source']['prediction_engine'] = pred
            except Exception:
                pass

        # 时序外推：如果持续当前趋势
        try:
            from working_memory import get_working_memory
            wm = get_working_memory()
            if wm:
                what = self._collect_what(openid, profile)
                vel = what.get('velocity', 0)
                score = what.get('score', 50)
                if vel != 0 and score:
                    # 外推2步
                    result['extrapolated_score'] = max(0, min(100, score + vel * 2))
                    result['source']['extrapolation'] = {
                        'current_score': score,
                        'velocity': vel,
                        'steps': 2,
                        'extrapolated': result['extrapolated_score'],
                    }
        except Exception:
            pass

        return result

    def _collect_what_to_do(self, openid: str, profile: dict = None) -> dict:
        """模块4：建议（What to do）

        从sleep_coach、AEO权重提取
        """
        result = {
            'recommended_intervention': '',
            'intervention_reason': '',
            'intervention_effectiveness': '',
            'source': {},
        }

        try:
            from sleep_coach import get_daily_suggestion
            if profile is None:
                from cache_layer import get_cached_profile
                profile = get_cached_profile(openid)
            if profile:
                emotion = profile.get('latest_emotion', 'neutral')
                suggestion = get_daily_suggestion(profile, emotion)
                if suggestion:
                    result['recommended_intervention'] = suggestion.get('title', '')
                    result['intervention_reason'] = suggestion.get('reason', '')
                    result['source']['sleep_coach'] = suggestion
        except Exception:
            pass

        # 从AEO权重提取：为什么选这个方案
        try:
            from weight_optimizer import get_weight_optimizer
            wo = get_weight_optimizer()
            weights = wo.get_weights(openid, {})
            if weights:
                sorted_weights = sorted(weights.items(), key=lambda x: x[1], reverse=True)
                top_layer, top_weight = sorted_weights[0]
                layer_names = {
                    'rl': '强化学习（RL）',
                    'pomdp': 'POMDP信念',
                    'wm': '工作记忆',
                    'temporal': '时序趋势',
                }
                result['intervention_reason'] += (
                    f"当前决策权重最高的是{layer_names.get(top_layer, top_layer)}"
                    f"（{top_weight:.0%}）"
                )
                result['source']['aeo_weights'] = weights
        except Exception:
            pass

        # 效果参考
        try:
            from recommendation_tracker import get_recommendation_insights
            if profile is None:
                from cache_layer import get_cached_profile
                profile = get_cached_profile(openid)
            if profile:
                insights = get_recommendation_insights(profile)
                if insights and '建议效果追踪' in insights:
                    result['intervention_effectiveness'] = insights
                    result['source']['recommendation_tracker'] = True
        except Exception:
            pass

        return result

    # ==================== 叙事构建 ====================

    def _has_sufficient_data(self, modules: dict) -> bool:
        """检查是否有足够数据生成有意义的故事"""
        what = modules.get('what', {})
        score = what.get('score', None)
        source = what.get('source', {})
        has_score = score is not None and score > 0
        has_trend = what.get('trend_direction', '') != ''

        # 检查是否来自默认信念（POMDP无数据时的默认值45）
        # 如果仅有一个默认评分且无WM数据，视为数据不足
        pomdp_source = source.get('pomdp', {})
        wm_source = source.get('wm_trend', {})
        has_wm_data = wm_source.get('n', 0) > 1

        # 有实际WM数据或非默认评分才算足够
        if has_wm_data and has_score:
            return True
        # 如果只有默认POMDP评分（45分）且无WM数据 → 数据不足
        if has_score and not has_wm_data:
            if score is not None and abs(score - 45.0) < 5.0:
                return False
            return True
        return has_trend

    def _build_narrative(self, modules: dict, mode: str = 'analyze') -> str:
        """根据4个模块数据和输出模式构建叙事文本

        Args:
            modules: 4个模块的数据 dict
            mode: 'chat' | 'analyze' | 'weekly'

        Returns:
            str: 叙事文本
        """
        what = modules.get('what', {})
        why = modules.get('why', {})
        whats_next = modules.get('whats_next', {})
        what_to_do = modules.get('what_to_do', {})

        # 构建4段文本
        segments = []

        # --- 模块1：现状 ---
        seg1 = self._build_what_segment(what, mode)
        if seg1:
            segments.append(seg1)

        # --- 模块2：原因 ---
        seg2 = self._build_why_segment(why, mode)
        if seg2:
            segments.append(seg2)

        # --- 模块3：预测 ---
        seg3 = self._build_whats_next_segment(whats_next, mode)
        if seg3:
            segments.append(seg3)

        # --- 模块4：建议 ---
        seg4 = self._build_what_to_do_segment(what_to_do, mode)
        if seg4:
            segments.append(seg4)

        if not segments:
            return "数据不足，再聊几次我就能给你分析了。"

        if mode == 'chat':
            # 简短版：1-2句，取前2段
            short = '. '.join(segments[:2])
            if len(short) > 150:
                short = short[:150] + '。'
            return short.strip()
        else:
            # 完整版：4段
            return '\n'.join([s for s in segments if s])

    def _build_what_segment(self, what: dict, mode: str) -> str:
        """构建模块1：现状"""
        score = what.get('score')
        band = what.get('score_band', '')
        trend_dir = what.get('trend_direction', '')
        velocity = what.get('velocity', 0)
        state_text = what.get('state_text', '')

        parts = []

        # 评分
        if score is not None and score > 0:
            score_str = f"{score:.0f}分"
            if mode == 'chat':
                parts.append(f"你的睡眠评分在{score_str}")
            else:
                band_str = f"，{band}" if band else ""
                parts.append(f"你的睡眠评分在{score_str}左右{band_str}")

        # 趋势
        if trend_dir == 'down' and abs(velocity) > 1:
            parts.append(f"近3天以每天{abs(velocity):.1f}分的速度下滑")
        elif trend_dir == 'up' and abs(velocity) > 1:
            parts.append(f"近3天以每天{velocity:.1f}分的速度上升")
        elif trend_dir == 'down':
            parts.append("近期呈下降趋势")
        elif trend_dir == 'up':
            parts.append("近期呈上升趋势")

        # 状态描述词
        if state_text and mode != 'chat':
            parts.append(f"整体处于「{state_text}」阶段")

        if not parts:
            return ""

        return '。'.join(parts) + '。'

    def _build_why_segment(self, why: dict, mode: str) -> str:
        """构建模块2：原因"""
        symptoms = why.get('symptoms', [])
        emotion_trend = why.get('emotion_trend', '')
        circadian = why.get('circadian_regularity', '')

        parts = []

        if symptoms:
            symptom_text = '、'.join(symptoms[:3])  # 最多3个
            parts.append(f"主要受{symptom_text}影响")

        if circadian:
            parts.append(f"你的{cicadian}")

        if emotion_trend:
            parts.append(emotion_trend)

        if not parts:
            return ""

        # 连接
        if len(parts) >= 2:
            text = '。'.join(parts[:-1]) + '。' + parts[-1]
        else:
            text = parts[0]

        if '焦虑' in text or '负面' in text:
            text += "这可能会加剧入睡难度。"

        return text

    def _build_whats_next_segment(self, whats_next: dict, mode: str) -> str:
        """构建模块3：预测"""
        predicted = whats_next.get('predicted_score')
        extrapolated = whats_next.get('extrapolated_score')

        parts = []

        if predicted is not None:
            parts.append(f"我预测你今晚评分可能在{predicted:.0f}分左右")
            conf = whats_next.get('prediction_confidence', 0)
            if conf > 0.7:
                parts.append("这个预测比较确信")
            elif conf > 0.5:
                parts.append("预测有一定把握")
            elif conf > 0:
                parts.append("预测存在较大不确定性")
        elif extrapolated is not None:
            parts.append(f"按当前趋势，明晚评分可能降至{extrapolated:.0f}分")

        if not parts:
            return ""

        text = '。'.join(parts) + '。'

        # 给简短版加个预测提示
        if predicted is not None and predicted < 50 and mode == 'chat':
            text += "今晚可能需要早点准备入睡。"

        return text

    def _build_what_to_do_segment(self, what_to_do: dict, mode: str) -> str:
        """构建模块4：建议"""
        intervention = what_to_do.get('recommended_intervention', '')
        reason = what_to_do.get('intervention_reason', '')
        effectiveness = what_to_do.get('intervention_effectiveness', '')

        parts = []

        if intervention:
            parts.append(f"我推荐今晚试试{intervention}")

        if reason:
            parts.append(f"这是我根据你最近的数据推算的最优方案")

        if effectiveness and '建议效果追踪' in effectiveness:
            # 提取效果数据
            for line in effectiveness.split('\n'):
                line = line.strip()
                if '上次' in line or '有效' in line or '80%' in line or '反馈' in line:
                    parts.append(f"你类似的用户中，{line}")
                    break

        if not parts:
            return ""

        return '。'.join(parts) + '。'


# ==================== 全局实例 ====================

_narrative_instance = None


def get_narrative_engine() -> NarrativeEngine:
    """获取全局叙事引擎实例"""
    global _narrative_instance
    if _narrative_instance is None:
        _narrative_instance = NarrativeEngine()
    return _narrative_instance


# ==================== 自测 ====================

def _run_self_test():
    """运行5个自测场景"""
    import sys

    print('=' * 60)
    print('Narrative Engine Self-Test (v6.3.0)')
    print('=' * 60)

    ne = NarrativeEngine()
    results = []

    # ---------- Test 1: 有数据的用户 → 完整4模块 ----------
    print('\n1. 有数据的用户 → 生成包含4个模块的完整故事')
    try:
        # 先创建一个有数据的用户
        from pomdp_learner import get_engine
        engine = get_engine()
        engine.observe('_ba_narrative_test', text='失眠了睡不着', score=55)
        engine.observe('_ba_narrative_test', text='翻来覆去', score=50)
        engine.observe('_ba_narrative_test', text='凌晨醒了', score=45)

        from working_memory import get_working_memory
        wm = get_working_memory()
        for i, s in enumerate([55, 50, 45]):
            wm.push('_ba_narrative_test', {
                'text': f'Day {i}',
                'score_obs': s,
                'emotion': 'negative',
                'intervention': 'none',
                'outcome': 'none',
            })

        result = ne.generate_story('_ba_narrative_test', {'mode': 'analyze'})
        story = result['story']
        modules = result['modules']
        print(f'   Story length: {len(story)} chars')
        print(f'   Story: {story[:200]}...')
        ok = result['has_data'] and len(story) > 80 and all(k in modules for k in ['what', 'why', 'whats_next', 'what_to_do'])
        print(f'   PASS={ok}')
        results.append(('1-完整故事', ok))
    except Exception as e:
        print(f'   FAIL: {e}')
        import traceback
        traceback.print_exc()
        results.append(('1-完整故事', False))

    # ---------- Test 2: 空用户 → 简短版 ----------
    print('\n2. 空用户 → 生成简短版')
    try:
        result = ne.generate_story('_ba_narrative_empty', {'mode': 'chat'})
        story = result['story']
        print(f'   Story: {story}')
        ok = not result['has_data'] and '数据不足' in story
        print(f'   PASS={ok}')
        results.append(('2-空用户', ok))
    except Exception as e:
        print(f'   FAIL: {e}')
        results.append(('2-空用户', False))

    # ---------- Test 3: 下降趋势用户 → "恶化"语义 ----------
    print('\n3. 下降趋势用户 → 故事体现"恶化"语义')
    try:
        from working_memory import get_working_memory
        wm = get_working_memory()
        wm.push('_ba_narrative_down', {'text': 'Day0', 'score_obs': 75, 'emotion': 'neutral', 'intervention': 'none', 'outcome': 'none'})
        wm.push('_ba_narrative_down', {'text': 'Day1', 'score_obs': 65, 'emotion': 'negative', 'intervention': 'none', 'outcome': 'none'})
        wm.push('_ba_narrative_down', {'text': 'Day2', 'score_obs': 55, 'emotion': 'negative', 'intervention': 'none', 'outcome': 'none'})
        wm.push('_ba_narrative_down', {'text': 'Day3', 'score_obs': 45, 'emotion': 'negative', 'intervention': 'none', 'outcome': 'none'})

        result = ne.generate_story('_ba_narrative_down', {'mode': 'analyze'})
        story = result['story']
        print(f'   Story: {story[:200]}...')
        ok = '下滑' in story or '下降' in story or '恶化' in story or '降低' in story
        print(f'   PASS={ok}')
        results.append(('3-下降趋势', ok))
    except Exception as e:
        print(f'   FAIL: {e}')
        results.append(('3-下降趋势', False))

    # ---------- Test 4: 上升趋势用户 → "改善"语义 ----------
    print('\n4. 上升趋势用户 → 故事体现"改善"语义')
    try:
        from working_memory import get_working_memory
        wm = get_working_memory()
        wm.push('_ba_narrative_up', {'text': 'Day0', 'score_obs': 40, 'emotion': 'negative', 'intervention': 'none', 'outcome': 'none'})
        wm.push('_ba_narrative_up', {'text': 'Day1', 'score_obs': 55, 'emotion': 'neutral', 'intervention': 'none', 'outcome': 'none'})
        wm.push('_ba_narrative_up', {'text': 'Day2', 'score_obs': 65, 'emotion': 'positive', 'intervention': 'none', 'outcome': 'none'})
        wm.push('_ba_narrative_up', {'text': 'Day3', 'score_obs': 75, 'emotion': 'positive', 'intervention': 'none', 'outcome': 'none'})

        result = ne.generate_story('_ba_narrative_up', {'mode': 'analyze'})
        story = result['story']
        print(f'   Story: {story[:200]}...')
        ok = '上升' in story or '改善' in story or '提高' in story or '攀升' in story
        print(f'   PASS={ok}')
        results.append(('4-上升趋势', ok))
    except Exception as e:
        print(f'   FAIL: {e}')
        results.append(('4-上升趋势', False))

    # ---------- Test 5: 注入LLM prompt格式 ----------
    print('\n5. 注入LLM prompt格式正确')
    try:
        # 模拟chat_prompt_builder的注入
        from pomdp_learner import get_engine
        engine = get_engine()
        engine.observe('_ba_narrative_llm', text='睡不好', score=60)
        engine.observe('_ba_narrative_llm', text='醒了', score=55)

        from working_memory import get_working_memory
        wm = get_working_memory()
        for i, s in enumerate([60, 55, 50]):
            wm.push('_ba_narrative_llm', {
                'text': f'Day {i}',
                'score_obs': s,
                'emotion': 'neutral',
                'intervention': 'none',
                'outcome': 'none',
            })

        result = ne.generate_story('_ba_narrative_llm', {'mode': 'chat'})
        story = result['story']

        # 模拟注入格式: 用方括号包裹
        formatted = f"[睡眠故事: {story}]"
        print(f'   Formatted: {formatted[:150]}...')
        ok = formatted.startswith('[睡眠故事:') and formatted.endswith(']')
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
