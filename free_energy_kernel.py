# -*- coding: utf-8 -*-
"""
自由能内核 — 变分自由能 (VFE) 计算
用于决定是否干预：如果当前状态自由能低（预测误差小 + 模型复杂度低），算法保持安静。
如果自由能高太高，且干预能预期降低自由能，则输出建议。

参考：神经科学中 Friston 的自由能原理，
    数哲灵感周刊第3期「自由能原理 → 主动探索强化学习」

扩展：因果轨迹引擎 — 将VFE异常解释为因果链
    来源: AI战略内参第10期「Agents-K1: 知识编排」
"""

import math
import json
import time
from typing import Dict, Optional

DEFAULT_ENTROPY_THRESHOLD = 0.8
DEFAULT_PREDICTION_ERROR_WEIGHT = 1.0
DEFAULT_COMPLEXITY_WEIGHT = 0.1
DEFAULT_SILENCE_THRESHOLD = 0.3
DEFAULT_SILENCE_DECAY_ALPHA = 0.8


def compute_belief_entropy(belief_distribution):
    if not belief_distribution:
        return 0.0
    total = sum(belief_distribution.values())
    if total <= 0:
        return 0.0
    entropy = 0.0
    for v in belief_distribution.values():
        p = v / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def compute_prediction_error(hr, stress, predicted_hr=70.0, predicted_stress=3):
    hr_error = 0.0
    stress_error = 0.0
    if hr is not None:
        hr_error = min(1.0, abs(hr - predicted_hr) / 100.0)
    if stress is not None:
        stress_error = min(1.0, abs(stress - predicted_stress) / 10.0)
    if hr is None and stress is None:
        return 0.5
    count = (1 if hr is not None else 0) + (1 if stress is not None else 0)
    return (hr_error + stress_error) / count


def compute_complexity_score(session_history_len, max_history=100):
    return min(1.0, session_history_len / max_history)


def compute_vfe(belief_entropy, prediction_error, complexity,
                alpha=1.0, beta=0.1):
    return alpha * prediction_error + beta * complexity - belief_entropy


def estimate_silence_reward(current_vfe, predicted_intervention_vfe, entropy):
    base_silence = current_vfe - predicted_intervention_vfe
    entropy_penalty = max(0, entropy - DEFAULT_ENTROPY_THRESHOLD) * 0.5
    return base_silence - entropy_penalty


class FreeEnergyTracker:
    def __init__(self, user_id, silence_threshold=0.3):
        self.user_id = user_id
        self.silence_threshold = silence_threshold
        self.history = []
        self._silence_smoothed = None
        self._last_vfe = None

    def evaluate(self, state, session_history_len=0, predicted_intervention_vfe=None):
        hr = state.get('heart_rate')
        stress = state.get('stress_level')
        belief_dist = state.get('belief_distribution', {})

        entropy = compute_belief_entropy(belief_dist)
        pred_error = compute_prediction_error(hr, stress)
        complexity = compute_complexity_score(session_history_len)
        vfe = compute_vfe(entropy, pred_error, complexity)

        if predicted_intervention_vfe is None:
            predicted_intervention_vfe = vfe * 0.8

        silence_score = estimate_silence_reward(vfe, predicted_intervention_vfe, entropy)

        if self._silence_smoothed is None:
            self._silence_smoothed = 1.0 if (silence_score > 0 and vfe < self.silence_threshold) else 0.0
        else:
            self._silence_smoothed = (
                DEFAULT_SILENCE_DECAY_ALPHA * self._silence_smoothed
                + (1 - DEFAULT_SILENCE_DECAY_ALPHA) * (1.0 if silence_score > 0 else 0.0)
            )

        should_be_silent = self._silence_smoothed > 0.5 and vfe < self.silence_threshold

        record = {
            'ts': time.time(),
            'vfe': round(vfe, 4),
            'entropy': round(entropy, 4),
            'pred_error': round(pred_error, 4),
            'complexity': round(complexity, 4),
            'silence_score': round(silence_score, 4),
            'silence_smoothed': round(self._silence_smoothed, 4),
            'should_be_silent': should_be_silent,
        }
        self.history.append(record)
        if len(self.history) > 200:
            self.history = self.history[-200:]
        self._last_vfe = vfe
        return record

    def get_summary(self):
        if not self.history:
            return {'status': 'no_data'}
        recent = self.history[-10:]
        avg_vfe = sum(r['vfe'] for r in recent) / len(recent)
        silence_ratio = sum(1 for r in recent if r['should_be_silent']) / len(recent)
        return {
            'avg_vfe': round(avg_vfe, 4),
            'silence_ratio': round(silence_ratio, 4),
            'total_entries': len(self.history),
            'last_vfe': round(self.history[-1]['vfe'], 4),
            'last_entropy': round(self.history[-1]['entropy'], 4),
        }


