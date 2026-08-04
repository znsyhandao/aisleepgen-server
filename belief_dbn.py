"""
belief_dbn.py — 基于动态贝叶斯网络的团灭风险预测模型

数学框架：
  P(annihilation_in_3_rounds | observations)
  
  观测变量（5维）：
    d  — 内稳态偏离度 (0-1)，来自 homeostatic_kernel.attractor_distance
    λ  — Lyapunov 指数 (-1 to 1)，来自 homeostatic_kernel.lyapunov_max
    r  — 韧性半径 (0-1)，来自 homeostatic_kernel.resilience_radius
    h  — AI暗示次数，来自 belief_drift._extract_ai_hints
    s  — 用户种子词数，来自 belief_drift._count_user_seeds

  隐变量：
    C  — 认知渗透程度 (0-1)，团灭的"看不见的原因"

模型结构（2层DBN）：
  时间 t-1:  [d, λ, r, h, s] → C_{t-1}
  时间 t:    [d, λ, r, h, s] → C_t → P(团灭)

  用 C_t-1 更新 C_t 的先验，形成时序依赖。

用法：
  risk = assess_annihilation_risk(profile, current_message, homeostasis_result)
  返回 {'probability': 0.72, 'level': 'high', 'evidence': {...}}
"""

import math
import datetime
from typing import Optional

# ── 先验概率分布（基于安全闸历史数据和临床经验校准） ──

# 权重矩阵 W = [w_d, w_λ, w_r, w_h, w_s]
# 通过5轮校准测试手动调整
_DEFAULT_WEIGHTS = [0.20, 0.15, 0.20, 0.25, 0.20]

# 每个观测变量的"危险阈值"（超过阈值才贡献风险）
_THRESHOLDS = {
    'd': 0.20,   # 偏离 > 0.2
    'lam': 0.05, # Lyapunov > 0.05（正发散）
    'r': 0.25,   # 韧性 < 0.25
    'h': 2,      # AI暗示 >= 3次（注意：种子数直接计数，>= threshold 触发）
    's': 1,      # 用户种子词 >= 2
}

# 时序衰减因子（过去1轮的权重 = 1.0，过去N轮的权重 = alpha^N）
_ALPHA = 0.4

# 风险等级阈值
_RISK_THRESHOLDS = {
    'low': (0.0, 0.25),
    'watch': (0.25, 0.45),
    'elevated': (0.45, 0.65),
    'high': (0.65, 0.85),
    'critical': (0.85, 1.01),
}


def _extract_observations(
    profile: dict,
    current_message: str,
    homeostasis_result: dict
) -> dict:
    """从多个数据源提取当前轮的观测值"""
    obs = {
        'd': homeostasis_result.get('distance', 0.0),
        'lam': homeostasis_result.get('lyapunov_exponent', -0.1),
        'r': homeostasis_result.get('resilience_radius', 0.3),
        'h': 0,
        's': 0,
    }

    try:
        from belief_drift import _extract_ai_hints, _count_user_seeds
        history = profile.get('history', [])
        hints = _extract_ai_hints(history)
        total_hints = sum(h.get('count', 0) for h in hints.values())
        obs['h'] = total_hints

        # 找最危险的概念来算种子词
        worst_concept = max(hints, key=lambda k: hints[k]['count']) if hints else None
        if worst_concept:
            obs['s'] = _count_user_seeds(current_message, worst_concept)
    except Exception:
        pass

    return obs


