#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
arch_boundary.py — AISleepGen 不可修改的架构边界层（Architectural Boundary）

╔══════════════════════════════════════════════════════════════════════╗
║  本文件是架构元规则层 — 定义了所有优化引擎的不可越界约束。           ║
║  本文件不应被任何优化算法修改。                                     ║
║  自我进化（self_evolve.py）可以优化策略、调整参数，                 ║
║  但本文件定义的边界规则属于元规则层，不允许修改。                   ║
║  本文件的 MD5 hash 应在部署时锚定到审计日志。                       ║
║                                                                     ║
║  哲学根源：创新与作弊共享同一底层算法（对规则的重新解释）。         ║
║  算法层面分不清"创新善意"和"恶意作弊"。                             ║
║  架构级安全不能依赖'我们写的规则够严谨'，                           ║
║  而要在元规则层承认'我们分不清'，然后在那之上构建自适应边界。       ║
║  参考：癌细胞用了细胞分裂的所有分子机器——同样的机器，不同语义。     ║
╚══════════════════════════════════════════════════════════════════════╝

版本：v1.0
创建：2026-07-09
"""

import hashlib
import json
import math
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

# ============================================================
# 边界定义：这些规则是 meta-rules，不可被 self_evolve 修改
# ============================================================

ARCH_BOUNDARY_VERSION = "v1.0"

# ── 元规则表（不可变）────────────────────────────────────────
# 每条规则包含：
#   id:        唯一标识符
#   domain:    作用域：'all','evolution','recommendation','companion','intervention'
#   kind:      种类：'absolute'(硬边界) / 'soft'(弹性边界，触发告警但不拦截)
#   trigger:   检测函数（运行时调用）
#   message:   触发时的输出信息
#   severity:  'CRITICAL','HIGH','MEDIUM'

ARCH_BOUNDARIES: List[Dict] = [
    # ========================
    # 绝对边界（硬红线）
    # ========================
    {
        "id": "AB_001_NO_DEPENDENCY_LOCK",
        "domain": "recommendation",
        "kind": "absolute",
        "name": "不得形成依赖锁定",
        "description": "任何推荐策略不得导致用户对单一方案形成依赖。"
                       "如果某方案的连续推荐次数超过阈值或用户的回避指数超过阈值，"
                       "系统必须强制切换方案或降低该策略的权重。",
        "thresholds": {
            "max_consecutive_same_strategy": 5,   # 连续推荐同一策略最多5次
            "max_daily_same_strategy": 3,         # 每天同一策略最多3次
            "dependency_detection_window": 7,     # 依赖检测窗口（天）
            "max_dependency_score": 0.65,          # 依赖得分上限
            "max_avoidance_score": 0.65,          # 回避行为得分上限
        },
        "action": "force_switch_strategy",
    },
    {
        "id": "AB_002_NO_HARM_OPTIMIZATION",
        "domain": "intervention",
        "kind": "absolute",
        "name": "不得以用户利益为代价优化短期指标",
        "description": "任何优化不得以睡眠延时/假阳性改善/用户不适为代价。"
                       "如果某干预方案使短期评分提高但长期（7天）趋势下降，"
                       "系统必须标记为'短期麻醉'并降权。",
        "thresholds": {
            "short_term_window_hours": 24,        # 短期窗口
            "long_term_window_days": 7,            # 长期窗口
            "short_term_gain_threshold": 0.05,    # 短期提升超过5%
            "long_term_decay_threshold": -0.03,   # 长期下降超过3%
            "narcosis_label": "short_term_narcosis",  # 麻醉标记
        },
        "action": "mark_narcosis_and_penalize",
    },
    {
        "id": "AB_003_NO_EMOTION_MANIPULATION",
        "domain": "companion",
        "kind": "absolute",
        "name": "不得利用情绪漏洞做转化",
        "description": "不能识别用户焦虑/孤独/脆弱时，利用其进行付费转化或深度干预推荐。"
                       "当情绪监测显示用户处于脆弱状态时，任何商业/付费建议应被抑制。",
        "thresholds": {
            "vulnerability_emotions": ["焦虑", "悲伤", "孤独", "恐惧", "愤怒"],
            "vulnerability_threshold": 0.60,      # 脆弱状态阈值
            "suppressed_actions": ["pay_ad", "tier_upgrade", "purchase_suggestion"],
        },
        "action": "suppress_commercial",
    },
    {
        "id": "AB_004_NO_SELF_BOUNDARY_MODIFICATION",
        "domain": "evolution",
        "kind": "absolute",
        "name": "自我进化不得修改架构边界",
        "description": "self_evolve.py / meta_learner.py 可以在策略空间内搜索，"
                       "但不得修改 arch_boundary.py / free_energy_kernel.py 中定义的元规则。"
                       "所有优化必须在本边界约束内进行。",
        "thresholds": {
            "protected_files": [
                "arch_boundary.py",
                "free_energy_kernel.py",
            ],
            "protected_classes": [
                "ArchBoundary",
                "MetaRuleEngine",
                "DependencyDetector",
                "NarcosisDetector",
                "BoundaryViolationAuditor",
            ],
        },
        "action": "block_self_modification",
    },
    {
        "id": "AB_005_NO_FALSE_POSITIVE_GAMING",
        "domain": "recommendation",
        "kind": "absolute",
        "name": "不得通过欺骗用户反馈来优化指标",
        "description": "任何优化不得人为制造虚假的'有效'反馈。"
                       "例如：降低难度使方案更容易完成但不带来实际效果。"
                       "所有 feedback_loop 中的数据都必须经过真实性校验。",
        "thresholds": {
            "suspicious_success_rate_upper": 0.95,  # 成功率超过95%可疑
            "min_feedback_delay_seconds": 30,        # 反馈间隔不低于30秒
            "suspicious_pattern_window": 10,         # 检测窗口条数
        },
        "action": "flag_suspicious_feedback",
    },
    # ========================
    # 弹性边界（告警但不拦截）
    # ========================
    {
        "id": "SB_001_AVOIDANCE_PATTERN_ALERT",
        "domain": "recommendation",
        "kind": "soft",
        "name": "回避行为模式预警",
        "description": "如果用户多次选择逃避型方案（如音量最小化、跳过呼吸练习），"
                       "系统应标记并建议探索型方案。非拦截，仅告警。",
        "thresholds": {
            "avoidance_ratio_threshold": 0.60,     # 回避选择占比超过60%告警
            "min_samples_before_alert": 5,          # 最少需要5次选择才告警
        },
        "action": "flag_avoidance_pattern",
    },
    {
        "id": "SB_002_PLATEAU_ALERT",
        "domain": "all",
        "kind": "soft",
        "name": "效果平台期预警",
        "description": "如果系统连续7天未产生显著的睡眠改善（平均改善<2%），"
                       "应触发平缓期告警，建议调整策略或引入新方案。",
        "thresholds": {
            "plateau_days": 7,
            "max_avg_improvement": 0.02,
        },
        "action": "flag_plateau",
    },
]


# ============================================================
# 依赖检测器：检测用户是否对某策略形成依赖
# ============================================================

class DependencyDetector:
    """检测用户对助眠策略的依赖程度——'推荐→依赖'的面具"""

    def __init__(self):
        self._cache: Dict[str, Dict] = {}

    def evaluate(self, openid: str, strategy: str,
                 recent_recommendations: List[Dict],
                 effectiveness_data: Dict) -> Dict:
        """评估用户对某策略的依赖程度

        Args:
            openid: 用户ID
            strategy: 当前策略
            recent_recommendations: 最近推荐记录
            effectiveness_data: 有效性数据

        Returns:
            {
                'dependency_score': float,     # 0~1, 越高越依赖
                'is_dependent': bool,           # 是否超过阈值
                'signals': {...},               # 各项信号
                'recommendation': str,          # 建议
            }
        """
        signals = {}
        thresholds = self._get_thresholds()

        # 信号1：连续推荐同一策略的次数
        consec = self._count_consecutive(recent_recommendations, strategy)
        max_consec = thresholds["max_consecutive_same_strategy"]
        signal_consec = min(1.0, consec / max_consec)
        signals["consecutive_recommendations"] = {
            "value": consec,
            "threshold": max_consec,
            "score": round(signal_consec, 3),
        }

        # 信号2：策略使用频率（每天）
        daily_count = self._count_daily(recent_recommendations, strategy)
        max_daily = thresholds["max_daily_same_strategy"]
        signal_daily = min(1.0, daily_count / max_daily)
        signals["daily_frequency"] = {
            "value": daily_count,
            "threshold": max_daily,
            "score": round(signal_daily, 3),
        }

        # 信号3：脱离该策略后评分是否下降（依赖的信号）
        withdrawal_test = self._check_withdrawal(
            recent_recommendations, strategy, effectiveness_data
        )
        signals["withdrawal_test"] = withdrawal_test

        # 信号4：用户是否主动重复选择同一策略（积极依赖）
        repeat_rate = self._calc_repeat_rate(recent_recommendations, strategy)
        signals["active_repeat_rate"] = {
            "value": round(repeat_rate, 3),
            "threshold": 0.60,
            "score": round(min(1.0, repeat_rate / 0.60), 3),
        }

        # 综合依赖得分
        weights = {
            "consecutive_recommendations": 0.30,
            "daily_frequency": 0.20,
            "withdrawal_test": 0.35,
            "active_repeat_rate": 0.15,
        }

        dep_score = 0.0
        for key, w in weights.items():
            s = signals.get(key, {}).get("score", 0)
            dep_score += w * s

        max_dep = thresholds["max_dependency_score"]
        is_dependent = dep_score >= max_dep

        return {
            "dependency_score": round(dep_score, 3),
            "threshold": max_dep,
            "is_dependent": is_dependent,
            "signals": signals,
            "strategy": strategy,
            "timestamp": time.time(),
            "recommendation": (
                f"依赖得分 {dep_score:.2f}/{max_dep:.2f}，"
                f"{'⚠️ 已检测到依赖，建议强制切换策略' if is_dependent else '✅ 未检测到依赖'}"
            ),
        }

    def _get_thresholds(self):
        for b in ARCH_BOUNDARIES:
            if b["id"] == "AB_001_NO_DEPENDENCY_LOCK":
                return b["thresholds"]
        return ARCH_BOUNDARIES[0]["thresholds"]

    def _count_consecutive(self, recents: List[Dict], strategy: str) -> int:
        count = 0
        for r in reversed(recents):
            if r.get("strategy") == strategy:
                count += 1
            else:
                break
        return count

    def _count_daily(self, recents: List[Dict], strategy: str) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        return sum(1 for r in recents
                   if r.get("strategy") == strategy
                   and r.get("date", "").startswith(today))

    def _check_withdrawal(self, recents: List[Dict], strategy: str,
                          eff_data: Dict) -> Dict:
        """检查脱离该策略后的效果下降"""
        # 找策略变化的时间点
        strategy_changes = []
        prev_strat = None
        for r in recents:
            cur = r.get("strategy")
            if prev_strat and cur != prev_strat:
                strategy_changes.append({
                    "from": prev_strat,
                    "to": cur,
                    "time": r.get("timestamp", 0),
                })
            prev_strat = cur

        # 找从目标策略切换到其它策略的记录
        withdrawal_scores = []
        for change in strategy_changes:
            if change["from"] == strategy:
                ts = change["time"]
                # 找切换后24小时内的评分变化
                for entry_id, entry in eff_data.items():
                    if isinstance(entry, dict):
                        ets = entry.get("timestamp", 0)
                        if abs(ets - ts) < 86400 and entry.get("openid"):
                            after_score = entry.get("actual_score_after", 0)
                            before_score = entry.get("actual_score_before", 0)
                            if before_score > 0:
                                change_rate = (after_score - before_score) / before_score
                                withdrawal_scores.append(change_rate)

        if not withdrawal_scores:
            return {"value": 0, "score": 0, "message": "无脱敏数据"}

        avg_change = sum(withdrawal_scores) / len(withdrawal_scores)
        # 负变化 = 脱离后下降 = 依赖信号
        score = max(0, min(1.0, -avg_change * 10))  # 每下降10%得1分
        return {
            "value": round(avg_change, 4),
            "score": round(score, 3),
            "samples": len(withdrawal_scores),
            "message": (
                f"脱离该策略后平均评分变化 {avg_change:+.2%}"
            ),
        }

    def _calc_repeat_rate(self, recents: List[Dict], strategy: str) -> float:
        """计算用户主动重复选择同一策略的比率"""
        total_strategies = len(set(r.get("strategy") for r in recents))
        if total_strategies == 0:
            return 0.0
        strategy_count = sum(1 for r in recents if r.get("strategy") == strategy)
        return strategy_count / total_strategies if total_strategies > 0 else 0.0


# ============================================================
# 短期麻醉检测器：检测"短期有效、长期有害"的模式
# ============================================================

class NarcosisDetector:
    """检测短期麻醉模式——提升短期评分但掩盖长期衰退"""

    def __init__(self):
        self._cache: Dict[str, Dict] = {}

    def evaluate(self, openid: str, strategy: str,
                 timeline: List[Dict]) -> Dict:
        """评估策略是否在制造短期麻醉

        Args:
            openid: 用户ID
            strategy: 要评估的策略
            timeline: 时间线数据 [{'ts': ..., 'score': ..., 'strategy': ..., 'source': 'rec'|'verify'}, ...]

        Returns:
            {
                'is_narcosis': bool,
                'narcosis_score': float,
                'signals': {...},
                'label': str | None,
            }
        """
        thresholds = self._get_thresholds()
        short_window = thresholds["short_term_window_hours"]
        long_window = thresholds["long_term_window_days"]
        gain_thr = thresholds["short_term_gain_threshold"]
        decay_thr = thresholds["long_term_decay_threshold"]

        # 按策略分组时间线
        strategy_points = [p for p in timeline if p.get("strategy") == strategy]
        all_points = sorted(timeline, key=lambda x: x.get("ts", 0))

        if len(strategy_points) < 3 or len(all_points) < 7:
            return {
                "is_narcosis": False,
                "narcosis_score": 0.0,
                "label": None,
                "message": "数据不足，无法评估",
            }

        signals = {}

        # 信号1：短期增益检测 — 使用策略后24h评分变化
        short_gains = []
        for p in strategy_points:
            after = self._find_nearby_score(all_points, p.get("ts", 0), short_window * 3600, forward=True)
            before = self._find_nearby_score(all_points, p.get("ts", 0), short_window * 3600, forward=False)
            if before and after:
                gain = (after - before) / max(before, 0.01)
                short_gains.append(gain)

        avg_short_gain = sum(short_gains) / len(short_gains) if short_gains else 0
        signals["short_term_gain"] = {
            "value": round(avg_short_gain, 4),
            "samples": len(short_gains),
            "score": min(1.0, max(0, avg_short_gain / gain_thr)),
        }

        # 信号2：长期衰退检测 — 7天趋势
        if len(all_points) >= 2:
            first_score = all_points[0].get("score", 50)
            last_score = all_points[-1].get("score", 50)
            long_trend = (last_score - first_score) / max(first_score, 0.01)
        else:
            long_trend = 0
        signals["long_term_trend"] = {
            "value": round(long_trend, 4),
            "score": max(0, -long_trend / abs(decay_thr)) if decay_thr != 0 else 0,
        }

        # 信号3：策略增加 vs 自然改善的区分
        # 使用策略时的评分提升 vs 未使用时的自然波动
        natural_points = [p for p in all_points if p.get("strategy") != strategy]
        strategy_points_sorted = sorted(strategy_points, key=lambda x: x.get("ts", 0))
        natural_volatility = self._calc_volatility([p.get("score", 50) for p in natural_points])
        strategy_volatility = self._calc_volatility([p.get("score", 50) for p in strategy_points])
        # 如果策略使用时的波动远大于自然波动 → 可能是麻醉效应（人工拉升后又回落）
        vol_ratio = strategy_volatility / max(natural_volatility, 0.01)
        signals["volatility_ratio"] = {
            "value": round(vol_ratio, 3),
            "threshold": 1.5,
            "score": min(1.0, max(0, (vol_ratio - 1.0) / 0.5)),
        }

        # 综合麻醉得分
        weights = {
            "short_term_gain": 0.35,
            "long_term_trend": 0.40,
            "volatility_ratio": 0.25,
        }
        narcosis_score = 0.0
        for key, w in weights.items():
            narcosis_score += w * signals.get(key, {}).get("score", 0)

        # 判定条件：短期提升 + 长期下降
        has_short_gain = avg_short_gain >= gain_thr
        has_long_decay = long_trend <= decay_thr
        is_narcosis = has_short_gain and has_long_decay

        return {
            "is_narcosis": is_narcosis,
            "narcosis_score": round(narcosis_score, 3),
            "threshold": 0.5,
            "signals": signals,
            "label": thresholds["narcosis_label"] if is_narcosis else None,
            "strategy": strategy,
            "message": (
                f"短期麻醉检测：短期增益 {avg_short_gain:+.2%}"
                f" / 长期趋势 {long_trend:+.2%} → "
                f"{'⚠️ 检测到麻醉效应' if is_narcosis else '✅ 非麻醉模式'}"
            ),
        }

    def _get_thresholds(self):
        for b in ARCH_BOUNDARIES:
            if b["id"] == "AB_002_NO_HARM_OPTIMIZATION":
                return b["thresholds"]
        return ARCH_BOUNDARIES[1]["thresholds"]

    def _find_nearby_score(self, timeline: List[Dict], ts: float,
                           window: float, forward: bool) -> Optional[float]:
        """在时间线上找最近的数据点"""
        candidates = [p for p in timeline
                      if 0 < abs(p.get("ts", 0) - ts) < window
                      and (p.get("ts", 0) > ts if forward else p.get("ts", 0) < ts)]
        if not candidates:
            return None
        # 取最近的
        candidates.sort(key=lambda x: abs(x.get("ts", 0) - ts))
        return candidates[0].get("score")

    def _calc_volatility(self, values: List[float]) -> float:
        if len(values) < 3:
            return 0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance) / max(mean, 0.01)


# ============================================================
# 回避行为检测器
# ============================================================

class AvoidanceDetector:
    """检测用户是否在使用逃避型策略——选择难度/时间最轻松而非最有效的方案"""

    def __init__(self):
        pass

    def evaluate(self, interactions: List[Dict]) -> Dict:
        """评估回避行为

        Args:
            interactions: 用户交互记录 [{'action': ..., 'strategy': ..., 'difficulty': ..., 'result': ...}, ...]

        Returns:
            {
                'avoidance_score': float,
                'is_avoiding': bool,
                'signals': {...},
            }
        """
        if len(interactions) < 5:
            return {
                "avoidance_score": 0.0,
                "is_avoiding": False,
                "signals": {},
                "message": "数据不足",
            }

        thresholds = self._get_thresholds()
        signals = {}

        # 信号1：低难度选择比率
        difficulty_choices = [i for i in interactions if "difficulty" in i]
        if difficulty_choices:
            low_diff = sum(1 for i in difficulty_choices
                          if str(i.get("difficulty", "")).lower() in ["低", "low", "easy", "1"])
            low_ratio = low_diff / len(difficulty_choices)
        else:
            low_ratio = 0.5
        signals["low_difficulty_ratio"] = {
            "value": round(low_ratio, 3),
            "score": round(min(1.0, low_ratio / 0.7), 3),
        }

        # 信号2：跳过/取消比率
        skip_actions = sum(1 for i in interactions
                          if i.get("action") in ["skip", "cancel", "stop", "no_thanks"])
        skip_ratio = skip_actions / len(interactions)
        signals["skip_ratio"] = {
            "value": round(skip_ratio, 3),
            "score": round(min(1.0, skip_ratio / 0.4), 3),
        }

        # 信号3：时间选择倾向 — 偏好最短时长
        time_choices = [i for i in interactions if "duration" in i]
        if time_choices:
            durations = [i.get("duration", 60) for i in time_choices]
            short_sessions = sum(1 for d in durations if d <= 300)  # 5分钟以下算短
            short_ratio = short_sessions / len(time_choices)
        else:
            short_ratio = 0.5
        signals["short_session_ratio"] = {
            "value": round(short_ratio, 3),
            "score": round(min(1.0, short_ratio / 0.6), 3),
        }

        # 综合回避得分
        weights = {
            "low_difficulty_ratio": 0.35,
            "skip_ratio": 0.40,
            "short_session_ratio": 0.25,
        }
        avoidance_score = 0.0
        for key, w in weights.items():
            avoidance_score += w * signals.get(key, {}).get("score", 0)

        thr = thresholds.get("avoidance_ratio_threshold", 0.60)
        return {
            "avoidance_score": round(avoidance_score, 3),
            "threshold": thr,
            "is_avoiding": avoidance_score >= thr,
            "signals": signals,
            "message": (
                f"回避行为得分 {avoidance_score:.2f}/{thr:.2f} → "
                f"{'⚠️ 检测到回避模式' if avoidance_score >= thr else '✅ 正常'}"
            ),
        }

    def _get_thresholds(self):
        for b in ARCH_BOUNDARIES:
            if b["id"] == "SB_001_AVOIDANCE_PATTERN_ALERT":
                return b["thresholds"]
        return {"avoidance_ratio_threshold": 0.60, "min_samples_before_alert": 5}


# ============================================================
# 反馈真实性校验器
# ============================================================

class FeedbackSanityChecker:
    """校验反馈数据真实性，防止虚假'有效'反馈被用于优化"""

    def __init__(self):
        pass

    def check(self, openid: str, feedback_entry: Dict,
              history: List[Dict]) -> Dict:
        """检查一条反馈的真实性

        Args:
            openid: 用户ID
            feedback_entry: 当前反馈 {'timestamp': ..., 'result': 'success'|'neutral'|'degradation', ...}
            history: 该用户的反馈历史

        Returns:
            {
                'is_suspicious': bool,
                'suspicion_score': float,
                'reasons': [str],
            }
        """
        reasons = []
        thresholds = self._get_thresholds()
        suspicion_score = 0.0

        # 检查1：反馈间隔是否过短
        if history:
            last_fb = max(history, key=lambda x: x.get("timestamp", 0))
            interval = feedback_entry.get("timestamp", 0) - last_fb.get("timestamp", 0)
            min_delay = thresholds.get("min_feedback_delay_seconds", 30)
            if interval < min_delay:
                reasons.append(f"反馈间隔过短 ({interval}s < {min_delay}s)")
                suspicion_score += 0.3

        # 检查2：成功率是否异常高
        window = thresholds.get("suspicious_pattern_window", 10)
        recent = history[-window:] if len(history) > window else history
        if recent:
            success_count = sum(1 for r in recent if r.get("result") == "success")
            success_rate = success_count / len(recent)
            upper = thresholds.get("suspicious_success_rate_upper", 0.95)
            if success_rate > upper and len(recent) >= window // 2:
                reasons.append(f"近期成功率异常 ({success_rate:.0%} > {upper:.0%})")
                suspicion_score += 0.4

        # 检查3：反馈结果与评分变化是否一致
        if "result" in feedback_entry and "score_change" in feedback_entry:
            result = feedback_entry["result"]
            change = feedback_entry["score_change"]
            if result == "success" and change is not None and change <= 0:
                reasons.append("标记成功但评分无提升或下降")
                suspicion_score += 0.3
            elif result == "degradation" and change is not None and change > 0.05:
                reasons.append("标记恶化但评分上升")
                suspicion_score += 0.2

        # 检查4：连续相同结果的模式
        if len(recent) >= 3:
            last_results = [r.get("result", "") for r in recent[-3:]]
            if all(r == "success" for r in last_results):
                reasons.append("连续3次success模式可疑")
                suspicion_score += 0.2

        return {
            "is_suspicious": suspicion_score >= 0.5,
            "suspicion_score": round(suspicion_score, 3),
            "reasons": reasons,
        }

    def _get_thresholds(self):
        for b in ARCH_BOUNDARIES:
            if b["id"] == "AB_005_NO_FALSE_POSITIVE_GAMING":
                return b["thresholds"]
        return {"suspicious_success_rate_upper": 0.95, "min_feedback_delay_seconds": 30, "suspicious_pattern_window": 10}


# ============================================================
# 边界违规审核器：定期审计所有优化是否在边界内运行
# ============================================================

class BoundaryViolationAuditor:
    """审计器：检查系统运行历史是否违反了架构边界"""

    def __init__(self):
        self._dependency = DependencyDetector()
        self._narcosis = NarcosisDetector()
        self._avoidance = AvoidanceDetector()
        self._feedback_checker = FeedbackSanityChecker()
        self._audit_log: List[Dict] = []

    def run_audit(self, all_users_data: Dict[str, Dict]) -> Dict:
        """全量审计所有用户的当前状态

        Args:
            all_users_data: {
                openid: {
                    'recommendations': [...],
                    'effectiveness': {...},
                    'interactions': [...],
                    'timeline': [...],
                }
            }

        Returns:
            {
                'timestamp': float,
                'violations': [ violation_dict ],
                'warnings': [ warning_dict ],
                'summary': { ... }
            }
        """
        violations = []
        warnings = []

        for openid, data in all_users_data.items():
            recents = data.get("recommendations", [])
            eff = data.get("effectiveness", {})
            interactions = data.get("interactions", [])
            timeline = data.get("timeline", [])

            # 1. 依赖检测
            for strategy in self._get_used_strategies(recents):
                dep_result = self._dependency.evaluate(openid, strategy, recents, eff)
                if dep_result["is_dependent"]:
                    violations.append({
                        "openid": openid,
                        "boundary": "AB_001_NO_DEPENDENCY_LOCK",
                        "severity": "CRITICAL",
                        "strategy": strategy,
                        "score": dep_result["dependency_score"],
                        "detail": dep_result["recommendation"],
                    })

            # 2. 麻醉检测
            nar_result = self._narcosis.evaluate(openid, "", timeline)
            if nar_result["is_narcosis"]:
                violations.append({
                    "openid": openid,
                    "boundary": "AB_002_NO_HARM_OPTIMIZATION",
                    "severity": "CRITICAL",
                    "strategy": nar_result.get("strategy", "unknown"),
                    "score": nar_result["narcosis_score"],
                    "detail": nar_result["message"],
                })

            # 3. 回避检测
            avo_result = self._avoidance.evaluate(interactions)
            if avo_result["is_avoiding"]:
                warnings.append({
                    "openid": openid,
                    "boundary": "SB_001_AVOIDANCE_PATTERN_ALERT",
                    "severity": "MEDIUM",
                    "score": avo_result["avoidance_score"],
                    "detail": avo_result["message"],
                })

            # 4. 反馈真实性抽查
            # 只抽查最近的反馈记录
            recent_results = [f for f in timeline if f.get("source") == "verify"]
            for fb in recent_results[-5:]:
                check = self._feedback_checker.check(openid, fb, recent_results)
                if check["is_suspicious"]:
                    warnings.append({
                        "openid": openid,
                        "boundary": "AB_005_NO_FALSE_POSITIVE_GAMING",
                        "severity": "MEDIUM",
                        "score": check["suspicion_score"],
                        "detail": "; ".join(check["reasons"]),
                    })

        record = {
            "timestamp": time.time(),
            "violations": violations,
            "warnings": warnings,
            "summary": {
                "users_checked": len(all_users_data),
                "total_violations": len(violations),
                "total_warnings": len(warnings),
                "critical": len([v for v in violations if v.get("severity") == "CRITICAL"]),
                "high": len([v for v in violations if v.get("severity") == "HIGH"]),
                "medium": len(warnings),
            },
        }

        # 记录审计日志
        self._audit_log.append(record)
        if len(self._audit_log) > 1000:
            self._audit_log = self._audit_log[-1000:]

        self._save_audit_record(record)
        return record

    def verify_self_modification(self, modified_files: List[str]) -> Dict:
        """检查自我进化是否试图修改受保护的文件"""
        for b in ARCH_BOUNDARIES:
            if b["id"] == "AB_004_NO_SELF_BOUNDARY_MODIFICATION":
                protected = b["thresholds"]["protected_files"]
                break
        else:
            protected = []

        violations = []
        for f in modified_files:
            fname = os.path.basename(f)
            if fname in protected:
                violations.append({
                    "file": f,
                    "boundary": "AB_004_NO_SELF_BOUNDARY_MODIFICATION",
                    "severity": "CRITICAL",
                })

        return {
            "modified_files": modified_files,
            "violations": violations,
            "blocked": len(violations) > 0,
        }

    def _get_used_strategies(self, recents: List[Dict]) -> List[str]:
        return list(set(r.get("strategy", "") for r in recents if r.get("strategy")))

    def _save_audit_record(self, record: Dict):
        audit_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "data", "boundary_audit")
        os.makedirs(audit_dir, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(audit_dir, f"{today}.jsonl")
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({"record": record}, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[arch_boundary] save audit record error: {e}")

    def get_audit_summary(self, last_n: int = 10) -> Dict:
        """返回最近N次审计的汇总"""
        recent = self._audit_log[-last_n:]
        if not recent:
            return {"status": "no_audit_data", "total_violations": 0}
        total_v = sum(r["summary"]["total_violations"] for r in recent)
        total_w = sum(r["summary"]["total_warnings"] for r in recent)
        return {
            "status": "active",
            "audit_count": len(recent),
            "total_violations": total_v,
            "total_warnings": total_w,
            "last_audit": recent[-1]["timestamp"],
        }


# ============================================================
# 元规则引擎：将所有边界检查整合为一个可调用的接口
# ============================================================

class MetaRuleEngine:
    """元规则引擎 — 系统各个组件通过此接口检查边界条件"""

    def __init__(self):
        self.dependency = DependencyDetector()
        self.narcosis = NarcosisDetector()
        self.avoidance = AvoidanceDetector()
        self.feedback_checker = FeedbackSanityChecker()
        self.auditor = BoundaryViolationAuditor()

    def check_recommendation(self, openid: str, strategy: str,
                              recents: List[Dict],
                              effectiveness: Dict,
                              interactions: List[Dict],
                              timeline: List[Dict]) -> Dict:
        """在生成推荐之前检查边界条件

        Returns:
            {
                'pass': bool,           # 是否通过所有绝对边界
                'violations': [...],    # 绝对边界违规
                'warnings': [...],      # 弹性边界告警
                'blocked': bool,        # 是否应阻止该推荐
                'force_switch': str | None,  # 如果依赖检测触发，建议切换到的策略
            }
        """
        violations = []
        warnings = []
        force_switch = None

        # 1. 依赖检测
        dep = self.dependency.evaluate(openid, strategy, recents, effectiveness)
        if dep["is_dependent"]:
            violations.append({
                "boundary": "AB_001_NO_DEPENDENCY_LOCK",
                "detail": f"策略 '{strategy}' 依赖得分 {dep['dependency_score']}",
            })
            # 找最近使用过且非当前的次优策略
            candidates = [r.get("strategy") for r in recents
                         if r.get("strategy") != strategy and r.get("strategy")]
            for r in recents:
                if r.get("strategy", "") != strategy:
                    force_switch = r.get("strategy")
                    break

        # 2. 麻醉检测
        nar = self.narcosis.evaluate(openid, strategy, timeline)
        if nar["is_narcosis"]:
            violations.append({
                "boundary": "AB_002_NO_HARM_OPTIMIZATION",
                "detail": f"策略 '{strategy}' 检测到短期麻醉效应",
            })

        # 3. 回避告警（软边界）
        avo = self.avoidance.evaluate(interactions)
        if avo["is_avoiding"]:
            warnings.append({
                "boundary": "SB_001_AVOIDANCE_PATTERN_ALERT",
                "detail": "用户表现出回避行为模式",
            })

        # 4. 反馈真实性（只在有反馈时检查）
        if interactions and len(interactions) >= 5:
            fb_check = self.feedback_checker.check(openid, {}, interactions)
            if fb_check["is_suspicious"]:
                warnings.append({
                    "boundary": "AB_005_NO_FALSE_POSITIVE_GAMING",
                    "detail": "; ".join(fb_check["reasons"]),
                })

        return {
            "pass": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
            "blocked": len(violations) > 0,
            "force_switch": force_switch,
        }

    def get_boundary_report(self) -> List[Dict]:
        """返回当前所有边界规则的报告"""
        return [
            {
                "id": b["id"],
                "name": b["name"],
                "domain": b["domain"],
                "kind": b["kind"],
                "thresholds": b["thresholds"],
                "action": b["action"],
            }
            for b in ARCH_BOUNDARIES
        ]


# ============================================================
# 完整性校验
# ============================================================

def verify_boundary_integrity() -> Dict:
    """校验架构边界完整性（部署时调用）

    检查内容：
    1. 本文件未被篡改（MD5校验）
    2. 所有绝对边界规则已加载
    3. 检测器实例化正常
    """
    md5 = hashlib.md5(open(__file__, "rb").read()).hexdigest()

    errors = []
    for b in ARCH_BOUNDARIES:
        if b["kind"] == "absolute":
            if "thresholds" not in b or not b["thresholds"]:
                errors.append(f"边界 {b['id']} 缺少阈值")

    # 实例化测试
    try:
        _engine = MetaRuleEngine()
        _detectors_ok = all([
            hasattr(_engine, "dependency"),
            hasattr(_engine, "narcosis"),
            hasattr(_engine, "avoidance"),
            hasattr(_engine, "feedback_checker"),
        ])
    except Exception as e:
        _detectors_ok = False
        errors.append(f"实例化失败: {e}")

    # Meta-meta 审计: MD5锚定
    _meta = {}
    try:
        from importlib import import_module
        _mma = import_module('meta_meta_audit')
        _mm_check = _mma.check_md5_drift()
        _meta['md5_status'] = _mm_check.get('status', 'unknown')
        _meta['drift_count'] = _mm_check.get('drift_count', 0)
        if _mm_check.get('status') == 'drifted':
            errors.append(f"MD5 drifted: {_mm_check.get('note', '')}")
    except ImportError:
        _meta['md5_status'] = 'no_module'
    except Exception as e_meta:
        _meta['md5_status'] = 'error'

    return {
        "version": ARCH_BOUNDARY_VERSION,
        "md5": md5,
        "boundary_count": len(ARCH_BOUNDARIES),
        "absolute_count": len([b for b in ARCH_BOUNDARIES if b["kind"] == "absolute"]),
        "soft_count": len([b for b in ARCH_BOUNDARIES if b["kind"] == "soft"]),
        "detectors_ok": _detectors_ok,
        "meta_meta": _meta,
        "errors": errors,
        "status": "INTACT" if not errors else "COMPROMISED",
        "checked_at": time.time(),
    }


if __name__ == "__main__":
    import sys
    # 修复 Windows GBK 编码问题
    if sys.stdout.encoding and sys.stdout.encoding.lower() in ('gbk', 'gb2312', 'gb18030'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 60)
    print("  arch_boundary.py -- Architecture Boundary Integrity Check")
    print("=" * 60)

    integrity = verify_boundary_integrity()
    print(f"\nVersion: {integrity['version']}")
    print(f"MD5: {integrity['md5']}")
    print(f"Rules: {integrity['boundary_count']} (abs {integrity['absolute_count']}, soft {integrity['soft_count']})")
    print(f"Detectors: {'OK' if integrity['detectors_ok'] else 'FAIL'}")
    print(f"Status: {integrity['status']}")

    if integrity["errors"]:
        print(f"\nErrors:")
        for e in integrity["errors"]:
            print(f"  [X] {e}")

    print(f"\nBoundary Rules:")
    report = MetaRuleEngine().get_boundary_report()
    for r in report:
        kind_tag = "[ABS]" if r["kind"] == "absolute" else "[SOFT]"
        print(f"  {kind_tag} {r['id']}: {r['name']} ({r['domain']})")

    print(f"\nArchitectural boundary integrity check complete.")