# ===== Fisher 信息度量 — 信息几何扩展 =====

def compute_fisher_metric(t, hr, stress):
    hr_variation = max(0.01, abs(hr - 70.0) / 100.0)
    g_hh = 1.0 / max(hr_variation, 0.01)
    stress_variation = max(0.01, (stress - 3.0) / 10.0)
    g_ss = 1.0 / max(stress_variation, 0.01)
    g_tt = 1.0 + max(0, (t - 36000) / 14400)
    curvature = (g_hh + g_ss) / g_tt
    return {'g_tt': round(g_tt, 4), 'g_hh': round(g_hh, 4),
            'g_ss': round(g_ss, 4), 'curvature': round(curvature, 4)}


def compute_fisher_distance(state_a, state_b):
    d_hr = state_a.get('hr', 70) - state_b.get('hr', 70)
    d_stress = state_a.get('stress', 3) - state_b.get('stress', 3)
    d_t = (state_a.get('t', 0) - state_b.get('t', 0)) / 3600.0
    mid_hr = (state_a.get('hr', 70) + state_b.get('hr', 70)) / 2
    mid_stress = (state_a.get('stress', 3) + state_b.get('stress', 3)) / 2
    mid_t = (state_a.get('t', 0) + state_b.get('t', 0)) / 2
    metric = compute_fisher_metric(mid_t, mid_hr, mid_stress)
    return min(10.0, (
        metric['g_tt'] * d_t ** 2
        + metric['g_hh'] * (d_hr / 40.0) ** 2
        + metric['g_ss'] * (d_stress / 10.0) ** 2
    ) ** 0.5)


class FisherGeodesicPlanner:
    def __init__(self, user_id):
        self.user_id = user_id
        self._history = []

    def plan(self, current_hr, current_stress, target_hr=65.0, target_stress=2.0, max_steps=10):
        current_t = time.time()
        state_a = {'hr': current_hr, 'stress': current_stress, 't': current_t}
        state_b = {'hr': target_hr, 'stress': target_stress, 't': current_t + 3600}
        total_distance = compute_fisher_distance(state_a, state_b)
        if total_distance < 0.01:
            return {'steps': [], 'total_distance': 0.0, 'curvature': 0.0}
        steps = []
        for i in range(max_steps):
            frac = (i + 1) / max_steps
            i_hr = current_hr + (target_hr - current_hr) * frac
            i_stress = current_stress + (target_stress - current_stress) * frac
            i_t = current_t + (3600 * frac)
            metric = compute_fisher_metric(i_t, i_hr, i_stress)
            intensity = 0.3 / max(metric['curvature'], 0.5)
            intensity = max(0.1, min(0.8, intensity))
            steps.append({
                'step': i + 1, 'predicted_hr': round(i_hr, 1),
                'predicted_stress': round(i_stress, 1),
                'g_tt': metric['g_tt'], 'g_hh': metric['g_hh'],
                'g_ss': metric['g_ss'], 'curvature': metric['curvature'],
                'intensity': round(intensity, 4),
            })
        self._history.append({'ts': current_t, 'distance': round(total_distance, 4), 'steps': steps})
        return {
            'steps': steps, 'total_distance': round(total_distance, 4),
            'curvature': round(steps[-1]['curvature'], 4) if steps else 0.0,
            'intensity_profile': [s['intensity'] for s in steps],
        }


# ===== 因果轨迹引擎 — 睡眠因果推理 =====
# 来源: AI战略内参第10期「Agents-K1: 知识编排」

import os as _os
import json as _json

_CAUSAL_GRAPH_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                   'data', 'sleep_causal_graph.json')

def load_causal_graph(path=None):
    """从JSON文件加载睡眠因果知识图谱

    支持外部扩展：任意第三方可写入JSON然后调 load_causal_graph(自定义路径)
    返回 (graph, edges, node_count, edge_count)
    """
    p = path or _CAUSAL_GRAPH_PATH
    with open(p, 'r', encoding='utf-8') as f:
        data = _json.load(f)
    graph = data.get('nodes', {})
    edges = [(e[0], e[1], e[2], e[3]) for e in data.get('edges', [])]
    return graph, edges

