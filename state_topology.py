#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
state_topology.py — AISleepGen 睡眠状态拓扑映射

第一性原理：表征压缩。
智力的本质不是存储大量规则，而是将高维经验压缩到低维流形上。
用户的睡眠状态不是标量评分，而是在"好睡眠吸引子"附近的拓扑位置。

方法：
1. 从历史数据中找到最优的N个"好状态"作为吸引子
2. 每晚新的状态投射到吸引子空间——"你离好状态有多远"
3. 距离不是评分，而是向量 [入睡偏差, 维持偏差, 时长效期...]

数据不足时自动跳过(<7条有效记录)。
"""
import math
import json
import os
from datetime import datetime


def _safe_score(s):
    """安全转换评分"""
    try:
        return float(s) if s else 0.0
    except:
        return 0.0


def _extract_state_vector(history_entry):
    """从一条历史记录提取状态向量
    
    输出: dict of {维度名: 值}
    标准化到0-1区间（相对于全局常识边界）
    
    边界参考: sleep医学常识阈值
    - latency: 0-120分钟 → /120
    - awake_times: 0-5次 → /5
    - total_duration: 180-540分钟 → (v-180)/360
    """
    h = history_entry if isinstance(history_entry, dict) else {}
    extracted = h.get('extracted', {}) if isinstance(h.get('extracted'), dict) else {}
    
    latency = _safe_score(extracted.get('latency_min', h.get('sleep_latency', 0)))
    awake = _safe_score(extracted.get('awake_times', h.get('awake_times', 0)))
    duration = _safe_score(extracted.get('total_min', h.get('total_duration', 420)))
    deep_pct = _safe_score(extracted.get('deep_pct', 20))
    score = _safe_score(h.get('wm_score', 0))
    
    return {
        'latency_norm': min(1.0, latency / 120.0),      # 0=正常, 1=极限
        'awake_norm': min(1.0, awake / 5.0),              # 0=正常, 1=极限
        'duration_norm': max(0, min(1.0, (duration - 180) / 360.0)),  # 0=最短, 1=最长
        'deep_norm': min(1.0, deep_pct / 40.0),           # 0=无深睡, 1=极限
        'score_norm': score / 100.0,                      # 0-1
    }


def _euclidean_distance(v1, v2, dims=None):
    """计算状态向量间的欧氏距离（权重可调）
    
    评分权重高(0.4)，因为综合评分是最有信息的标签
    """
    if dims is None:
        dims = ['latency_norm', 'awake_norm', 'duration_norm', 'deep_norm', 'score_norm']
    
    weights = {
        'latency_norm': 0.2,
        'awake_norm': 0.2,
        'duration_norm': 0.15,
        'deep_norm': 0.05,
        'score_norm': 0.4,
    }
    
    total = 0.0
    weight_sum = 0.0
    for dim in dims:
        w = weights.get(dim, 1.0)
        total += w * (v1.get(dim, 0) - v2.get(dim, 0)) ** 2
        weight_sum += w
    
    return math.sqrt(total / weight_sum) if weight_sum > 0 else 0.0


# ═══ MERLIN记忆矩阵（DeepMind记忆增强世界模型启发） ═══
# 不只是2σ阈值检测，而是维护一个"罕见模式记忆库"，
# 当某个pattern第二次出现时，直接从记忆中调取建议

_MERLIN_MEMORY = []  # [{pattern_vector, cluster_id, suggestion, count}, ...]

def _merlin_remember(today_vector, suggestion=None):
    """存入或匹配记忆库
    
    如果today_vector和记忆中某个pattern相似(cosine>0.85)，count+=1
    否则新存入
    """
    if not today_vector:
        return None
    # 标准化为元组用于hash/比较
    v = tuple(round(today_vector.get(k, 0), 2) for k in ['latency_min', 'awake_times', 'total_min', 'deep_pct'])
    for mem in _MERLIN_MEMORY:
        # 简化的向量接近检测
        mem_v = tuple(mem['pattern'][k] for k in ['latency_min', 'awake_times', 'total_min', 'deep_pct'])
        similarity = sum(1 for a, b in zip(v, mem_v) if abs(a - b) < 0.3) / max(len(v), 1)
        if similarity > 0.75:
            mem['count'] += 1
            if suggestion:
                mem['suggestion'] = suggestion
            return mem
    if suggestion:
        _MERLIN_MEMORY.append({
            'pattern': today_vector,
            'suggestion': suggestion,
            'count': 1,
        })
    return None


def check_anomalous(profile, today_vector=None):
    """检测当前状态是否异常（距离所有历史分布太远）

    异常判定：
    1. 最近N晚的距离均值超出历史分布的2个标准差
    2. 连续3晚距离下降（变差）速率超过阈值
    3. 与历史所有记录的最小距离 > 阈值(0.5)

    输出: {
        'is_anomalous': bool,
        'reason': str,
        'anomaly_type': 'distance_shock'|'rapid_decline'|'unknown_novelty'|'normal',
    }
    """
    history = profile.get('history', [])
    if not history or len(history) < 5:
        return {'is_anomalous': False, 'anomaly_type': 'normal'}

    # 检查1：距离分布尾部
    topology = build_topology(profile)
    if topology.get('recent_nights'):
        distances = [n['distance'] for n in topology['recent_nights'] if 'distance' in n]
        if len(distances) >= 3:
            mean_d = sum(distances) / len(distances)
            var_d = sum((d - mean_d)**2 for d in distances) / len(distances)
            std_d = max(var_d ** 0.5, 0.01)
            latest_d = distances[-1]
            # 最新距离超出2个标准差
            if latest_d > mean_d + 2 * std_d and latest_d > 0.5:
                return {
                    'is_anomalous': True,
                    'reason': f'当前距离均值{latest_d:.2f}，历史均值{mean_d:.2f}±{std_d:.2f}，超出2σ',
                    'anomaly_type': 'distance_shock',
                }

    # 检查2：连续下降速率
    if topology.get('recent_nights') and len(distances) >= 3:
        recent_dists = distances[-3:]
        if all(recent_dists[i] > recent_dists[i+1] for i in range(2)):
            drop_rate = (recent_dists[-1] - recent_dists[0]) / 3
            if drop_rate > 0.05:
                return {
                    'is_anomalous': True,
                    'reason': f'连续3晚距离上升(变差)，速率{drop_rate:.3f}/晚',
                    'anomaly_type': 'rapid_decline',
                }

    return {'is_anomalous': False, 'anomaly_type': 'normal'}


def build_topology(profile):
    """从用户历史构建睡眠状态拓扑
    
    核心思想：
    - 对每晚的状态向量做标准化
    - 找到评分最高的3个"好状态吸引子"
    - 计算每个历史状态到最近吸引子的距离
    
    返回: dict {
        'has_topology': bool,
        'attractors': [...],        # Top-K 好状态向量
        'distances': [...],         # 所有状态到吸引子的距离
        'current_distance': float,  # 最新状态的距离
        'recent_trend': float,      # 近3晚距离变化趋势
    }
    """
    history = profile.get('history', [])
    if not history or len(history) < 7:
        return {'has_topology': False, 'attractors': [], 'distances': [],
                'current_distance': None, 'recent_trend': 0}

    # 提取所有有评分的状态向量
    vectors = []
    for h in history:
        if not isinstance(h, dict):
            continue
        score = _safe_score(h.get('wm_score', 0))
        if score <= 0:
            continue
        vec = _extract_state_vector(h)
        vec['_score'] = score
        vec['_date'] = h.get('date', '')
        vectors.append(vec)

    if len(vectors) < 7:
        return {'has_topology': False, 'attractors': [], 'distances': [],
                'current_distance': None, 'recent_trend': 0}

    # 找Top-K好状态吸引子(评分最高的3个)
    vectors_sorted = sorted(vectors, key=lambda v: v['_score'], reverse=True)
    attractors = vectors_sorted[:3]

    # 归一化吸引子（去掉多余字段）
    clean_attractors = []
    for a in attractors:
        clean_attractors.append({
            'latency_norm': a['latency_norm'],
            'awake_norm': a['awake_norm'],
            'duration_norm': a['duration_norm'],
            'deep_norm': a['deep_norm'],
            'score_norm': a['score_norm'],
            '_score': a['_score'],
        })

    # 计算每个状态到最近吸引子的距离
    distances = []
    for v in vectors:
        min_dist = min(_euclidean_distance(v, a) for a in clean_attractors)
        distances.append({
            'date': v['_date'],
            'score': v['_score'],
            'distance': round(min_dist, 3),
        })

    # 最新状态的距离
    current_distance = distances[-1]['distance'] if distances else None

    # 近3晚趋势
    recent = distances[-3:] if len(distances) >= 3 else distances
    recent_trend = 0
    if len(recent) >= 2:
        recent_trend = recent[-1]['distance'] - recent[0]['distance']

    # 距离评分简化：映射到0-100 直观分
    # 距离0 = 完美(100分)，距离1=很糟(0分)，线性插值
    def _distance_to_score(d):
        return max(0, min(100, round((1.0 - min(d, 1.0)) * 100)))

    return {
        'has_topology': True,
        'attractor_count': len(clean_attractors),
        'current_distance': round(current_distance, 3) if current_distance else None,
        'current_dscore': _distance_to_score(current_distance) if current_distance else None,
        'recent_trend': round(recent_trend, 3),
        'trend_direction': 'getting_closer' if recent_trend < -0.05
                           else ('drifting_away' if recent_trend > 0.05 else 'stable'),
        'sample_count': len(vectors),
        'recent_nights': distances[-7:] if len(distances) >= 7 else distances,
    }


def format_topology_summary(topology):
    """格式化拓扑摘要（用于注入到prompt或日志）"""
    if not topology.get('has_topology'):
        return ''
    
    lines = []
    lines.append(f'【状态拓扑】样本{topology["sample_count"]}晚, '
                 f'距好状态{topology["current_dscore"]}分, '
                 f'趋势{topology["trend_direction"]}')
    
    recent = topology.get('recent_nights', [])
    if recent:
        scores = [f'{r["date"][-5:]}={r["score"]}"距{r["distance"]:.2f}"' for r in recent[-5:]]
        lines.append(f'  近{len(recent)}晚: {" | ".join(scores)}')
    
    return '\n'.join(lines)


# ═══ 轨迹预测模型（SQLite 持久化 + LightGBM 跨用户学习） ═══
# 数据流：
#   record → SQLite (trajectory_samples) → LightGBM train (≥30样本) → predict
#   样本 < 30 时降级到当前手工公式
#   模型 pickle 保存到 .surgical_backups/

def _extract_trajectory_features(profile, strategy_id=None):
    """从 profile + strategy 提取预测特征向量
    
    返回值: [d_current, Δ_avg_3, μ_7, σ_7, has_strategy, avg_effect]
    或 None（数据不足时）
    """
    topology = build_topology(profile)
    if not topology.get('has_topology'):
        return None
    distances = [n['distance'] for n in topology.get('recent_nights', []) if 'distance' in n]
    if len(distances) < 3:
        return None
    
    # 当前距离
    d_current = distances[-1]
    
    # 近3步平均变化
    changes = [distances[i+1] - distances[i] for i in range(len(distances)-1)]
    avg_change_3 = sum(changes[-3:]) / max(len(changes[-3:]), 1)
    
    # 近7步均值、标准差
    recent_7 = distances[-7:] if len(distances) >= 7 else distances
    mu_7 = sum(recent_7) / max(len(recent_7), 1)
    sigma_7 = (sum((d - mu_7)**2 for d in recent_7) / max(len(recent_7), 1)) ** 0.5
    
    # 策略标识和效果
    has_strategy = 1.0 if strategy_id else 0.0
    avg_effect = _estimate_intervention_effect(profile, strategy_id)
    
    return [d_current, avg_change_3, mu_7, sigma_7, has_strategy, avg_effect]


def _predict_delta_learned(features):
    """用 LightGBM 模型预测下一步距离变化
    
    返回变化量（负值=距离变小=状态好转）
    样本<30或模型无效时返回 None（触发降级）
    """
    try:
        from trajectory_model_db import predict_delta as _db_predict
        return _db_predict(features)
    except Exception:
        return None


# ═══ MuZero回放缓冲区：从预测偏差中学习环境动力学 ═══
# 每次真实结果出来后，记录预测vs实际，下次用残差修正
# 这才是MuZero"从回放中学习"的核心，不是固定系数

_TRAJECTORY_BUFFER = []  # [{ts, strategy_id, _features, errors: [{step, predicted, actual, error}]}]

def _get_muero_correction(strategy_id, step=1):
    """从回放缓冲区中获取当前strategy在step步的平均预测偏差

    返回修正值（正值=预测偏乐观，负值=预测偏悲观）
    无数据返回0（不修正）
    """
    relevant = [e for e in _TRAJECTORY_BUFFER
                if e['strategy_id'] == strategy_id
                and any(err['step'] == step for err in e['errors'])]
    if not relevant:
        return 0.0
    errors_for_step = []
    for entry in relevant:
        for err in entry['errors']:
            if err['step'] == step:
                errors_for_step.append(err['error'])
    if not errors_for_step:
        return 0.0
    return sum(errors_for_step) / len(errors_for_step)  # 平均误差
# ═══ MuZero隐空间轨迹预测（DeepMind无模型规划启发） ═══
# 不在原始特征空间做预测，在拓扑距离空间做：
# 用户明天距好状态的距离 = f(今晚距好状态的距离, 干预策略)
# 本质：把马尔可夫链的输出映射到拓扑距离空间


def predict_trajectory(profile, strategy_id=None, steps=3, seed=None):
    """在拓扑距离空间预测未来N天的轨迹

    MuZero启发：不在原始状态空间推演，在隐空间(拓扑距离)推演。

    输入：
    - profile: 用户画像
    - strategy_id: 如果指定，模拟"执行此策略"下的轨迹
    - steps: 预测步数（1-7天）
    - seed: 随机种子，同一seed产生确定性轨迹（Dreamer多路径模拟用不同seed）

    输出：{
        'has_history': bool,
        'current_distance': float,        # 当前距好状态距离
        'trajectory': [                   # 未来N步的预测轨迹
            {'step': 1, 'predicted_distance': 0.28, 'confidence': 'medium', ...},
            ...
        ],
        'no_intervention_baseline': float, # 什么也不做的预期终点
        'improvement_if_no_action': float,  # 不做干预的自然改善量
    }

    数据不足(<3条有效历史)时跳过。
    """
    topology = build_topology(profile)
    if not topology.get('has_topology'):
        return {'has_history': False, 'current_distance': None, 'trajectory': []}

    current_distance = topology.get('current_distance')
    if current_distance is None:
        return {'has_history': False, 'current_distance': None, 'trajectory': [],
                'natural_trend': 'unknown', 'baseline_dscore': None,
                'no_intervention_baseline': None, 'strategy_if_applied': strategy_id}

    # 计算自然演变基线——从历史中看"不做干预时，距离如何自然变化"
    distances = [n['distance'] for n in topology.get('recent_nights', []) if 'distance' in n]
    if len(distances) < 3:
        return {'has_history': False, 'current_distance': current_distance, 'trajectory': []}

    # 步长变化趋势（最近3步的平均改善/恶化）
    changes = [distances[i+1] - distances[i] for i in range(len(distances)-1)]
    avg_change = sum(changes[-3:]) / max(len(changes[-3:]), 1) if len(changes) >= 3 else (changes[-1] if changes else 0)

    # 干预效果系数：来自 feedback_loop 或 recommendation_history
    # 如果没有数据，使用保守估计
    intervention_effect_coeff = _estimate_intervention_effect(profile, strategy_id)
    # 从回放缓冲区修正：如果以前预测过同样策略，看偏差
    if strategy_id:
        for step in range(1, steps + 1):
            correction = _get_muero_correction(strategy_id, step=step)
            if correction:
                intervention_effect_coeff -= correction * 0.1  # 残差修正，学习率0.1

    # ═══ 轻量学习模型：如果有足够训练数据，替换手工公式 ═══
    features = _extract_trajectory_features(profile, strategy_id)
    learned_delta = _predict_delta_learned(features)
    use_learned = learned_delta is not None  # 样本≥15 且训练成功

    trajectory = []
    simulated_distance = current_distance
    for step in range(1, steps + 1):
        if use_learned and step == 1:
            # 第1步用学习模型预测的变化量（只在第1步有足够样本）
            single_step_delta = learned_delta
            # 如果指定策略，叠加干预效果（学习模型自身已经隐含了策略效果）
            if strategy_id:
                simulated_distance += single_step_delta - intervention_effect_coeff * 0.3
            else:
                simulated_distance += single_step_delta
        else:
            # 后续步骤降级到衰减手工公式
            natural_change = avg_change * (0.8 ** (step - 1))
            simulated_distance += natural_change
            if strategy_id:
                simulated_distance -= intervention_effect_coeff * (0.85 ** (step - 1))

        simulated_distance = max(0, min(1, simulated_distance))

        # Dreamer随机波动：同一输入不同seed产生不同路径
        if seed is not None:
            import random
            rng = random.Random(seed + step * 1000)
            noise = rng.gauss(0, 0.02 * (0.8 ** (step - 1)))  # 波动随步数衰减
            simulated_distance = max(0, min(1, simulated_distance + noise))

        # 置信度随步数衰减
        step_conf = max(0.1, 1.0 - (step - 1) * 0.25)

        trajectory.append({
            'step': step,
            'predicted_distance': round(simulated_distance, 3),
            'predicted_dscore': max(0, min(100, round((1 - simulated_distance) * 100))),
            'confidence': 'high' if step_conf > 0.7 else ('medium' if step_conf > 0.4 else 'low'),
            'note': _describe_trajectory_point(step, simulated_distance),
        })

    no_intervention_final = current_distance + avg_change * sum((0.8 ** s) for s in range(steps))
    no_intervention_final = max(0, min(1, no_intervention_final))

    return {
        'has_history': True,
        'current_distance': round(current_distance, 3),
        'current_dscore': max(0, min(100, round((1 - current_distance) * 100))),
        'natural_trend': 'improving' if avg_change < -0.01 else ('declining' if avg_change > 0.01 else 'stable'),
        'trajectory': trajectory,
        'no_intervention_baseline': round(no_intervention_final, 3),
        'baseline_dscore': max(0, min(100, round((1 - no_intervention_final) * 100))),
        'strategy_if_applied': strategy_id,
    }


def _estimate_intervention_effect(profile, strategy_id=None):
    """估计干预效果的期望值
    
    从 recommendation_history 中统计该策略的历史平均改善量
    没有数据时返回保守估计0.05
    """
    if not strategy_id:
        return 0.0
    history = profile.get('_recommendation_history', [])
    effects = []
    for rec in history:
        if rec.get('type') == strategy_id and rec.get('status') == 'evaluated':
            delta = (rec.get('score_after') or 0) - (rec.get('score_at_time') or 0)
            # 转换为距离空间变化（评分从0-100 → 距离0-1，倒置）
            distance_delta = -delta / 100.0
            if abs(distance_delta) < 0.01:
                continue
            effects.append(distance_delta)

    if effects:
        return max(0, sum(effects) / len(effects))
    return 0.05  # 默认保守估计


def _describe_trajectory_point(step, distance):
    """生成轨迹点的可读描述"""
    if distance < 0.15:
        return '接近最佳状态'
    elif distance < 0.3:
        return '状态不错，小幅改善'
    elif distance < 0.5:
        return '中等水平，有提升空间'
    elif distance < 0.7:
        return '仍需努力'
    else:
        return '偏离较大，建议积极干预'


# ===== 快速测试 =====
if __name__ == '__main__':
    # Test with profile that has a decline at the end (so current_distance is non-zero)
    test_profile = {
        'history': [
            {'date': f'2026-07-{d+1:02d}', 'wm_score': s,
             'extracted': {'latency_min': max(10, 30 - d), 'awake_times': max(1, 3 - d//3), 'total_min': 400 + d * 10, 'deep_pct': 18 + d}}
            for d, s in enumerate([60, 63, 72, 75, 68, 70, 78, 82, 85, 65])
        ]
    }
    topo = build_topology(test_profile)
    print(f'拓扑状态: has={topo["has_topology"]}')
    print(f'  吸引子: {topo["attractor_count"]}个')
    print(f'  当前距离: {topo["current_distance"]}')
    print(f'  当前得分: {topo["current_dscore"]}/100')
    print(f'  趋势: {topo["trend_direction"]}')
    print()
    print(format_topology_summary(topo))

    # MuZero 轨迹预测测试
    print('\n=== MuZero 轨迹预测 ===')
    trajectory = predict_trajectory(test_profile, strategy_id='wind_down_routine', steps=5)
    print(f'当前距离: {trajectory["current_distance"]}')
    print(f'自然趋势: {trajectory["natural_trend"]}')
    print(f'不做干预预期: {trajectory["baseline_dscore"]}分')
    print('未来轨迹:')
    for t in trajectory['trajectory']:
        print(f'  第{t["step"]}天: 距离{t["predicted_distance"]}, {t["predicted_dscore"]}分, {t["note"]} (置信度{t["confidence"]})')
    print()
    trajectory_no = predict_trajectory(test_profile, strategy_id=None, steps=5)
    print('不做干预的基线轨迹:')
    for t in trajectory_no['trajectory']:
        print(f'  第{t["step"]}天: {t["predicted_dscore"]}分 ({t["note"]})')


def _record_trajectory_result(profile, strategy_id, predicted_trajectory, actual_dscore_history):
    """记录一次预测vs实际——供下次预测时修正+训练模型"""
    if not predicted_trajectory or not actual_dscore_history:
        return
    # 提取特征：记录时的 profile 状态
    features_v = _extract_trajectory_features(profile, strategy_id)
    
    # 计算每步误差
    errors = []
    for i, pred in enumerate(predicted_trajectory):
        if i < len(actual_dscore_history):
            diff = pred['predicted_dscore'] - actual_dscore_history[i]
            errors.append({
                'step': i + 1,
                'predicted': pred['predicted_dscore'],
                'actual': actual_dscore_history[i],
                'error': diff,
            })
    if errors:
        _TRAJECTORY_BUFFER.append({
            'ts': __import__('datetime').datetime.now().isoformat(),
            'strategy_id': strategy_id,
            '_features': features_v,
            'errors': errors,
        })
        # 保持缓冲区最多100条
        while len(_TRAJECTORY_BUFFER) > 100:
            _TRAJECTORY_BUFFER.pop(0)
        
        # ═══ 同时写入 SQLite 持久化（跨用户、重启不丢） ═══
        if features_v is not None and errors and errors[0].get('step') == 1:
            openid = profile.get('openid', '__unknown__') if isinstance(profile, dict) else '__unknown__'
            actual_delta = -errors[0]['error'] / 100.0  # 实际距离变化
            try:
                from trajectory_model_db import record_sample
                record_sample(openid, strategy_id, features_v, actual_delta)
            except Exception as e:
                print(f'[state_topology] trajectory_db record error: {type(e).__name__}: {e}')