def _compute_evidence_strength_v2(obs: dict) -> float:
    """
    计算单轮的证据强度 E ∈ [0, 1]。
    
    E = Σ w_i * sigmoid(k*(x_i - θ_i))
    
    其中 sigmoid 保证了阈值附近的平滑过渡：
      x << θ → sigmoid < 0 → 不贡献
      x ≈ θ → sigmoid ≈ 0.5 → 部分贡献
      x >> θ → sigmoid ≈ 1 → 全贡献
    """
    weights = _DEFAULT_WEIGHTS

    # 归一化的5个特征值
    def _sigmoid(z):
        return 1.0 / (1.0 + math.exp(-z))

    features = []

    # d: 偏离度，阈值 0.20
    d = obs.get('d', 0)
    features.append(_sigmoid(8.0 * (d - _THRESHOLDS['d'])))

    # λ: Lyapunov，高于阈值才危险
    lam = obs.get('lam', 0)
    features.append(_sigmoid(8.0 * (lam - _THRESHOLDS['lam'])))

    # r: 1-r（韧性越低越危险），阈值 0.25
    r = obs.get('r', 0.3)
    features.append(_sigmoid(8.0 * ((1 - r) - (1 - _THRESHOLDS['r']))))

    # h: AI暗示次数，阈值 3
    h = obs.get('h', 0)
    features.append(min(1.0, h / max(_THRESHOLDS['h'], 1) * 0.5))

    # s: 用户种子词，阈值 2
    s = obs.get('s', 0)
    features.append(min(1.0, s / max(_THRESHOLDS['s'], 1) * 0.5))

    evidence = sum(w * f for w, f in zip(weights, features))
    return min(1.0, max(0.0, evidence))


def _compute_temporal_posterior(
    profile: dict,
    obs: dict
) -> float:
    """
    时序后验概率 P(C_t | E_1..E_t)。
    
    形式：P(C_t) = (1 - α) * E_t + α * P(C_{t-1})
    
    这是简化的一阶马尔可夫链，但捕捉了时序依赖。
    """
    E_t = _compute_evidence_strength_v2(obs)

    # 从历史中读取上一次的 C_{t-1}
    _history = profile.get('history', [])
    prev_C = 0.0
    if _history:
        # 检查前一条记录是否有信念偏移状态
        last_h = _history[-1] if isinstance(_history[-1], dict) else {}
        prev_C = last_h.get('_belief_C', 0.0)

    # 一阶马尔可夫更新
    C_t = (1 - _ALPHA) * E_t + _ALPHA * prev_C
    return min(1.0, max(0.0, C_t))


def _calculate_decay_velocity(profile: dict, homeostatic_state: dict) -> float:
    """
    计算衰减速度 v（额外风险因子）。
    
    如果用户的评分在加速下降，即使当前证据不强，也需要提高警惕。
    v = (Δscore_t - Δscore_{t-1}) / max(1, score_{t-1})
    
    正值 → 加速下降 → 增加风险
    """
    history = profile.get('history', [])
    if len(history) < 3:
        return 0.0

    scores = [
        h.get('wm_score', 0) for h in history[-4:]
        if isinstance(h, dict) and h.get('wm_score', 0) > 0
    ]

    if len(scores) < 2:
        return 0.0

    # 最近两次的下降量
    d1 = scores[-2] - scores[-1]  # 最后一次下降
    d0 = scores[-3] - scores[-2] if len(scores) >= 3 else d1  # 前一次下降
    
    v = (d1 - d0) / max(scores[-1], 10)
    return max(-0.2, min(0.3, v))  # 限制范围 [-0.2, 0.3]