def extend_graph(new_nodes: dict = None, new_edges: list = None, save_path=None):
    """扩展因果知识图谱 — 从外部注入新的因果边

    Args:
        new_nodes: {node_key: '中文描述', ...}
        new_edges: [(cause, effect, weight, evidence_type), ...]
        save_path: 保存路径，None则覆盖原文件
    """
    p = save_path or _CAUSAL_GRAPH_PATH
    with open(p, 'r', encoding='utf-8') as f:
        data = _json.load(f)
    if new_nodes:
        data['nodes'].update(new_nodes)
    if new_edges:
        existing_keys = set((e[0], e[1]) for e in data['edges'])
        for e in new_edges:
            if (e[0], e[1]) not in existing_keys:
                data['edges'].append(list(e))
                existing_keys.add((e[0], e[1]))
    data['graph_meta']['node_count'] = len(data['nodes'])
    data['graph_meta']['edge_count'] = len(data['edges'])
    data['graph_meta']['updated'] = '2026-06-14'
    with open(p, 'w', encoding='utf-8') as f:
        _json.dump(data, f, ensure_ascii=False, indent=2)
    return len(data['nodes']), len(data['edges'])

# 默认加载
_SLEEP_CAUSAL_GRAPH, _SLEEP_CAUSAL_EDGES = load_causal_graph()
SLEEP_CAUSAL_GRAPH = _SLEEP_CAUSAL_GRAPH
SLEEP_CAUSAL_EDGES = _SLEEP_CAUSAL_EDGES


def trace_causal_path(inputs):
    active_nodes = {}
    for key, label in SLEEP_CAUSAL_GRAPH.items():
        val = inputs.get(key)
        if val is not None:
            if key == 'hr':
                anomaly = abs(val - 70) / 40.0
            elif key == 'stress':
                anomaly = abs(val - 3) / 7.0
            elif key == 'sleep_latency':
                anomaly = abs(val - 20) / 60.0
            elif key == 'awake_times':
                anomaly = min(1.0, val / 5.0)
            elif key == 'total_sleep':
                anomaly = abs(val - 420) / 240.0
            else:
                anomaly = 0.3
            active_nodes[key] = {'value': val, 'label': label, 'anomaly': min(1.0, anomaly)}

    if not active_nodes:
        return {'chains': [], 'root_cause': 'unknown', 'entropy': 0.0, 'explanation': '暂无数据'}

    # 多跳传播：从用户可观测节点沿因果边传播异常度到推理节点
    node_anomaly = {k: v['anomaly'] for k, v in active_nodes.items()}
    # 建邻接表
    adj_forward = {}  # cause -> [(effect, weight)]
    adj_backward = {}  # effect -> [(cause, weight)]
    for cause, effect, weight, etype in SLEEP_CAUSAL_EDGES:
        if cause not in adj_forward:
            adj_forward[cause] = []
        if effect not in adj_forward:
            adj_forward[effect] = []
        adj_forward[cause].append((effect, weight, etype))
        if effect not in adj_backward:
            adj_backward[effect] = []
        adj_backward[effect].append((cause, weight, etype))

    # BFS：从已知节点传播异常
    visited = set()
    propagation = {}  # node -> {anomaly, path}
    queue = list(active_nodes.keys())
    for n in queue:
        visited.add(n)
    # 正向传播（原因→结果）
    while queue:
        cur = queue.pop(0)
        cur_anomaly = node_anomaly.get(cur, 0)
        for effect, weight, etype in adj_forward.get(cur, []):
            if effect not in visited:
                visited.add(effect)
                prop = cur_anomaly * abs(weight)
                if prop > 0.05:
                    node_anomaly[effect] = min(1.0, prop)
                    propagation[effect] = {'via': cur, 'strength': round(prop, 3), 'etype': etype}
                    queue.append(effect)
    # 反向传播（结果→原因）
    queue2 = list(active_nodes.keys())
    visited2 = set(active_nodes.keys())
    while queue2:
        cur = queue2.pop(0)
        cur_anomaly = node_anomaly.get(cur, 0)
        for cause, weight, etype in adj_backward.get(cur, []):
            if cause not in visited2:
                visited2.add(cause)
                prop = cur_anomaly * abs(weight) * 0.5  # 反向强度减半
                if prop > 0.05:
                    old_anomaly = node_anomaly.get(cause, 0)
                    node_anomaly[cause] = max(old_anomaly, prop)
                    propagation[cause] = {'via': cur, 'strength': round(prop, 3), 'etype': etype}
                    queue2.append(cause)

    chains = []
    for cause, effect, weight_raw, etype in SLEEP_CAUSAL_EDGES:
        use_w = abs(weight_raw)
        # 前后都在输入中
        if cause in active_nodes and effect in active_nodes:
            ca = active_nodes[cause]['anomaly']
            ea = active_nodes[effect]['anomaly']
            prop = use_w * ca * min(1.0, ea / max(ca, 0.01))
            if prop > 0.1:
                chains.append({
                    'cause': cause, 'effect': effect,
                    'causal_weight': round(weight_raw, 2),
                    'propagation_strength': round(prop, 3),
                    'evidence_type': etype, 'path': [cause, effect],
                })
        # 前因在输入 + 后果BFS传播到
        elif cause in active_nodes and effect in node_anomaly:
            prop = use_w * active_nodes[cause]['anomaly']
            if prop > 0.1:
                chains.append({
                    'cause': cause, 'effect': effect,
                    'causal_weight': round(weight_raw, 2),
                    'propagation_strength': round(prop, 3),
                    'evidence_type': etype, 'path': [cause, effect],
                    'inferred': True,
                })
        # 后果在输入 + 前因BFS传播到
        elif effect in active_nodes and cause in node_anomaly:
            prop = use_w * active_nodes[effect]['anomaly'] * 0.5
            if prop > 0.1:
                chains.append({
                    'cause': cause, 'effect': effect,
                    'causal_weight': round(weight_raw, 2),
                    'propagation_strength': round(prop, 3),
                    'evidence_type': etype, 'path': [cause, effect],
                    'inferred': True,
                })
        # 前后都BFS传播到
        elif cause in node_anomaly and effect in node_anomaly:
            prop = node_anomaly.get(cause, 0) * use_w
            if prop > 0.1:
                chains.append({
                    'cause': cause, 'effect': effect,
                    'causal_weight': round(weight_raw, 2),
                    'propagation_strength': round(prop, 3),
                    'evidence_type': etype, 'path': [cause, effect],
                    'inferred': True,
                })

    chains.sort(key=lambda x: -x['propagation_strength'])

    root_cause = 'unknown'
    max_score = 0
    for node, info in active_nodes.items():
        out_deg = adj_forward.get(node, [])
        score = info['anomaly'] * (1 + len(out_deg))
        if score > max_score:
            max_score = score
            root_cause = node

    if chains:
        top = chains[0]
        cause_val = active_nodes[top['cause']]['value'] if top['cause'] in active_nodes else '?'
        effect_val = active_nodes[top['effect']]['value'] if top['effect'] in active_nodes else '?'
        explanation = (
            f"主要路径: {SLEEP_CAUSAL_GRAPH.get(top['cause'], top['cause'])}"
            f"({cause_val}) → "
            f"{SLEEP_CAUSAL_GRAPH.get(top['effect'], top['effect'])}"
            f"({effect_val}), "
            f"推理强度{top['propagation_strength']:.2f}."
        )
    else:
        explanation = '未发现显著因果传播.'

    if chains:
        strengths = [c['propagation_strength'] for c in chains[:5]]
        total_s = sum(strengths)
        entropy = -(sum((s/total_s) * math.log2(s/total_s)
                       for s in strengths if s > 0)) / math.log2(len(strengths)) if total_s > 0 else 0.0
    else:
        entropy = 0.0

    return {
        'chains': chains[:5],
        'root_cause': root_cause,
        'root_cause_label': SLEEP_CAUSAL_GRAPH.get(root_cause, root_cause),
        'entropy': round(entropy, 3),
        'explanation': explanation,
        'active_nodes': {k: {'value': v['value'], 'anomaly': v['anomaly']}
                         for k, v in active_nodes.items()},
    }


