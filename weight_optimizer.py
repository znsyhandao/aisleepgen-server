#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weight_optimizer.py — AEO (Agent Engine Optimization) v1.0

决策权重动态优化系统。让每个决策因素的权重不再硬编码，
而是由A/B实验数据+集群特征动态决定。

核心类:
    WeightOptimizer:
        - get_weights(openid, context) -> dict {rl, pomdp, wm, temporal}
        - set_base_weights(weights_dict) -> None
        - record_outcome(openid, weights_used, action, outcome) -> None
        - optimize() -> dict
        - get_cluster_weights(cluster_id) -> dict

权重结构:
    ['rl', 'pomdp', 'wm', 'temporal']

存储:
    - data/weight_history/base_weights.json
    - data/weight_history/cluster_weights.json
    - data/weight_history/outcome_log.json

集成点:
    - conscious_decider.py: 替换RL_WEIGHT/POMDP_WEIGHT等硬编码
    - population_manager.py: 集群变动时刷新
    - ab_framework.py: A/B实验比较不同权重配比
    - dp_router.py: 记录outcome
    - dynamic_safeguards.py: 差outcome回滚
"""

import json
import os
import time
import logging
import copy
import random
from datetime import datetime
from collections import defaultdict

_wo_log = logging.getLogger('aisleepgen.weight_optimizer')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WEIGHT_DIR = os.path.join(PROJECT_ROOT, 'data', 'weight_history')
BASE_WEIGHTS_PATH = os.path.join(WEIGHT_DIR, 'base_weights.json')
CLUSTER_WEIGHTS_PATH = os.path.join(WEIGHT_DIR, 'cluster_weights.json')
OUTCOME_LOG_PATH = os.path.join(WEIGHT_DIR, 'outcome_log.json')

# 权重键
WEIGHT_KEYS = ['rl', 'pomdp', 'wm', 'temporal']

# 默认权重
DEFAULT_WEIGHTS = {
    'rl': 0.35,
    'pomdp': 0.35,
    'wm': 0.15,
    'temporal': 0.15,
}

# 优化参数
OPTIMIZE_WINDOW = 200          # 每次optimize分析最近多少条outcome
OPTIMIZE_STEP = 0.02           # 单次调整步长
MIN_CLUSTER_SAMPLES = 10       # 集群最少样本量才独立调整
N_NEEDED_FOR_NEW_USER = 5      # 新用户阈值（<5观测视为新用户）

# 上下文微调系数
HIGH_UNCERTAINTY_TEMPORAL_BOOST = 0.05   # 高不确定→temporal+5%
LOW_UNCERTAINTY_RL_BOOST = 0.05         # 低不确定→rl+5%
NEW_USER_WM_BOOST = 0.10                # 新用户→wm+10%
WORSENING_POMDP_BOOST = 0.10            # 恶化中→pomdp+10%


# ==================== 工具函数 ====================

def _ensure_dirs():
    """确保存储目录存在"""
    os.makedirs(WEIGHT_DIR, exist_ok=True)


def _normalize(weights_dict):
    """归一化权重，确保和为1.0"""
    total = sum(weights_dict.get(k, 0.0) for k in WEIGHT_KEYS)
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    result = {}
    for k in WEIGHT_KEYS:
        result[k] = round(weights_dict.get(k, 0.0) / total, 4)
    # 浮点误差修正
    diff = 1.0 - sum(result.values())
    if abs(diff) > 0.0001:
        result[WEIGHT_KEYS[-1]] = round(result.get(WEIGHT_KEYS[-1], 0.0) + diff, 4)
    return result


def _clamp_weights(weights_dict):
    """钳制权重到合理范围 [0.05, 0.8]"""
    result = {}
    for k in WEIGHT_KEYS:
        result[k] = max(0.05, min(0.8, weights_dict.get(k, DEFAULT_WEIGHTS[k])))
    return _normalize(result)


def _redistribute_reduction(weights_dict, boosted_key, delta):
    """从一个boosted key增加delta，从其他所有键等比例抽调"""
    other_keys = [k for k in WEIGHT_KEYS if k != boosted_key]
    total_other = sum(weights_dict.get(k, 0) for k in other_keys)
    if total_other <= 0:
        return
    for k in other_keys:
        proportion = weights_dict.get(k, 0) / total_other if total_other > 0 else 0
        weights_dict[k] = weights_dict.get(k, 0) - delta * proportion
        # 保证不低于最小阈值
        if weights_dict[k] < 0.05:
            weights_dict[k] = 0.05


# ==================== 核心类 ====================

class WeightOptimizer:
    """决策权重动态优化器

    管理全局基准权重和集群特异权重，支持上下文微调。

    用法:
        wo = WeightOptimizer()
        weights = wo.get_weights("user_openid", context)
        wo.record_outcome("user_openid", weights, "push_now", 0.8)
        wo.optimize()  # 定期调用
    """

    def __init__(self):
        _ensure_dirs()
        self._base_weights = None
        self._cluster_weights = None
        self._outcome_log = None
        self._last_load = 0
        self._lock = None
        try:
            import threading
            self._lock = threading.Lock()
        except ImportError:
            pass

    # ==================== IO: 加载/保存 ====================

    def _load_base_weights(self, force=False):
        """加载全局基准权重"""
        now = time.time()
        if self._base_weights is not None and not force and now - self._last_load < 60:
            return self._base_weights
        try:
            if os.path.exists(BASE_WEIGHTS_PATH):
                with open(BASE_WEIGHTS_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                weights = {}
                for k in WEIGHT_KEYS:
                    weights[k] = float(data.get(k, DEFAULT_WEIGHTS[k]))
                self._base_weights = _normalize(weights)
            else:
                self._base_weights = dict(DEFAULT_WEIGHTS)
                self._save_base_weights()
        except Exception as e:
            _wo_log.warning('[WeightOpt] Load base weights error: %s', e)
            self._base_weights = dict(DEFAULT_WEIGHTS)
        self._last_load = now
        return self._base_weights

    def _save_base_weights(self):
        """保存全局基准权重"""
        if self._base_weights is None:
            return
        try:
            data = dict(self._base_weights)
            data['_updated_at'] = datetime.now().isoformat()
            with open(BASE_WEIGHTS_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _wo_log.warning('[WeightOpt] Save base weights error: %s', e)

    def _load_cluster_weights(self, force=False):
        """加载集群特异权重"""
        if self._cluster_weights is not None and not force:
            return self._cluster_weights
        try:
            if os.path.exists(CLUSTER_WEIGHTS_PATH):
                with open(CLUSTER_WEIGHTS_PATH, 'r', encoding='utf-8') as f:
                    self._cluster_weights = json.load(f)
            else:
                self._cluster_weights = {}
                self._save_cluster_weights()
        except Exception as e:
            _wo_log.warning('[WeightOpt] Load cluster weights error: %s', e)
            self._cluster_weights = {}
        return self._cluster_weights

    def _save_cluster_weights(self):
        """保存集群特异权重"""
        if self._cluster_weights is None:
            return
        try:
            data = {
                'clusters': self._cluster_weights,
                '_updated_at': datetime.now().isoformat(),
            }
            with open(CLUSTER_WEIGHTS_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _wo_log.warning('[WeightOpt] Save cluster weights error: %s', e)

    def _load_outcome_log(self):
        """加载outcome日志"""
        try:
            if os.path.exists(OUTCOME_LOG_PATH):
                with open(OUTCOME_LOG_PATH, 'r', encoding='utf-8') as f:
                    self._outcome_log = json.load(f)
            else:
                self._outcome_log = {'outcomes': []}
                self._save_outcome_log()
        except Exception as e:
            _wo_log.warning('[WeightOpt] Load outcome log error: %s', e)
            self._outcome_log = {'outcomes': []}
        return self._outcome_log

    def _save_outcome_log(self):
        """保存outcome日志"""
        if self._outcome_log is None:
            return
        try:
            with open(OUTCOME_LOG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._outcome_log, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _wo_log.warning('[WeightOpt] Save outcome log error: %s', e)

    # ==================== 权重获取 ====================

    def _get_user_cluster_id(self, openid):
        """获取用户所属集群ID (from population_manager)"""
        try:
            from population_manager import get_population_manager
            pm = get_population_manager()
            cluster_id = pm.get_cluster_id(openid)
            if cluster_id is not None:
                return str(cluster_id)
        except Exception:
            pass
        return None

    def _count_user_observations(self, openid):
        """获取用户观测数"""
        try:
            from pomdp_learner import get_engine
            engine = get_engine()
            belief = engine.get_belief(openid)
            if isinstance(belief, dict):
                return belief.get('n', 0) or belief.get('observation_count', 0)
        except Exception:
            pass
        # fallback: 从pomdp_learner获取
        try:
            import pomdp_learner as _pm
            if hasattr(_pm, 'ALearner') and hasattr(_pm.ALearner, '_load_counts'):
                counts = _pm.ALearner._load_counts()
                return counts.get(openid, {}).get('n', 0)
        except Exception:
            pass
        return 0

    def get_weights(self, openid, context=None):
        """获取用户当前的完整权重（含上下文微调）

        Args:
            openid: 用户ID
            context: dict，可包含:
                - 'high_uncertainty': bool, 高不确定状态
                - 'low_uncertainty': bool, 低不确定状态
                - 'worsening': bool, 正在恶化状态

        Returns:
            dict: {rl: float, pomdp: float, wm: float, temporal: float}
        """
        # 1. 从全局基准出发
        base = self._load_base_weights()
        weights = dict(base)

        # 2. 检查集群特异权重
        cluster_id = self._get_user_cluster_id(openid)
        if cluster_id:
            cluster_weights = self._load_cluster_weights()
            if cluster_id in cluster_weights:
                cw = cluster_weights[cluster_id]
                # 检查集群样本量是否足够
                cluster_size = cw.get('cluster_size', 0)
                if cluster_size >= MIN_CLUSTER_SAMPLES:
                    c_weights = cw.get('weights', {})
                    for k in WEIGHT_KEYS:
                        if k in c_weights:
                            weights[k] = float(c_weights[k])

        # 3. 上下文微调
        if context is None:
            context = {}
        adjustments = []

        # 高不确定→temporal+5%
        if context.get('high_uncertainty'):
            # 从其他权重均摊抽调，加到temporal上
            delta = HIGH_UNCERTAINTY_TEMPORAL_BOOST
            weights['temporal'] = weights.get('temporal', DEFAULT_WEIGHTS['temporal']) + delta
            _redistribute_reduction(weights, 'temporal', delta)
            adjustments.append('high_uncertainty: temporal+5%')

        # 低不确定→rl+5%
        if context.get('low_uncertainty'):
            delta = LOW_UNCERTAINTY_RL_BOOST
            weights['rl'] = weights.get('rl', DEFAULT_WEIGHTS['rl']) + delta
            _redistribute_reduction(weights, 'rl', delta)
            adjustments.append('low_uncertainty: rl+5%')

        # 新用户→wm+10%
        n_obs = self._count_user_observations(openid)
        if n_obs < N_NEEDED_FOR_NEW_USER:
            delta = NEW_USER_WM_BOOST
            weights['wm'] = weights.get('wm', DEFAULT_WEIGHTS['wm']) + delta
            _redistribute_reduction(weights, 'wm', delta)
            adjustments.append('new_user: wm+10%')

        # 正在恶化→pomdp+10%
        if context.get('worsening'):
            delta = WORSENING_POMDP_BOOST
            weights['pomdp'] = weights.get('pomdp', DEFAULT_WEIGHTS['pomdp']) + delta
            _redistribute_reduction(weights, 'pomdp', delta)
            adjustments.append('worsening: pomdp+10%')

        # 4. 归一化（防御性，确认和为1.0）
        weights = _normalize(weights)

        if _wo_log.isEnabledFor(logging.DEBUG):
            _wo_log.debug('[WeightOpt] get_weights(%s): %s (adjustments: %s)',
                          openid[:8], {k: round(v, 3) for k, v in weights.items()}, adjustments)

        return weights

    def get_context_from_signals(self, signals):
        """从决策信号中提取上下文标记

        Args:
            signals: conscious_decider 的 signals dict

        Returns:
            dict: {high_uncertainty, low_uncertainty, worsening}
        """
        context = {}

        # 高不确定: pc_high_uncertainty 或 高熵
        pc = signals.get('pc_signal', {})
        kf = signals.get('kf_signal', {})

        high_unc = signals.get('pc_high_uncertainty', False)
        if not high_unc and pc.get('uncertainty', 0) > 0.5:
            high_unc = True
        if not high_unc and kf.get('uncertainty', 10) > 12:
            high_unc = True
        context['high_uncertainty'] = high_unc

        # 低不确定: 低熵 + 低KF不确定性
        low_unc = False
        if pc.get('uncertainty', 0.5) < 0.2 and kf.get('uncertainty', 10) < 5:
            low_unc = True
        context['low_uncertainty'] = low_unc

        # 正在恶化: 时序趋势
        wm = signals.get('wm_signal', {})
        worsening = False
        if wm.get('has_data') and wm.get('trend') == 'down':
            worsening = True
        if kf.get('score_rate', 0) < -2:
            worsening = True
        context['worsening'] = worsening

        # 状态上下文
        try:
            from working_memory import get_working_memory as _gwm
            _wm = _gwm()
            if _wm is not None:
                sc = _wm.state_context(None)  # 全局状态
                if sc == '正在恶化':
                    worsening = True
                    context['worsening'] = True
        except Exception:
            pass

        return context

    def set_base_weights(self, weights_dict):
        """设置全局基准权重

        Args:
            weights_dict: dict，如 {rl: 0.30, pomdp: 0.30, wm: 0.20, temporal: 0.20}
        """
        new_weights = _clamp_weights(weights_dict)
        old = self._load_base_weights()
        self._base_weights = new_weights
        self._save_base_weights()
        _wo_log.info('[WeightOpt] Base weights updated: %s -> %s',
                     {k: round(v, 3) for k, v in old.items()},
                     {k: round(v, 3) for k, v in new_weights.items()})
        return True

    # ==================== 集群权重管理 ====================

    def init_cluster_weights(self, cluster_id, cluster_size=0):
        """为集群初始化权重（新集群创建时调用）

        Args:
            cluster_id: 集群ID (str 或 int)
            cluster_size: 集群当前用户数
        """
        cluster_key = str(cluster_id)
        cw = self._load_cluster_weights()
        base = self._load_base_weights()
        cw[cluster_key] = {
            'weights': dict(base),
            'cluster_size': cluster_size,
            'created_at': datetime.now().isoformat(),
            'last_optimized': None,
            'outcome_count': 0,
            'positive_count': 0,
        }
        self._cluster_weights = cw
        self._save_cluster_weights()
        _wo_log.info('[WeightOpt] Cluster %s weights initialized (size=%d)', cluster_key, cluster_size)

    def refresh_cluster_weights(self):
        """刷新所有集群权重（重聚类后调用）"""
        try:
            from population_manager import get_population_manager
            pm = get_population_manager()
            clusters = pm._load_clusters()
        except Exception:
            _wo_log.warning('[WeightOpt] Cannot refresh cluster weights: population not available')
            return

        cw = self._load_cluster_weights()
        changed = False
        for cidx, cdata in clusters.items():
            cluster_key = str(cidx)
            cluster_size = len(cdata.get('users', []))
            if cluster_key not in cw:
                # 新集群，初始化
                self.init_cluster_weights(cluster_key, cluster_size)
                changed = True
            else:
                # 更新cluster_size
                cw[cluster_key]['cluster_size'] = cluster_size
                changed = True

        # 删除不存在的集群
        existing_keys = {str(cidx) for cidx in clusters.keys()}
        for ck in list(cw.keys()):
            if ck not in existing_keys:
                del cw[ck]
                changed = True

        if changed:
            self._cluster_weights = cw
            self._save_cluster_weights()

    def get_cluster_weights(self, cluster_id):
        """获取某集群的特异权重

        Args:
            cluster_id: 集群ID

        Returns:
            dict: {rl: float, pomdp: float, wm: float, temporal: float}
        """
        cluster_key = str(cluster_id)
        cw = self._load_cluster_weights()
        if cluster_key in cw:
            c_data = cw[cluster_key]
            if c_data.get('cluster_size', 0) >= MIN_CLUSTER_SAMPLES:
                weights = c_data.get('weights', {})
                if weights:
                    return _normalize(weights)
        # fallback: 全局基准
        return dict(self._load_base_weights())

    # ==================== Outcome记录 ====================

    def record_outcome(self, openid, weights_used, action, outcome_value):
        """记录一次决策的权重使用情况和结果

        Args:
            openid: 用户ID
            weights_used: 实际使用的权重dict {rl, pomdp, wm, temporal}
            action: 执行的动作
            outcome_value: 结果值 (0~1), 1=成功
        """
        log = self._load_outcome_log()
        entry = {
            'openid': openid,
            'ts': time.time(),
            'timestamp': datetime.now().isoformat(),
            'weights': {k: round(weights_used.get(k, 0), 4) for k in WEIGHT_KEYS},
            'action': str(action)[:50],
            'outcome': round(float(outcome_value), 4),
        }
        log['outcomes'].append(entry)
        # 限制日志大小
        if len(log['outcomes']) > 5000:
            log['outcomes'] = log['outcomes'][-5000:]
        self._outcome_log = log
        self._save_outcome_log()

        # 同时更新集群统计
        cluster_id = self._get_user_cluster_id(openid)
        if cluster_id:
            cw = self._load_cluster_weights()
            if cluster_id in cw:
                cw[cluster_id]['outcome_count'] = cw[cluster_id].get('outcome_count', 0) + 1
                if outcome_value >= 0.5:
                    cw[cluster_id]['positive_count'] = cw[cluster_id].get('positive_count', 0) + 1
                self._cluster_weights = cw
                self._save_cluster_weights()

        _wo_log.debug('[WeightOpt] record_outcome(%s): action=%s, outcome=%.3f', openid[:8], action, outcome_value)

    # ==================== 优化算法 ====================

    def optimize(self):
        """分析历史数据，调整基准权重

        算法:
            1. 收集最近N个outcome，按使用的权重分组
            2. 对每种权重组合，计算平均成功率
            3. 每个权重：如果当前值效果优于该权重的其他值，小幅上调；否则下调
            4. 确保归一化和为1.0，每个变化不超过±0.02

        Returns:
            dict: 优化报告 {old_weights, new_weights, changes, adjustments}
        """
        log = self._load_outcome_log()
        outcomes = log.get('outcomes', [])

        if len(outcomes) < 10:
            _wo_log.info('[WeightOpt] optimize: too few outcomes (%d), skipping', len(outcomes))
            return {
                'status': 'skipped',
                'reason': f'too_few_outcomes ({len(outcomes)})',
                'old_weights': dict(self._load_base_weights()),
                'new_weights': dict(self._load_base_weights()),
            }

        # 取最近OPTIMIZE_WINDOW条
        recent = outcomes[-OPTIMIZE_WINDOW:]

        # 按权重键值分组分析
        old_weights = self._load_base_weights()
        new_weights = dict(old_weights)
        changes = {}
        adjustments = []

        for key_idx, key in enumerate(WEIGHT_KEYS):
            # 把所有outcome分成两组：当前值对比其他值
            current_val = old_weights.get(key, DEFAULT_WEIGHTS[key])

            # 分析当前值的outcome
            current_outcomes = []
            other_outcomes = []

            for entry in recent:
                w_val = entry.get('weights', {}).get(key, DEFAULT_WEIGHTS[key])
                outcome_val = entry.get('outcome', 0.5)
                # 允许±0.005的容差
                if abs(w_val - current_val) < 0.01:
                    current_outcomes.append(outcome_val)
                else:
                    other_outcomes.append(outcome_val)

            if len(current_outcomes) < 3:
                # 样本不足，跳过此权重
                continue

            avg_current = sum(current_outcomes) / len(current_outcomes) if current_outcomes else 0.5
            avg_other = sum(other_outcomes) / len(other_outcomes) if other_outcomes else 0.5

            if avg_current > avg_other + 0.01:
                # 当前值更好，上调
                delta = OPTIMIZE_STEP
                adjustments.append(f'{key}: up ({avg_current:.3f} > {avg_other:.3f})')
            elif avg_current < avg_other - 0.01:
                # 其他值更好，下调
                delta = -OPTIMIZE_STEP
                adjustments.append(f'{key}: down ({avg_current:.3f} < {avg_other:.3f})')
            else:
                # 差异不大，保持
                delta = 0.0
                adjustments.append(f'{key}: stable ({avg_current:.3f} ≈ {avg_other:.3f})')

            if delta != 0:
                new_weights[key] = current_val + delta
                changes[key] = delta

        # 钳制并归一化
        new_weights = _clamp_weights(new_weights)

        # 确保变化不超过±0.02
        for key in WEIGHT_KEYS:
            delta = new_weights.get(key, 0) - old_weights.get(key, DEFAULT_WEIGHTS[key])
            if abs(delta) > OPTIMIZE_STEP + 0.001:  # 额外0.001容差给归一化
                # 钳制
                if delta > 0:
                    new_weights[key] = old_weights.get(key, DEFAULT_WEIGHTS[key]) + OPTIMIZE_STEP
                else:
                    new_weights[key] = old_weights.get(key, DEFAULT_WEIGHTS[key]) - OPTIMIZE_STEP

        # 重新归一化
        new_weights = _normalize(new_weights)

        # 应用新权重
        self._base_weights = new_weights
        self._save_base_weights()

        report = {
            'status': 'optimized',
            'old_weights': {k: round(old_weights.get(k, 0), 4) for k in WEIGHT_KEYS},
            'new_weights': {k: round(new_weights.get(k, 0), 4) for k in WEIGHT_KEYS},
            'changes': {k: round(v, 4) for k, v in changes.items()},
            'adjustments': adjustments,
            'analyzed_outcomes': len(recent),
            'timestamp': datetime.now().isoformat(),
        }

        _wo_log.info('[WeightOpt] optimize: %s -> %s (changes: %s)',
                     report['old_weights'], report['new_weights'], changes)
        return report

    def optimize_cluster(self, cluster_id):
        """优化单个集群的权重

        Args:
            cluster_id: 集群ID

        Returns:
            dict: 优化报告，或 None（样本不足）
        """
        cluster_key = str(cluster_id)
        cw = self._load_cluster_weights()

        if cluster_key not in cw:
            return None

        cluster_data = cw[cluster_key]
        cluster_size = cluster_data.get('cluster_size', 0)

        if cluster_size < MIN_CLUSTER_SAMPLES:
            _wo_log.info('[WeightOpt] Cluster %s too small (%d < %d), using global weights',
                         cluster_key, cluster_size, MIN_CLUSTER_SAMPLES)
            return {'status': 'skipped', 'reason': f'cluster_too_small ({cluster_size})'}

        # 收集该集群所有outcome
        log = self._load_outcome_log()
        outcomes = log.get('outcomes', [])
        cluster_outcomes = [e for e in outcomes if self._get_user_cluster_id(e['openid']) == cluster_key]

        if len(cluster_outcomes) < 10:
            return {'status': 'skipped', 'reason': f'too_few_outcomes ({len(cluster_outcomes)})'}

        recent = cluster_outcomes[-OPTIMIZE_WINDOW:]
        old_weights = cluster_data.get('weights', dict(self._load_base_weights()))
        new_weights = dict(old_weights)
        changes = {}
        adjustments = []

        for key in WEIGHT_KEYS:
            current_val = old_weights.get(key, DEFAULT_WEIGHTS[key])
            current_outcomes = []
            other_outcomes = []

            for entry in recent:
                w_val = entry.get('weights', {}).get(key, DEFAULT_WEIGHTS[key])
                outcome_val = entry.get('outcome', 0.5)
                if abs(w_val - current_val) < 0.01:
                    current_outcomes.append(outcome_val)
                else:
                    other_outcomes.append(outcome_val)

            if len(current_outcomes) < 3:
                continue

            avg_current = sum(current_outcomes) / len(current_outcomes) if current_outcomes else 0.5
            avg_other = sum(other_outcomes) / len(other_outcomes) if other_outcomes else 0.5

            if avg_current > avg_other + 0.01:
                delta = OPTIMIZE_STEP
                adjustments.append(f'{key}: up ({avg_current:.3f} > {avg_other:.3f})')
            elif avg_current < avg_other - 0.01:
                delta = -OPTIMIZE_STEP
                adjustments.append(f'{key}: down ({avg_current:.3f} < {avg_other:.3f})')
            else:
                delta = 0.0
                adjustments.append(f'{key}: stable ({avg_current:.3f} ≈ {avg_other:.3f})')

            if delta != 0:
                new_weights[key] = current_val + delta
                changes[key] = delta

        new_weights = _clamp_weights(new_weights)

        for key in WEIGHT_KEYS:
            delta = new_weights.get(key, 0) - old_weights.get(key, DEFAULT_WEIGHTS[key])
            if abs(delta) > OPTIMIZE_STEP + 0.001:
                if delta > 0:
                    new_weights[key] = old_weights.get(key, DEFAULT_WEIGHTS[key]) + OPTIMIZE_STEP
                else:
                    new_weights[key] = old_weights.get(key, DEFAULT_WEIGHTS[key]) - OPTIMIZE_STEP

        new_weights = _normalize(new_weights)

        # 更新集群权重
        cw[cluster_key]['weights'] = new_weights
        cw[cluster_key]['last_optimized'] = datetime.now().isoformat()
        self._cluster_weights = cw
        self._save_cluster_weights()

        report = {
            'status': 'optimized',
            'cluster_id': cluster_key,
            'old_weights': {k: round(old_weights.get(k, 0), 4) for k in WEIGHT_KEYS},
            'new_weights': {k: round(new_weights.get(k, 0), 4) for k in WEIGHT_KEYS},
            'changes': {k: round(v, 4) for k, v in changes.items()},
            'adjustments': adjustments,
            'analyzed_outcomes': len(recent),
            'timestamp': datetime.now().isoformat(),
        }
        return report

    # ==================== 重置 ====================

    def reset_to_defaults(self):
        """重置所有权重到默认值"""
        self._base_weights = dict(DEFAULT_WEIGHTS)
        self._save_base_weights()
        self._cluster_weights = {}
        self._save_cluster_weights()
        # 清空outcome日志
        self._outcome_log = {'outcomes': []}
        self._save_outcome_log()
        _wo_log.info('[WeightOpt] All weights reset to defaults')
        return True

    # ==================== 状态查询 ====================

    def get_status(self):
        """获取完整状态报告"""
        base = self._load_base_weights()
        cw = self._load_cluster_weights()
        log = self._load_outcome_log()
        return {
            'base_weights': {k: round(v, 4) for k, v in base.items()},
            'cluster_weights': {
                ck: {
                    'weights': {k: round(v, 4) for k, v in cd.get('weights', {}).items()},
                    'cluster_size': cd.get('cluster_size', 0),
                    'outcome_count': cd.get('outcome_count', 0),
                    'positive_count': cd.get('positive_count', 0),
                    'last_optimized': cd.get('last_optimized'),
                }
                for ck, cd in sorted(cw.items())
            },
            'total_outcomes': len(log.get('outcomes', [])),
            'total_clusters': len(cw),
        }

    def get_outcome_summary(self, n=100):
        """获取最近N条outcome摘要"""
        log = self._load_outcome_log()
        recent = log.get('outcomes', [])[-n:]
        if not recent:
            return {'count': 0}
        avg_outcome = sum(e['outcome'] for e in recent) / len(recent)
        positive_count = sum(1 for e in recent if e['outcome'] >= 0.5)
        return {
            'count': len(recent),
            'avg_outcome': round(avg_outcome, 4),
            'positive_rate': round(positive_count / len(recent), 4),
            'time_range': [
                recent[0]['timestamp'] if recent else None,
                recent[-1]['timestamp'] if recent else None,
            ],
        }


# ==================== 全局实例 ====================

_optimizer_instance = None


def get_weight_optimizer():
    """获取全局WeightOptimizer实例（单例）"""
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = WeightOptimizer()
    return _optimizer_instance


# ==================== 兼容快捷函数 ====================

def get_weights(openid, context=None):
    """快捷获取权重"""
    wo = get_weight_optimizer()
    return wo.get_weights(openid, context)


def record_outcome(openid, weights_used, action, outcome_value):
    """快捷记录outcome"""
    wo = get_weight_optimizer()
    wo.record_outcome(openid, weights_used, action, outcome_value)


def optimize():
    """快捷触发优化"""
    wo = get_weight_optimizer()
    return wo.optimize()


# ==================== 自测 ====================

if __name__ == '__main__':
    import shutil

    logging.basicConfig(level=logging.DEBUG)
    print('=== WeightOptimizer Self-Test ===')

    # 清理旧数据
    if os.path.exists(WEIGHT_DIR):
        shutil.rmtree(WEIGHT_DIR)
    os.makedirs(WEIGHT_DIR, exist_ok=True)

    wo = get_weight_optimizer()

    # Patch: 让 _count_user_observations 对已知测试用户返回 >= N_NEEDED_FOR_NEW_USER
    _orig_count_obs = wo._count_user_observations
    def _patched_count(openid):
        if openid in ('test_user1', 'test_user_seen', '_ba_opt_user'):
            return N_NEEDED_FOR_NEW_USER + 1
        return _orig_count_obs(openid)
    wo._count_user_observations = _patched_count

    # 1. 初始全局权重
    print('\n1. Default base weights:')
    base = wo._load_base_weights()
    print(f'   {base}')
    assert abs(base['rl'] - 0.35) < 0.001, f"rl expected 0.35, got {base['rl']}"
    assert abs(base['pomdp'] - 0.35) < 0.001
    assert abs(base['wm'] - 0.15) < 0.001
    assert abs(base['temporal'] - 0.15) < 0.001
    assert abs(sum(base.values()) - 1.0) < 0.001
    print('   OK: default weights normalized to 1.0')

    # 2. 高不确定→temporal+5%
    print('\n2. High uncertainty context:')
    weights_high = wo.get_weights('test_user1', {'high_uncertainty': True})
    base_weights = wo._load_base_weights()
    print(f'   base:    {base_weights}')
    print(f'   high_unc: {weights_high}')
    temporal_boost = weights_high['temporal'] - base_weights['temporal']
    print(f'   temporal boost: {temporal_boost:.4f} (expected ~0.05)')
    assert temporal_boost > 0.02, f"Temporal boost too small: {temporal_boost}"
    assert abs(sum(weights_high.values()) - 1.0) < 0.01
    print('   OK: temporal boosted and normalized')

    # 3. 低不确定→rl+5%
    print('\n3. Low uncertainty context:')
    weights_low = wo.get_weights('test_user1', {'low_uncertainty': True})
    print(f'   low_unc: {weights_low}')
    rl_boost = weights_low['rl'] - base_weights['rl']
    print(f'   rl boost: {rl_boost:.4f} (expected ~0.05)')
    assert rl_boost > 0.02, f"RL boost too small: {rl_boost}"
    assert abs(sum(weights_low.values()) - 1.0) < 0.01
    print('   OK: rl boosted and normalized')

    # 4. 新用户→wm+10%
    print('\n4. New user context:')
    # 恢复原始计数函数，让新用户真正返回0
    wo._count_user_observations = _orig_count_obs
    # 模拟一个无观测的新用户
    class MockPomdp:
        def get_belief(self, openid):
            return {'n': 0}
    import pomdp_learner as _pm
    _orig_engine = None
    try:
        _orig_engine = _pm._engine
    except AttributeError:
        pass
    _pm._engine = None
    # 用monkey-patch让count返回0
    _orig_count_func = None
    try:
        from pomdp_learner import ALearner
        _orig_count_func = ALearner._load_counts
        def _mock_counts():
            return {'_ba_new_user': {'n': 0}}
        ALearner._load_counts = staticmethod(_mock_counts)
    except Exception:
        pass
    weights_new = wo.get_weights('_ba_new_user', {})
    wm_boost = weights_new['wm'] - base_weights['wm']
    print(f'   base:    {base_weights}')
    print(f'   new_user: {weights_new}')
    print(f'   wm boost: {wm_boost:.4f} (expected ~0.10)')
    assert wm_boost > 0.05, f"WM boost too small: {wm_boost}"
    assert abs(sum(weights_new.values()) - 1.0) < 0.01
    if _orig_count_func:
        try:
            from pomdp_learner import ALearner
            ALearner._load_counts = staticmethod(_orig_count_func)
        except Exception:
            pass
    print('   OK: wm boosted and normalized')

    # 5. 正在恶化→pomdp+10%
    print('\n5. Worsening context:')
    # 重新patch确保不触发new_user（使用已知用户）
    wo._count_user_observations = _patched_count
    weights_worse = wo.get_weights('test_user_seen', {'worsening': True})
    wo._count_user_observations = _orig_count_obs
    pomdp_boost = weights_worse['pomdp'] - base_weights['pomdp']
    print(f'   base:   {base_weights}')
    print(f'   worsen: {weights_worse}')
    print(f'   pomdp boost: {pomdp_boost:.4f} (expected ~0.10)')
    assert pomdp_boost > 0.05, f"POMDP boost too small: {pomdp_boost}"
    assert abs(sum(weights_worse.values()) - 1.0) < 0.01
    print('   OK: pomdp boosted and normalized')

    # 6. optimize() 归一化=1.0
    print('\n6. optimize() normalization:')
    # 添加一些模拟outcome数据
    for i in range(30):
        w = dict(DEFAULT_WEIGHTS) if i % 2 == 0 else {'rl': 0.40, 'pomdp': 0.30, 'wm': 0.15, 'temporal': 0.15}
        wo.record_outcome(f'_ba_opt_user_{i % 5}', w, 'push', 0.7 if i % 3 != 0 else 0.3)
    report = wo.optimize()
    print(f'   old: {report["old_weights"]}')
    print(f'   new: {report["new_weights"]}')
    new_sum = sum(report['new_weights'].values())
    print(f'   sum: {new_sum:.4f}')
    assert abs(new_sum - 1.0) < 0.01, f"Sum not 1.0: {new_sum}"
    print('   OK: normalize after optimize()')

    # 7. 每次权重变化不超过±0.02
    print('\n7. Weight change limit:')
    max_change = max(abs(report['new_weights'][k] - report['old_weights'][k]) for k in WEIGHT_KEYS)
    print(f'   max change: {max_change:.4f} (limit: 0.02)')
    assert max_change <= 0.025, f"max change {max_change} > 0.02"
    print('   OK: changes within limit')

    # 8. 集群权重独立于全局
    print('\n8. Cluster weights independent:')
    wo.init_cluster_weights('test_cluster_1', 15)
    wo.init_cluster_weights('test_cluster_2', 3)  # 小于10
    cw = wo._load_cluster_weights()
    print(f'   cluster_1 weights: {cw.get("test_cluster_1", {}).get("weights", {})}')
    print(f'   cluster_2 weights: {cw.get("test_cluster_2", {}).get("weights", {})}')
    # 修改集群1的权重
    cw['test_cluster_1']['weights'] = {'rl': 0.50, 'pomdp': 0.25, 'wm': 0.15, 'temporal': 0.10}
    wo._cluster_weights = cw
    wo._save_cluster_weights()
    cw1 = wo.get_cluster_weights('test_cluster_1')
    cw2 = wo.get_cluster_weights('test_cluster_2')
    print(f'   cluster_1 get: {cw1}')
    print(f'   cluster_2 get: {cw2}')
    assert abs(cw1['rl'] - 0.50) < 0.02, f"Cluster 1 rl not independent: {cw1['rl']}"
    # 集群2样本不足，应该用全局
    print(f'   cluster_2 rl should be ~0.35 (default), got {cw2["rl"]}')
    assert abs(cw2['rl'] - 0.35) < 0.02, f"Cluster 2 should use global: {cw2['rl']}"
    print('   OK: clusters independent, small cluster uses global')

    # 9. set_base_weights 和归一化
    print('\n9. set_base_weights:')
    wo.set_base_weights({'rl': 0.40, 'pomdp': 0.30, 'wm': 0.20, 'temporal': 0.10})
    new_base = wo._load_base_weights()
    print(f'   {new_base}')
    assert abs(sum(new_base.values()) - 1.0) < 0.01
    print('   OK: set_base_weights with normalization')

    # 10. 重置
    print('\n10. Reset to defaults:')
    wo.reset_to_defaults()
    reset_base = wo._load_base_weights()
    print(f'   {reset_base}')
    assert abs(reset_base['rl'] - 0.35) < 0.001
    assert abs(reset_base['pomdp'] - 0.35) < 0.001
    print('   OK: reset successful')

    print('\nAll WeightOptimizer tests PASS!')