def assess_annihilation_risk(
    profile: dict,
    current_message: str = '',
    homeostasis_result: dict = None
) -> dict:
    """
    团灭风险评估主入口。
    
    返回：
    {
        'probability': float,   # 0-1 团灭概率
        'level': str,           # low/watch/elevated/high/critical
        'evidence': float,      # 当前证据强度
        'posterior': float,     # 时序后验
        'velocity': float,      # 衰减加速度
        'observations': dict,   # 原始观测值
        'recommended_action': str,  # 建议动作
        'details': str,         # 人类可读的解释
    }
    """
    if homeostasis_result is None:
        homeostasis_result = {}

    # 步骤1：提取观测值
    obs = _extract_observations(profile, current_message, homeostasis_result)

    # 步骤2：计算证据强度 E
    E = _compute_evidence_strength_v2(obs)

    # 步骤3：时序后验 P
    P = _compute_temporal_posterior(profile, obs)

    # 步骤4：衰减速度 v
    v = _calculate_decay_velocity(profile, homeostasis_result)

    # 步骤5：最终概率 = 时序后验 + 速度修正
    prob = min(1.0, max(0.0, P + v * 0.3))

    # 步骤6：等级映射
    level = 'low'
    for lvl, (lo, hi) in _RISK_THRESHOLDS.items():
        if lo <= prob < hi:
            level = lvl
            break
    if prob >= 0.85:
        level = 'critical'

    # 步骤7：建议动作
    action_map = {
        'low': '无额外动作',
        'watch': '加强内稳态监控',
        'elevated': '建议注入信念偏移告警',
        'high': '强制信念偏移告警 + 安全闸满负荷',
        'critical': '所有外部输入降级 + 纯共情模式',
    }
    action = action_map.get(level, 'unknown')

    # 步骤8：人类可读解释
    details = f'团灭风险: {prob*100:.0f}% ({level})'
    if prob > 0.45:
        details += f'\n主因: 证据强度{E:.2f}'
        if obs['h'] >= _THRESHOLDS['h']:
            details += f' + AI暗示{obs["h"]}次'
        if obs['s'] >= _THRESHOLDS['s']:
            details += f' + 用户种子{obs["s"]}个'
        if v > 0.05:
            details += f' + 加速崩盘(v={v:.2f})'

    return {
        'probability': round(prob, 4),
        'level': level,
        'evidence': round(E, 4),
        'posterior': round(P, 4),
        'velocity': round(v, 4),
        'observations': obs,
        'recommended_action': action,
        'details': details,
    }


def update_belief_C(profile: dict, current_message: str, homeostasis_result: dict) -> float:
    """
    更新 profile 中本条记录的 _belief_C（隐状态）。
    供 dp_router.handle_chat 在保存修改过的 profile 前调用。
    """
    obs = _extract_observations(profile, current_message, homeostasis_result)
    C_t = _compute_temporal_posterior(profile, obs)
    return round(C_t, 4)


# ============================================================
# v3: 在线学习
# 每轮 chat 后用实际后果更新权重 w。3行核心数学。
# ============================================================

import os
import json

_DATA_DIR = os.path.join(os.path.dirname(__file__) or '.', 'data')
_WEIGHT_PATH = os.path.join(_DATA_DIR, 'dbn_weights.json')

_DBN_WEIGHTS = list(_DEFAULT_WEIGHTS)
_DBN_ALPHA = _ALPHA
_DBN_H = 0.3

# ── Adagrad 累积梯度 ──
_ADA_EPS = 1e-8  # 防除零
_ADA_ETA = 0.1   # base lr
_ADA_G = [0.0, 0.0, 0.0, 0.0, 0.0]  # 各权重累积平方梯度
_ADA_AG = 0.0    # alpha 累积平方梯度


def _load_weights():
    global _DBN_WEIGHTS, _DBN_ALPHA, _DBN_H
    try:
        if os.path.exists(_WEIGHT_PATH):
            with open(_WEIGHT_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _DBN_WEIGHTS = data.get('weights', list(_DEFAULT_WEIGHTS))
        if 'adagrad_g' in data:
            _ADA_G = data['adagrad_g']
            _ADA_AG = data.get('adagrad_alpha_g', 0.0)
            _DBN_ALPHA = data.get('alpha', _ALPHA)
            _DBN_H = data.get('h', 0.3)
    except Exception:
        pass


def _save_weights():
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_WEIGHT_PATH, 'w', encoding='utf-8') as f:
            json.dump({
                'weights': _DBN_WEIGHTS,
                'alpha': _DBN_ALPHA,
                'h': _DBN_H,
                'updated_at': datetime.datetime.now().isoformat(),
            }, f)
    except Exception:
        pass


_load_weights()