class SleepCausalInference:
    """睡眠因果推理 — 将自由能评估 + 因果链 → 可理解的解释"""

    def __init__(self, user_id):
        self.user_id = user_id
        self._history = []

    def infer(self, inputs, vfe_result=None):
        causal = trace_causal_path(inputs)
        rc = causal['root_cause']
        explanation = causal['explanation']

        vfe_note = ''
        if vfe_result:
            vfe = vfe_result.get('vfe', 0)
            if vfe < 0.1:
                vfe_note = '状态稳定,无需干预.'
            elif vfe > 0.3:
                vfe_note = f'检测到异常(VFE={vfe:.2f}),建议关注.'

        action_map = {
            'stress': '建议入睡前做15分钟正念冥想,降低压力水平.',
            'hr': '心率偏高时,可尝试4-7-8呼吸法(吸气4秒→屏息7秒→呼气8秒).',
            'sleep_latency': '入睡困难可尝试渐进式肌肉放松(从头到脚逐部位绷紧→放松).',
            'awake_times': '夜间觉醒频繁建议检查卧室温度和噪音水平.',
            'total_sleep': '总睡眠不足,建议提前30分钟上床.',
        }
        action = action_map.get(rc, '建议保持规律作息.')

        result = {
            'causal_path': causal,
            'root_cause': rc,
            'root_cause_label': causal['root_cause_label'],
            'explanation': f'{vfe_note}{explanation}',
            'action_suggestion': action,
            'confidence': max(0.1, 1.0 - causal['entropy']),
        }
        self._history.append(result)
        return result
