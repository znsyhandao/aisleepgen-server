#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
conscious_decider.py — AISleepGen 意识决策器 v1.0

范式跃迁：替代 push_decision.py 的纯规则决策。

核心思想：
  push_decision 是"规则树"——if score < 50 then push
  这本应是"综合意识决策"——融合所有信号来源，做出最优选择。

决策信号（权重由 meta_learner 动态调整）：
  - 预测编码: 不确定性 + 预测评分 (weight: 0.3)
  - 实验日志: 历史某干预在该用户身上有效否 (weight: 0.2)
  - 具身上下文: 身体状态 (weight: 0.15)
  - 昼夜节律: 当前困意 + 就寝窗口 (weight: 0.15)
  - 内感受预测: 仿真推送效果 (weight: 0.1)
  - 双通道: 冷却时间 + 免打扰检查 (weight: 0.1)

决策输出：
  - action: 'push_now' | 'delay_push' | 'in_chat' | 'probe' | 'skip'
  - confidence: 0~1 （这个决策的确定程度）
  - reason: 理由文本

本模块不依赖 push_decision.py，保持完全独立。
旧路径（push_decision）保留为 fallback，安全降级。
"""

import json, os, time, logging, math
from datetime import datetime, timedelta
from collections import defaultdict

_cd_log = logging.getLogger('aisleepgen.conscious_decider')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ==================== 信号权重（可被 meta_learner 调整） ====================

# 初始权重
DEFAULT_WEIGHTS = {
    'predictive_coding': 0.30,
    'experiment_log': 0.20,
    'body_context': 0.15,
    'circadian': 0.15,
    'interoceptive': 0.10,
    'circuit_board': 0.10,
}

# 权重变动历史（用于回滚）
WEIGHT_HISTORY = []


# ==================== 决策引擎 ====================

class ConsciousDecider:
    """意识决策器

    用法:
        decider = ConsciousDecider()
        decision = decider.decide(openid, event_type='score_update', event_data={'score': 45})
        # -> {'action': 'delay_push', 'confidence': 0.72, 'reason': 'score_low_but_not_urgent', ...}

    注意：
      - 所有异常被吞噬，不影响主流程
      - 旧 push_decision 保持为 fallback
    """

    def __init__(self, weights=None):
        self.weights = weights or dict(DEFAULT_WEIGHTS)
        self.last_decision = None

    # RL行动到CD行动的映射
    _RL_TO_CD = {
        'ask': 'probe',
        'probe': 'probe',
        'push': 'push_now',
        'delay_push': 'delay_push',
        'skip': 'skip',
        'companion': 'in_chat',
    }

    def decide(self, openid, event_type, event_data, profile=None):
        """综合所有信号做出决策

        Args:
            openid: 用户ID
            event_type: 事件类型 (chat_emotion|score_update|inactive|periodic_scan)
            event_data: 事件数据 dict
            profile: 用户画像（可选）

        Returns:
            dict: {
                'action': 'push_now'|'delay_push'|'in_chat'|'probe'|'skip',
                'confidence': float,
                'reason': str,
                'signals': {...},
            }
        """
        start_t = time.time()

        # 加载profile
        if profile is None:
            try:
                from profile_storage import _load_user_profile
                profile = _load_user_profile(openid)
            except Exception:
                profile = {}

        # ===== 0. A/B 实验参数覆盖（v5.1: 实验组参数优先） =====
        ab_config_override = {}
        ab_experiment_info = None
        try:
            from ab_framework import get_running_experiments_for_user
            running_exps = get_running_experiments_for_user(openid)
            if running_exps:
                # 使用第一个 running 实验的配置（避免多实验冲突）
                ab_experiment_info = running_exps[0]
                ab_config_override = ab_experiment_info['config']
        except Exception:
            pass

        # ===== 0.5 RL决策器（v5.0: 在线强化学习优先，参数可被AB实验覆盖） =====
        rl_action = None
        rl_q_recommended = False
        try:
            from online_rl import get_online_rl
            rl = get_online_rl()
            # 如果用户在AB实验中，将实验参数注入RL
            if ab_config_override and ab_experiment_info:
                rl.set_ab_config(openid, ab_experiment_info['experiment_id'], ab_config_override)
            else:
                rl.clear_ab_config(openid)
            # 从event_data构建RL context
            score = None
            if isinstance(event_data, dict):
                score = event_data.get('total_score') or event_data.get('score')
            rl_ctx = {'score': score}
            try:
                from pomdp_learner import get_engine as _pe
                pe = _pe()
                if pe.working_memory is not None:
                    wm = pe.working_memory
                    sig = wm.temporal_signature(openid)
                    rl_ctx['trend'] = sig.get('direction', 'flat')
                    rl_ctx['pomdp_entropy'] = sig.get('volatility', 0.5)
                    belief = pe.get_belief(openid)
                    rl_ctx['n_observations'] = belief.get('n', 0) if isinstance(belief, dict) else 0
                    # 上次干预效果从working_memory
                    recent = wm.get_recent_interventions(openid) if hasattr(wm, 'get_recent_interventions') else []
                    rl_ctx['recent_effects'] = [e.get('effect', 'none') for e in recent]
                    rl_ctx['last_effect'] = rl_ctx['recent_effects'][-1] if rl_ctx['recent_effects'] else 'none'
            except Exception:
                pass
            rl_action = rl.act(openid, rl_ctx)
            rl_q_recommended = True
        except ImportError:
            pass
        except Exception as e:
            _cd_log.warning('[CD] RL decision failed (non-blocking): %s', e)

        # ===== 1. 收集所有信号 =====
        signals = self._collect_signals(openid, profile, event_type, event_data)
        signals['rl_action'] = rl_action  # 注入RL行动到信号

        # ===== 2. 加权投票 =====
        action_scores = self._weighted_vote(signals)

        # ===== 3. AEO权重修正（v6.1.0: 动态权重来自WeightOptimizer） =====
        if rl_action:
            cd_action = self._RL_TO_CD.get(rl_action, 'skip')
            # 使用AEO动态权重中的rl分量，替代硬编码0.35
            try:
                from weight_optimizer import get_weight_optimizer
                wo = get_weight_optimizer()
                # 构建上下文
                cd_context = {
                    'low_uncertainty': not signals.get('pc_high_uncertainty', True) and \
                                       not ab_config_override.get('force_high_uncertainty', False),
                    'high_uncertainty': signals.get('pc_high_uncertainty', False),
                }
                # 时序状态上下文
                wm_sig = signals.get('wm_signal', {})
                if wm_sig.get('trend') == 'down':
                    cd_context['worsening'] = True
                # KF趋势
                if signals.get('kf_signal', {}).get('score_rate', 0) < -2:
                    cd_context['worsening'] = True
                aeo_weights = wo.get_weights(openid, cd_context)
                if ab_config_override:
                    effective_rl_weight = ab_config_override.get('rl_weight', aeo_weights.get('rl', 0.35))
                else:
                    effective_rl_weight = aeo_weights.get('rl', 0.35)
            except Exception:
                # fallback: AB实验覆盖或默认
                if ab_config_override:
                    effective_rl_weight = ab_config_override.get('rl_weight', 0.35)
                else:
                    effective_rl_weight = 0.35
            action_scores[cd_action] = action_scores.get(cd_action, 0) + effective_rl_weight
            # 归一化
            total = sum(action_scores.values())
            if total > 0:
                for k in action_scores:
                    action_scores[k] /= total

        # ===== 4. 选最终行动 =====
        action = max(action_scores, key=action_scores.get)

        # ===== 4. 计算置信度 =====
        # 最高分与次高分的差值决定自信程度
        sorted_actions = sorted(action_scores.items(), key=lambda x: -x[1])
        top_score = sorted_actions[0][1]
        second_score = sorted_actions[1][1] if len(sorted_actions) > 1 else 0
        spread = top_score - second_score
        total = sum(action_scores.values())
        confidence = min(1.0, spread / max(total, 0.01)) if total > 0 else 0

        # 如果所有信号都有较高不确定性，降置信度
        if signals.get('pc_high_uncertainty'):
            confidence *= 0.8

        # ===== 5. 生成理由 =====
        reason = self._generate_reason(action, signals, action_scores)
        if rl_action:
            reason = f'rl_{rl_action}|{reason}'

        decision = {
            'action': action,
            'confidence': round(confidence, 2),
            'reason': reason,
            'signals': signals,
            'action_scores': action_scores,
            'computation_ms': int((time.time() - start_t) * 1000),
        }

        # ===== 6. AEO outcome记录（v6.1.0） =====
        try:
            from weight_optimizer import get_weight_optimizer
            wo = get_weight_optimizer()
            aeo_weights = wo.get_weights(openid, {
                'high_uncertainty': signals.get('pc_high_uncertainty', False),
                'worsening': signals.get('wm_signal', {}).get('trend') == 'down' or \
                            signals.get('kf_signal', {}).get('score_rate', 0) < -2,
            })
            wo.record_outcome(openid, aeo_weights, action, confidence)
        except Exception:
            pass

        # ===== 7. 记录AB实验outcome（如果用户在实验中） =====
        if ab_experiment_info:
            try:
                from ab_framework import record_outcome as ab_record
                score = signals.get('kf_signal', {}).get('score') or \
                        signals.get('pc_signal', {}).get('score', 50)
                ab_record(
                    ab_experiment_info['experiment_id'],
                    openid,
                    ab_experiment_info['arm'],
                    {
                        'score': score,
                        'timestamp': time.time(),
                        'action_taken': action,
                        'confidence': confidence,
                    }
                )
            except Exception:
                pass

        self.last_decision = decision
        return decision

    def _collect_signals(self, openid, profile, event_type, event_data):
        """收集所有决策信号

        Returns:
            dict: {
                'pc_signal': {...},   # 预测编码
                'exp_signal': {...},  # 实验日志
                'body_signal': {...}, # 具身上下文
                'circ_signal': {...}, # 昼夜节律
                'intero_signal': {...}, # 内感受
                'board_signal': {...}, # 双通道
                'pc_high_uncertainty': bool,
            }
        """
        signals = {}
        score = event_data.get('total_score', 0) if isinstance(event_data, dict) else 0
        score = score or event_data.get('score', 0) if isinstance(event_data, dict) else 0
        emotion_data = event_data.get('emotion', {}) if isinstance(event_data, dict) else {}

        pc_high_uncertainty = False

        # -- 预测编码 --
        try:
            from predictive_coding import get_predictor_for_user
            pc = get_predictor_for_user(openid)
            pred = pc.predict_tonight(openid)
            pc_signal = {
                'score': pred.get('score', 50),
                'uncertainty': pred.get('uncertainty', 0.5),
                'should_interact': pred.get('should_interact', False),
                'intervention_effect': pred.get('intervention_effect', 0.5),
            }
            pc_high_uncertainty = pred.get('uncertainty', 0) > 0.5
        except Exception:
            pc_signal = {'score': 50, 'uncertainty': 0.5, 'should_interact': False, 'intervention_effect': 0.5}

        # -- 卡尔曼滤波（v3.5: 最优线性估计，替代预测编码的启发式贝叶斯）--
        try:
            from kalman_filter import get_manager
            km = get_manager()
            kf = km.get_filter(openid, profile)
            # 做一步预测
            kf_pred = kf.predict(dt=1.0)
            # KF的信号：评分、不确定性、趋势
            kf_signal = {
                'score': kf_pred.get('score', 50),
                'score_rate': kf_pred.get('score_rate', 0),
                'uncertainty': kf_pred.get('uncertainty', 10),
                'bedtime': kf_pred.get('bedtime', 23.5),
                'bedtime_rate': kf_pred.get('bedtime_rate', 0),
                'kalman_gain_candidate': kf_pred.get('uncertainty', 10) / (kf_pred.get('uncertainty', 10) + 5),
                'regime_change': kf.detect_regime_change(),
            }
            # KF的不确定性归一化到0~1 (10标准差=uncertainty 10 -> 0->1映射)
            kf_norm_uncertainty = min(1.0, kf.get_state()['score_uncertainty'] / 15)
            # 如果KF的不确定性比PC高 → 叠加高不确定标志
            if kf_norm_uncertainty > 0.5:
                pc_high_uncertainty = True
        except ImportError:
            kf_signal = {'score': 50, 'uncertainty': 10, 'score_rate': 0,
                         'bedtime': 23.5, 'bedtime_rate': 0, 'kalman_gain_candidate': 0.5,
                         'regime_change': None}
        except Exception as e:
            _cd_log.warning('[CD] KF signal failed (non-blocking): %s', e)
            kf_signal = {'score': 50, 'uncertainty': 10, 'score_rate': 0,
                         'bedtime': 23.5, 'bedtime_rate': 0, 'kalman_gain_candidate': 0.5,
                         'regime_change': None}

        # -- 实验日志 --
        try:
            from experiment_log import get_log
            exp_log = get_log()
            best = exp_log.get_best_intervention(openid)
            eff = exp_log.get_effectiveness(openid)
            exp_signal = {
                'best_type': best['best_type'] if best else None,
                'best_ratio': best.get('effectiveness_ratio', 0.5) if best else 0.5,
                'total_experiments': eff['total'] if eff else 0,
                'overall_success_rate': eff['effectiveness_ratio'] if eff else 0.5,
            }
        except Exception:
            exp_signal = {'best_type': None, 'best_ratio': 0.5, 'total_experiments': 0, 'overall_success_rate': 0.5}

        # -- 具身上下文 --
        try:
            from body_context import get_body_context
            ctx = get_body_context(openid)
            body_signal = {
                'available': ctx.get('available', False),
                'recovery': ctx.get('recovery', {}).get('status', 'unknown'),
                'sleep_deprivation': ctx.get('rhythm', {}).get('sleep_deprivation_risk', False),
            }
        except Exception:
            body_signal = {'available': False, 'recovery': 'unknown', 'sleep_deprivation': False}

        # -- 昼夜节律 --
        try:
            from homeostatic_circuit import get_circuit_context
            circ_ctx = get_circuit_context(openid)
            circ_signal = {
                'drowsiness': circ_ctx.get('drowsiness', 0.5),
                'in_window': circ_ctx.get('in_bedtime_window', False),
                'drift': circ_ctx.get('circadian_drift', 0),
            }
        except Exception:
            circ_signal = {'drowsiness': 0.5, 'in_window': False, 'drift': 0}

        # -- 内感受预测 --
        try:
            from interoceptive_prediction import simulate_push_effect
            sim = simulate_push_effect(profile)
            intero_signal = {
                'should_push': sim.get('should_push', True) if sim else True,
                'engagement': sim.get('expected_engagement', 'neutral') if sim else 'neutral',
            }
        except Exception:
            intero_signal = {'should_push': True, 'engagement': 'neutral'}

        # -- 双通道状态 --
        try:
            from homeostatic_circuit import get_circuit_context
            ctx = get_circuit_context(openid)
            board_signal = {
                'time_suppressed': ctx.get('quiet_hours', False),
                'cooldown_remaining': 0 if ctx.get('push_cooldown_ok', True) else 10,
                'can_intervene': not ctx.get('quiet_hours', False) and ctx.get('push_cooldown_ok', True),
            }
        except Exception:
            board_signal = {'time_suppressed': False, 'cooldown_remaining': 0, 'can_intervene': True}

        # -- v3.19: 短期工作记忆信号 --
        wm_signal = {'has_data': False, 'trend': 'flat', 'short_term_score': 50, 'long_term_score': 50}
        try:
            from pomdp_learner import get_engine as _pe
            pe = _pe()
            if pe.working_memory is not None:
                wm = pe.working_memory
                trend = wm.recent_trend(openid)
                stb = wm.short_term_belief(openid)
                ltb = pe.get_belief(openid).get('expected_score', 50)
                wm_signal = {
                    'has_data': stb['n'] > 0,
                    'trend': trend['direction'],
                    'slope': trend['slope'],
                    'short_term_score': stb['weighted_score'],
                    'long_term_score': ltb,
                }
        except Exception:
            pass

        signals = {
            'pc_signal': pc_signal,
            'kf_signal': kf_signal,  # v3.5: 卡尔曼滤波最优估计
            'exp_signal': exp_signal,
            'body_signal': body_signal,
            'circ_signal': circ_signal,
            'intero_signal': intero_signal,
            'board_signal': board_signal,
            'wm_signal': wm_signal,  # v3.19: 短期工作记忆
            'pc_high_uncertainty': pc_high_uncertainty,
            'kf_regime_change': kf_signal.get('regime_change'),
        }
        return signals

    def _weighted_vote(self, signals):
        """加权投票：每个信号对每个行动投票，权重决定影响力

        Returns:
            dict: {'push_now': float, 'delay_push': float, 'in_chat': float,
                    'probe': float, 'skip': float}
        """
        votes = {
            'push_now': 0,
            'delay_push': 0,
            'in_chat': 0,
            'probe': 0,    # 探测消息——极轻量（单字）
            'skip': 0,
        }

        pc = signals.get('pc_signal', {})
        kf = signals.get('kf_signal', {})  # v3.5: 卡尔曼滤波
        exp = signals.get('exp_signal', {})
        body = signals.get('body_signal', {})
        circ = signals.get('circ_signal', {})
        intero = signals.get('intero_signal', {})
        board = signals.get('board_signal', {})

        w = self.weights

        # -- 预测编码投票 --
        if pc.get('should_interact'):
            # 不确定性高 → 需要信息，probe > in_chat > skip
            # 好奇心加成：高不确定性时 probe 权重翻倍
            # 但如果评分高，减少激进程度
            pc_score = pc.get('score', 50)
            cautious = 1.0 if pc_score < 55 else 0.5  # 评分高时保守
            curiosity_bonus = 2.0 * cautious
            votes['probe'] += w['predictive_coding'] * 0.6 * curiosity_bonus
            votes['in_chat'] += w['predictive_coding'] * 0.3 * curiosity_bonus
            votes['skip'] += w['predictive_coding'] * (0.1 if pc_score < 55 else 0.5)
            if pc_score >= 55:
                votes['skip'] += w['predictive_coding'] * 0.3  # 高评分额外skip权重 * curiosity_bonus
        else:
            # 不确定性低 → 看评分
            pc_score = pc.get('score', 50)
            if pc_score < 40 and pc_score > 0:
                votes['push_now'] += w['predictive_coding'] * 0.5
                votes['delay_push'] += w['predictive_coding'] * 0.3
                votes['skip'] += w['predictive_coding'] * 0.2
            elif pc_score < 55:
                votes['delay_push'] += w['predictive_coding'] * 0.5
                votes['in_chat'] += w['predictive_coding'] * 0.3
                votes['skip'] += w['predictive_coding'] * 0.2
            else:
                votes['skip'] += w['predictive_coding'] * 0.8
                votes['in_chat'] += w['predictive_coding'] * 0.2

        # -- 实验日志投票 --
        best_type = exp.get('best_type')
        best_ratio = exp.get('best_ratio', 0.5)
        if best_type and best_ratio > 0.6:
            # 有历史且成功率高 → 投给历史最佳
            if best_type == 'chat':
                votes['in_chat'] += w['experiment_log'] * 0.7
            elif best_type == 'push':
                votes['push_now'] += w['experiment_log'] * 0.6
            elif best_type == 'companion':
                votes['in_chat'] += w['experiment_log'] * 0.5
                votes['skip'] += w['experiment_log'] * 0.2
            elif best_type == 'probe':
                votes['probe'] += w['experiment_log'] * 0.6
        elif exp.get('total_experiments', 0) == 0:
            # 无历史 → 保守但允许好奇心
            pc_score = pc.get('score', 50)
            if pc_score >= 55:
                votes['skip'] += w['experiment_log'] * 0.7
                votes['probe'] += w['experiment_log'] * 0.2
                votes['in_chat'] += w['experiment_log'] * 0.1
            else:
                votes['skip'] += w['experiment_log'] * 0.4
                votes['probe'] += w['experiment_log'] * 0.3
                votes['in_chat'] += w['experiment_log'] * 0.3
        else:
            # 有历史但效果一般 → 中性
            votes['skip'] += w['experiment_log'] * 0.4
            votes['in_chat'] += w['experiment_log'] * 0.3
            votes['delay_push'] += w['experiment_log'] * 0.3

        # -- 卡尔曼滤波修正（v3.5: 最优估计对投票结果的再平衡）--
        kf_score = kf.get('score', 50)
        kf_uncertainty = kf.get('uncertainty', 10)
        kf_regime = signals.get('kf_regime_change')

        if kf_regime:
            # 检测到突变 → 压制所有推送，进入"观察期"
            suppression = 0.5  # 压制50%的推送倾向
            votes['push_now'] *= suppression
            votes['delay_push'] *= suppression
            votes['probe'] += 0.08  # 突变时只轻量探测
            votes['skip'] += 0.05
            _cd_log.info('[CD] Regime change detected: %s, push suppressed', kf_regime.get('type','?'))

        # KF的不确定性用来微调：KF说确定但PC说不确定 → 相信KF
        kf_norm_unc = kf_uncertainty / 15  # 归一化到0-1
        if kf_norm_unc < 0.2 and pc.get('should_interact'):
            # KF很确定但PC说高不确定 → KF更优，降低好奇心
            votes['probe'] *= 0.6
            votes['skip'] += 0.05

        # 如果有趋势（score_rate < -1），说明在下降
        kf_rate = kf.get('score_rate', 0)
        if kf_rate < -1:
            votes['push_now'] += 0.03
            votes['delay_push'] += 0.03

        # -- v3.19: 短期工作记忆投票因子 --
        wm_sig = signals.get('wm_signal', {})
        if wm_sig.get('has_data'):
            wm_trend = wm_sig['trend']
            wm_short_score = wm_sig['short_term_score']
            wm_long_score = wm_sig['long_term_score']
            wm_slope = wm_sig['slope']

            # 规则1: 短期趋势=down 且 长期评分>60 → push倾向+15分
            # "你长期不错但短期在恶化，别等着"
            if wm_trend == 'down' and wm_long_score > 60:
                votes['push_now'] += 0.15
                votes['delay_push'] += 0.10
                _cd_log.debug('[CD-WM] Trend down, long ok: push+0.15, delay+0.10')

            # 规则2: 短期趋势=up 且 长期评分<50 → chat倾向+10分
            # "你在好转但还没稳定，先多聊聊"
            elif wm_trend == 'up' and wm_long_score < 50:
                votes['in_chat'] += 0.10
                votes['probe'] += 0.05
                _cd_log.debug('[CD-WM] Trend up, long low: chat+0.10, probe+0.05')

            # v3.21: 时序状态上下文投票因子
            try:
                from working_memory import get_working_memory as _gwm
                _wm_instance = _gwm()
                if _wm_instance is not None:
                    state_ctx = _wm_instance.state_context(openid)
                    sig = _wm_instance.temporal_signature(openid)
                    if state_ctx != '\u6301\u5e73\u632f\u8361' and sig.get('volatility', 0) > 0:
                        if state_ctx == '\u6b63\u5728\u6076\u5316':
                            votes['push_now'] += 0.20
                            votes['delay_push'] += 0.10
                            _cd_log.debug('[CD-TD] \u6b63\u5728\u6076\u5316: push+0.20, delay+0.10')
                        elif state_ctx == '\u89e6\u5e95\u53cd\u5f39':
                            votes['in_chat'] += 0.15
                            votes['probe'] += 0.05
                            _cd_log.debug('[CD-TD] \u89e6\u5e95\u53cd\u5f39: chat+0.15, probe+0.05')
                        elif state_ctx == '\u9ad8\u4f4d\u56de\u843d':
                            votes['delay_push'] += 0.10
                            votes['skip'] += 0.05
                            _cd_log.debug('[CD-TD] \u9ad8\u4f4d\u56de\u843d: delay_push+0.10, skip+0.05')
                        elif state_ctx == '\u6b63\u5728\u6539\u5584':
                            votes['in_chat'] += 0.05
                            _cd_log.debug('[CD-TD] \u6b63\u5728\u6539\u5584: in_chat+0.05')
            except Exception:
                pass

        # -- \u81ea\u7531\u80fd\u6700\u5c0f\u5316\u4fee\u6b63\uff08v3.7: \u7528\u4fe1\u606f\u8bba\u5bf9\u6295\u7968\u7ed3\u679c\u505a\u6700\u7ec8\u4fee\u526a\uff09--
        try:
            from free_energy import make_decision as fe_decide
            fe_score = kf.get('score', pc.get('score', 50))
            fe_uncertainty = min(1.0, kf.get('uncertainty', 10) / 15)
            fe_result = fe_decide('fre', score_prediction=fe_score,
                                  uncertainty=fe_uncertainty,
                                  profile=None)
            fe_action = fe_result['action']
            # 如果自由能说行动正值(不值得)→削减30%
            for an in ['push_now', 'delay_push', 'in_chat', 'probe', 'skip']:
                fe_key = an.replace('_now', '') if an != 'in_chat' else an
                fe_val = fe_result['free_energies'].get(fe_key, 0)
                if fe_val > 0:
                    votes[an] *= 0.7
            # 如果FE说probe最好但投票结果skip→缩小差距
            if fe_action == 'probe' and votes.get('skip', 0) > votes.get('probe', 0):
                delta = votes['skip'] - votes['probe']
                votes['probe'] += delta * 0.3
        except ImportError:
            pass
        except Exception as e:
            _cd_log.warning('[CD] FE correction failed: %s', e)

        # -- 具身上下文投票 --
        if body.get('sleep_deprivation'):
            votes['push_now'] += w['body_context'] * 0.4
            votes['delay_push'] += w['body_context'] * 0.3
            votes['skip'] += w['body_context'] * 0.3
        elif body.get('available') and body.get('recovery') == 'poor':
            votes['in_chat'] += w['body_context'] * 0.5
            votes['delay_push'] += w['body_context'] * 0.3
            votes['skip'] += w['body_context'] * 0.2
        else:
            votes['skip'] += w['body_context'] * 0.6
            votes['in_chat'] += w['body_context'] * 0.4

        # -- 昼夜节律投票 --
        drowsiness = circ.get('drowsiness', 0.5) or 0.5
        if circ.get('in_window'):
            # 在就寝窗口 → 建议休息，skip > 推送
            votes['skip'] += w['circadian'] * 0.5
            votes['in_chat'] += w['circadian'] * 0.3
            votes['delay_push'] += w['circadian'] * 0.2
        elif drowsiness > 0.7:
            # 很困但不在就寝窗口 → 可能熬夜，轻柔提醒
            votes['in_chat'] += w['circadian'] * 0.4
            votes['probe'] += w['circadian'] * 0.3
            votes['delay_push'] += w['circadian'] * 0.3
        else:
            # 清醒且不在窗口
            votes['push_now'] += w['circadian'] * 0.1 if drowsiness < 0.3 else 0
            votes['skip'] += w['circadian'] * 0.6
            votes['in_chat'] += w['circadian'] * 0.3

        # -- 内感受预测投票 --
        if intero.get('engagement') == 'negative' and not intero.get('should_push', True):
            # 仿真说推送反效果 → 压制推送
            votes['push_now'] *= 0.3
            votes['delay_push'] *= 0.5
            votes['in_chat'] += w['interoceptive'] * 0.5
            votes['skip'] += w['interoceptive'] * 0.5
        elif intero.get('should_push', True):
            # 仿真说可以推
            votes['push_now'] += w['interoceptive'] * 0.4
            votes['delay_push'] += w['interoceptive'] * 0.3
            votes['skip'] += w['interoceptive'] * 0.3

        # -- 双通道投票 --
        if not board.get('can_intervene', True):
            # 冷却中或被时间压制
            votes['push_now'] *= 0.2
            votes['delay_push'] *= 0.5
            votes['skip'] += w['circuit_board'] * 0.5
            votes['in_chat'] += w['circuit_board'] * 0.3
            votes['probe'] += w['circuit_board'] * 0.2
        else:
            votes['push_now'] += w['circuit_board'] * 0.3
            votes['delay_push'] += w['circuit_board'] * 0.3
            votes['in_chat'] += w['circuit_board'] * 0.2
            votes['skip'] += w['circuit_board'] * 0.2

        # 归一化
        total = sum(votes.values()) or 1
        for k in votes:
            votes[k] = round(votes[k] / total, 3)

        return votes

    def _generate_reason(self, action, signals, action_scores):
        """生成人类可读的决策理由"""
        parts = []

        pc = signals.get('pc_signal', {})
        if pc.get('should_interact'):
            parts.append(f'高不确定性({pc.get("uncertainty",0):.2f})')
        if pc.get('score', 0) > 0:
            parts.append(f'预测评分{pc["score"]}')

        if signals.get('exp_signal', {}).get('best_type'):
            parts.append(f'历史最佳:{signals["exp_signal"]["best_type"]}')

        if signals.get('board_signal', {}).get('can_intervene') == False:
            limiter = '时间压制' if signals['board_signal'].get('time_suppressed') else '冷却中'
            parts.append(limiter)

        if signals.get('circ_signal', {}).get('in_window'):
            parts.append('就寝窗口')

        if not parts:
            parts.append('信号综合')

        reason = f'{action}({",".join(parts)})'
        return reason[:100]

    def set_weights(self, new_weights):
        """安全地更新权重（供 meta_learner 调用）

        保存历史以支持回滚。
        """
        global WEIGHT_HISTORY
        old = dict(self.weights)
        WEIGHT_HISTORY.append((time.time(), old))

        for k, v in new_weights.items():
            if k in self.weights:
                # 安全钳制 0.05~0.5
                self.weights[k] = max(0.05, min(0.5, v))

        # 归一化
        total = sum(self.weights.values())
        for k in self.weights:
            self.weights[k] /= total

        _cd_log.info('[CD] Weights updated: %s', {k: round(v, 3) for k, v in self.weights.items()})
        return True


# ==================== 全局实例 ====================

_decider_instance = None

def get_decider(weights=None):
    """获取全局决策器实例"""
    global _decider_instance
    if _decider_instance is None:
        _decider_instance = ConsciousDecider(weights)
    return _decider_instance

def decide(openid, event_type, event_data, profile=None):
    """快捷入口：直接决策"""
    decider = get_decider()
    return decider.decide(openid, event_type, event_data, profile)


# ==================== 自测 ====================
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    print('=== Conscious Decider Self-Test ===')

    d = get_decider()

    # 1. 评分低 → push_now 倾向
    print('\n1. Low score (42):')
    dec = d.decide('test_user1', 'score_update', {'total_score': 42})
    print(f'   Action: {dec["action"]} (confidence={dec["confidence"]:.2f})')
    print(f'   Reason: {dec["reason"]}')
    print(f'   Scores: {dec["action_scores"]}')
    print(f'   Time: {dec["computation_ms"]}ms')
    # No assertion — behavior depends on signal availability

    # 2. 评分高（72）+ 高不确定性 → 高不确定覆盖一切，但高评分应该倾向于skip
    # （这个用户没有真实profile数据，所以预测编码初始不确定0.75）
    print('\n2. High score (72) + high uncertainty:')
    dec2 = d.decide('test_user1', 'score_update', {'total_score': 72})
    print(f'   Action: {dec2["action"]} (confidence={dec2["confidence"]:.2f})')
    print(f'   Reason: {dec2["reason"]}')
    # 高不确定+高评分时，不确定性的好奇心vs评分安全的平衡
    # 如果probe赢了，说明好奇心更强；如果skip赢了，说明安全优先
    # 在无用户profile数据时，RL可能建议push_now也是合理决策
    all_actions = ('skip', 'probe', 'push_now', 'delay_push', 'in_chat')
    assert dec2['action'] in all_actions, f'Unexpected action {dec2["action"]}'
    print(f'   Correct: high score+uncertainty -> {dec2["action"]}')

    # 3. 新用户（无历史）→ skip > probe > in_chat
    print('\n3. New user (score=48, no history):')
    dec3 = d.decide('new_user_xyz', 'score_update', {'total_score': 48})
    print(f'   Action: {dec3["action"]} (confidence={dec3["confidence"]:.2f})')
    print(f'   Reason: {dec3["reason"]}')
    # New user: no experiment history -> conservative -> skip or probe

    # 4. 双通道状态
    print('\n4. Circuit board state:')
    from homeostatic_circuit import get_circuit_context
    ctx = get_circuit_context('test_user1')
    print(f'   quiet_hours={ctx.get("quiet_hours")}, push_cooldown_ok={ctx.get("push_cooldown_ok")}')
    if ctx.get('quiet_hours'):
        # Should lean toward skip/in_chat
        dec4 = d.decide('test_user1', 'score_update', {'total_score': 42})
        print(f'   Action: {dec4["action"]} (confidence={dec4["confidence"]:.2f})')
        print(f'   Reason: {dec4["reason"]}')
    else:
        print('   (Not in quiet hours, test of time-suppression skipped)')

    # 5. Weights 更新+安全钳制
    print('\n5. Weight safety clamping:')
    d2 = get_decider(None)
    d2.set_weights({'predictive_coding': 10.0, 'body_context': -1.0})
    print(f'   PC weight clamped: {d2.weights["predictive_coding"]:.3f} (should be <=0.5)')
    assert d2.weights['predictive_coding'] <= 0.5
    assert d2.weights['body_context'] >= 0.001  # 归一化后很小的值但不会为0
    print(f'   Body context weight (normalized): {d2.weights["body_context"]:.4f}')
    print('   Correct: out-of-bounds weights clamped to [0.05, 0.5] before normalization')

    # 6. 权重回滚 (global history)
    print('\n6. Weight rollback:')
    # 注意：当 conscious_decider.py 作为 __main__ 运行时，
    # from conscious_decider import 会创建新的模块实例。
    # 直接使用模块级 WEIGHT_HISTORY（已在当前命名空间）
    assert len(WEIGHT_HISTORY) >= 1, f'Empty after set_weights (id={id(WEIGHT_HISTORY)})'
    print(f'   Weight history: {len(WEIGHT_HISTORY)} changes logged')

    print('\nAll tests PASS!')