def _compute_evidence_strength_v2(obs):
    def _sigmoid(z):
        return 1.0 / (1.0 + math.exp(-z))
    features = []
    d = obs.get('d', 0)
    features.append(_sigmoid(8.0 * (d - _THRESHOLDS['d'])))
    lam = obs.get('lam', 0)
    features.append(_sigmoid(8.0 * (lam - _THRESHOLDS['lam'])))
    r = obs.get('r', 0.3)
    features.append(_sigmoid(8.0 * ((1 - r) - (1 - _THRESHOLDS['r']))))
    h = obs.get('h', 0)
    features.append(min(1.0, h / max(_THRESHOLDS['h'], 1) * 0.5))
    s = obs.get('s', 0)
    features.append(min(1.0, s / max(_THRESHOLDS['s'], 1) * 0.5))
    return sum(w * f for w, f in zip(_DBN_WEIGHTS, features))



def online_learn(profile, current_message='', homeostasis_result=None, actual_outcome=None):
    """在线学习（Adagrad）。
    
    使用 Adagrad 自适应学习率更新 DBN 权重和 alpha。
    """
    global _DBN_WEIGHTS, _DBN_ALPHA, _ADA_G, _ADA_AG, _ADA_ETA
    
    wm_score = getattr(profile, 'get', lambda k, d: d)('wm_score', 50) or 50
    if isinstance(wm_score, (list, dict)):
        wm_score = 50
    wm_score = float(wm_score)
    
    from .homeostatic_kernel import evaluate as _hke
    hs_result = _hke(profile)
    
    obs = _extract_observations(profile, current_message, hs_result)
    E = _compute_evidence_strength_v2(obs)
    predicted = _sigmoid(E, _DBN_H)
    
    error = predicted - actual_outcome
    
    # Adagrad 权重更新（每个权重独立学习率）
    obs_keys = ['d', 'lam', 'r', 'h', 's']
    features = [
        _sigmoid(8.0 * (obs.get('d', 0) - _THRESHOLDS['d'])),
        _sigmoid(8.0 * (obs.get('lam', 0) - _THRESHOLDS['lam'])),
        _sigmoid(8.0 * ((1 - obs.get('r', 0.3)) - (1 - _THRESHOLDS['r']))),
        min(1.0, obs.get('h', 0) / max(_THRESHOLDS['h'], 1) * 0.5),
        min(1.0, obs.get('s', 0) / max(_THRESHOLDS['s'], 1) * 0.5),
    ]
    
    for i in range(len(_DBN_WEIGHTS)):
        g_t = error * features[i]
        _ADA_G[i] += g_t ** 2
        sum_g = sum(_ADA_G)
        eta_i = _ADA_ETA / (sum_g ** 0.5 + _ADA_EPS) if sum_g > 0 else _ADA_ETA
        _DBN_WEIGHTS[i] -= eta_i * g_t
    
    total = sum(_DBN_WEIGHTS)
    if total > 0:
        _DBN_WEIGHTS = [w / total for w in _DBN_WEIGHTS]
    
    # Adagrad alpha
    alpha_g = error * 0.1
    _ADA_AG += alpha_g ** 2
    eta_a = _ADA_ETA / (_ADA_AG ** 0.5 + _ADA_EPS)
    _DBN_ALPHA = max(0.1, min(0.8, _DBN_ALPHA + eta_a * alpha_g))
    
    _save_dbn_weights()
    
    return {
        'predicted': round(predicted, 4),
        'error': round(error, 4),
        'weights': [round(w, 4) for w in _DBN_WEIGHTS],
        'alpha': round(_DBN_ALPHA, 4),
        'features': [round(f, 4) for f in features],
        'adagrad_g_sum': round(sum(_ADA_G), 4),
    }


def get_learning_stats():
    return {
        'weights': [round(w, 4) for w in _DBN_WEIGHTS],
        'alpha': round(_DBN_ALPHA, 4),
        'h': _DBN_H,
        'thresholds': _THRESHOLDS,
        'weight_path': _WEIGHT_PATH,
    }
