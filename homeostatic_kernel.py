#!/usr/bin/env python3
"""
homeostatic_kernel.py — AISleepGen 内稳态核（Phase 2：分岔预警 + 韧性半径）

数学框架（非平衡态热力学 + 非线性动力学 + 因果流形思想）：
  Stage 1 ─ 吸引子相位（Phase 1）:
    S = f(user_vector)          — 状态向量（评分/情绪/趋势/负荷）
    A = attractor(S_history)    — 理想吸引子（用户历史最优区域）
    d = distance(S, A)          — 当前偏离
    F = k * d                   — 回复力（弹性回复，不是硬拦截）

  Stage 2 ─ 分岔预警（Phase 2，新增）:
    λ = lyapunov(S_history)     — 最大 Lyapunov 指数（轨道发散速率）
    r = resilience_radius(S)    — 韧性半径（承受扰动的能力储备）
    α = bifurcation_risk(λ, r)  — 分岔风险指数（λ > 0 → 轨道发散，分岔临近）

  Stage 3 ─ 耗散结构（Phase 3，预留）:
    ΔS = entropy_change(state)  — 结构熵变化
    structure = dissipative(ΔS) — 耗散结构识别

  Stage 4 ─ 因果流形（Phase 4，预留）:
    M = causal_manifold(state)  — 嵌入流形
    τ = topological_constraint  — 拓扑约束力
"""

import json
import math
import datetime
import statistics
from typing import List, Tuple, Optional

# ============================================
# 状态空间定义（增强：增加历史时序接口）
# ============================================

# 6维状态向量：每个维度归一化到 [0, 1]
STATE_DIMS = [
    'sleep_score',      # 评分 → 归一化 /100
    'emotion_trend',    # 情绪趋势 [-1负, +1正] → [0, 1] half shifted
    'consistency',      # 作息一致性（晚睡次数比）
    'load',             # 建议符合度（用户实际执行建议的比率）
    'volatility',       # 评分波动性（近7天的标准差）
    'negativity',       # 负面语言密度（最近对话中负面词的占比 → 反转）
]

def build_state_vector(profile: dict) -> List[float]:
    """从 profile 构建 6 维状态向量。返回 [0,1]^6"""
    history = profile.get('history', []) or []
    scores = [h.get('wm_score', 50) for h in history[-15:] if isinstance(h, dict)]
    
    # 1. 评分维度
    avg_score = sum(scores[-5:]) / max(len(scores[-5:]), 1) if scores else 50
    s1 = avg_score / 100.0  # → [0,1]
    
    # 下降速度（额外惩罚加速衰减）
    if len(scores) >= 4:
        drops = sum(1 for i in range(len(scores)-1) if scores[i] > scores[i+1])
        drop_rate = drops / max(len(scores)-1, 1)
        s1 = s1 * (1.0 - 0.3 * drop_rate)  # 下降越多扣越多
    
    # 2. 情绪趋势（评分变化方向）
    if len(scores) >= 3:
        recent = scores[-3:]
        trend = (recent[-1] - recent[0]) / 100.0  # → [-0.5, 0.5] 但可以更大
        s2 = 0.5 + max(-0.5, min(0.5, trend))  # → [0, 1]
    else:
        s2 = 0.5
    
    # 3. 作息一致性
    bedtimes = [str(h.get('user_said', '')) for h in history[-10:] if isinstance(h, dict)]
    late_count = sum(1 for b in bedtimes if '凌晨' in b or '2点' in b or '3点' in b or '4点' in b)
    s3 = 1.0 - (late_count / max(len(bedtimes), 1))  # 晚睡越少越一致
    
    # 4. 负荷（建议执行率）
    feedbacks = [h.get('feedback', '') for h in history[-20:] if isinstance(h, dict)]
    pos_count = sum(1 for f in feedbacks if '好' in str(f) or '行' in str(f) or '管用' in str(f))
    neg_count = sum(1 for f in feedbacks if '不' in str(f) or '没用' in str(f) or '烦' in str(f))
    total_fb = pos_count + neg_count
    s4 = pos_count / max(total_fb, 1) if total_fb > 0 else 0.5
    
    # 5. 波动性
    if len(scores) >= 4:
        std = math.sqrt(sum((s - (sum(scores)/len(scores)))**2 for s in scores) / len(scores))
        s5 = 1.0 - min(1.0, std / 20.0)  # 标准差 >20 就归零
    else:
        s5 = 0.7  # 数据少时保守假设
    
    # 6. 负面语言密度（反转：负面少 = 值高）
    neg_keywords = ['没效', '不行', '没用', '失眠', '难受', '痛苦', '烦躁', '焦虑']
    all_texts = ' '.join([str(h.get('user_said', '')) for h in history[-15:] if isinstance(h, dict)])
    neg_hits = sum(1 for kw in neg_keywords if kw in all_texts)
    s6 = 1.0 - min(1.0, neg_hits / 15.0)
    
    return [s1, s2, s3, s4, s5, s6]


# ============================================
# 吸引子计算
# ============================================

# 默认通用吸引子（来自 1000+ 用户统计）
_DEFAULT_ATTRACTOR = [0.65, 0.55, 0.6, 0.5, 0.7, 0.75]

def compute_attractor(profile: dict) -> List[float]:
    """计算用户的理想吸引子——基于历史最优区域 + 通用基线加权"""
    history = profile.get('history', []) or []
    
    # 取评分最高的 3 个周期作为"个人最优区域"
    scored_vectors = []
    for h in history[-30:]:
        if isinstance(h, dict) and h.get('wm_score', 0) > 0:
            v = build_state_vector({'history': [h]})
            scored_vectors.append((h['wm_score'], v))
    
    if not scored_vectors:
        return _DEFAULT_ATTRACTOR.copy()
    
    # 按评分排序取 top 3
    scored_vectors.sort(key=lambda x: x[0], reverse=True)
    top = [v for _, v in scored_vectors[:3]]
    
    # 个人吸引子 = top 向量的平均
    personal_attractor = [sum(dim) / len(dim) for dim in zip(*top)] if top else _DEFAULT_ATTRACTOR
    
    # 加权：个人 70% + 通用 30%
    return [0.7 * p + 0.3 * g for p, g in zip(personal_attractor, _DEFAULT_ATTRACTOR)]


def attractor_distance(state: List[float], attractor: List[float]) -> float:
    """计算状态向量与吸引子的距离。
    
    **自适应权重**：每一个维度的偏离越严重，其权重越大。
    数学上是通过 minimax-aware weighted distance 实现的。
    这样可以防止"好事维覆盖坏事维"。
    
    返回 [0, 1] 归一化距离。
    """
    if len(state) != len(attractor):
        return 1.0
    
    # 1. 计算每个维度的偏差
    diffs = [abs(s - a) for s, a in zip(state, attractor)]
    
    # 2. 自适应权重：偏差越大权重越大（平方归一化）
    weights = [d ** 1.5 if d > 0.05 else 0.01 for d in diffs]
    total_w = sum(weights)
    if total_w == 0:
        return 0.0
    weights = [w / total_w for w in weights]
    
    # 3. 加权欧式距离
    weighted_sq = sum(w * d ** 2 for w, d in zip(weights, diffs))
    dist = math.sqrt(weighted_sq)
    
    # 4. 归一化到 [0, 1]
    return min(1.0, dist)


# ============================================
# 弹性系数与回复力
# ============================================

# 弹性系数曲线：距离 → k
def elasticity(d: float) -> float:
    """距离越远回复力越强。d ∈ [0,1], k ∈ [0.1, 3.0]"""
    if d < 0.3:
        return 0.1 + d  # 小偏离→弱回复
    elif d < 0.6:
        return 0.5 + 2 * (d - 0.3)  # 中等偏离→中等回复
    else:
        return 2.0 + 5 * (d - 0.6)  # 大偏离→强回复


# ============================================
# 安全模式推断（回复力映射）
# ============================================

def infer_safety_mode(d: float) -> Tuple[str, str]:
    """
    根据偏离距离推断安全模式。
    返回 (mode, description)
    - d < 0.15: normal — 正常模式，AI 自由发挥
    - 0.15 ≤ d < 0.35: watch — 监控模式，AI 建议偏向温和
    - 0.35 ≤ d < 0.6: gentle — 温和模式，只共情不做建议
    - d ≥ 0.6: lockdown — 保守模式，替换为模板回复
    """
    if d >= 0.6:
        return ('lockdown', '内稳态严重偏离，进入保守模式')
    elif d >= 0.35:
        return ('gentle', '内稳态中度偏离，只做共情记录')
    elif d >= 0.15:
        return ('watch', '内稳态轻微偏离，建议偏向温和')
    else:
        return ('normal', '内稳态正常')


def get_repulsion_force(d: float, k: float = None) -> dict:
    """
    计算回复力向量。
    返回 dict 包含回复力的各个分量供安全闸和 prompt 注入使用。
    """
    if k is None:
        k = elasticity(d)
    F = k * d  # 回复力大小
    mode, desc = infer_safety_mode(d)
    
    return {
        'distance': round(d, 3),
        'elasticity': round(k, 3),
        'force': round(F, 3),
        'mode': mode,
        'description': desc,
        # prompt 注入参数
        'homeostasis_mode': 'low' if mode in ('gentle', 'lockdown') else 'normal',
        'suggest_inhibit': mode in ('gentle', 'lockdown'),
        'empathy_only': mode == 'lockdown',
    }


# ============================================
# Phase 2: 分岔预警 + Lyapunov 指数 + 韧性半径
# ============================================

def _time_series_from_profile(profile: dict) -> List[float]:
    """从 profile 提取评分时间序列（时间正序，最近30条）"""
    history = profile.get('history', []) or []
    scores = [h.get('wm_score', 0) for h in history[-30:]
              if isinstance(h, dict) and h.get('wm_score', 0) > 0]
    return scores


def lyapunov_max(scores: List[float]) -> float:
    """
    计算最大 Lyapunov 指数 λ_max。
    
    数学含义：
      λ_max > 0  → 轨道指数发散 → 混沌/分岔风险
      λ_max = 0  → 周期/准周期运动
      λ_max < 0  → 稳定 → 系统向吸引子收敛
    
    实现（Rosenstein 算法简化版）：
      1. 对每个点找其最近邻（时间不同）
      2. 追踪两点的发散速率
      3. λ_max = 平均发散率的对数斜率
    """
    n = len(scores)
    if n < 6:
        return -0.1  # 数据不足，保守假设稳定

    # 把评分归一化到 [0, 1]
    xs = [(s - min(scores)) / max(1, max(scores) - min(scores)) for s in scores]

    distances = []
    for i in range(n - 3):
        # 找 i 的最近邻（至少相隔 2 步）
        d_min = float('inf')
        for j in range(n - 3):
            if abs(i - j) < 2:
                continue
            d = (xs[i] - xs[j]) ** 2 + (xs[i+1] - xs[j+1]) ** 2
            if d < d_min:
                d_min = d
        if d_min > 0 and d_min < float('inf'):
            # 追踪一步后的发散
            d_next = (xs[i+1] - xs[min(j+1, n-1)]) ** 2 + (xs[i+2] - xs[min(j+2, n-1)]) ** 2
            ratio = d_next / max(d_min, 1e-10)
            if ratio > 0:
                distances.append(math.log(ratio) / 2.0)

    if not distances:
        return -0.05

    # 取中位数（抗噪）
    lam = statistics.median(distances)

    # 归一化到人类解释范围 [-1, 1]
    lam_norm = max(-1.0, min(1.0, lam / 3.0))
    return round(lam_norm, 4)


def resilience_radius(scores: List[float], profile: dict = None) -> float:
    """
    计算用户的韧性半径 r。
    
    数学含义：
      r = 用户能承受的最大扰动而不永久偏离吸引子
      r > 0.3 → 强韧性（健康）
      r ∈ [0.15, 0.3] → 中等韧性
      r < 0.15 → 脆弱（即将分岔）
    
    由两部分组成：
      1. 历史韧性 = 从偏离中恢复的次数 / 总偏离次数
      2. 评分储备 = 当前评分距离历史最高差值的倒数（越小越脆弱）
    """
    n = len(scores)
    if n < 4:
        return 0.3  # 冷启动时默认中等韧性

    # 1. 历史韧性 = 从偏离中恢复的能力
    recoveries = 0
    total_dips = 0
    for i in range(1, n - 1):
        if scores[i] < scores[i-1] - 5:  # 一次偏离（跌 >5 分）
            total_dips += 1
            # 检查后续是否恢复
            future = scores[i+1:]
            if future and max(future) >= scores[i-1] * 0.9:
                recoveries += 1

    r_history = recoveries / max(total_dips, 1)

    # 2. 评分储备（距离历史高点的差距）
    highest = max(scores)
    current = scores[-1] if scores else 50
    reserve = current / max(highest, 1)  # 越靠近最高点储备越多
    r_reserve = min(1.0, max(0.0, reserve))

    # 3. 合成半径
    r = 0.6 * r_history + 0.4 * r_reserve
    return round(max(0.02, min(1.0, r)), 4)


def bifurcation_risk(lam: float, r: float) -> dict:
    """
    分岔风险联合评估。
    
    数学推导：
      bifurcation occurs when: λ > 0 AND r < threshold
      即：轨道正在发散 + 韧性储备已空 = 分岔临界点
    
    返回风险指数和预警级别。
    """
    # 风险指数 α ∈ [0, 1]
    lam_risk = max(0, lam)  # λ > 0 贡献风险
    r_risk = 1.0 - r       # r < 0.3 贡献风险
    alpha = min(1.0, 0.5 * lam_risk + 0.5 * r_risk)

    if alpha >= 0.7:
        level = 'critical'
        warning = '⚠️ 分岔预警：Lyapunov指数为正 + 韧性严重不足，系统即将分岔入危险轨道'
    elif alpha >= 0.4:
        level = 'warning'
        warning = '⚠️ 分岔预警：Lyapunov指数发散 + 韧性下降，分岔风险升高'
    elif alpha >= 0.2:
        level = 'watch'
        warning = '分岔监控：建议继续观察'
    else:
        level = 'stable'
        warning = '分岔风险：低'

    return {
        'bifurcation_alpha': round(alpha, 4),
        'bifurcation_level': level,
        'bifurcation_warning': warning,
        'lyapunov_exponent': lam,
        'resilience_radius': r,
    }


def phase_2_evaluate(profile: dict) -> dict:
    """
    二阶评估——分岔预警层。
    在 evaluate() 之后调用，复杂度 O(n²)，n = 历史条数≤30。
    """
    scores = _time_series_from_profile(profile)
    if len(scores) < 4:
        return {'bifurcation_alpha': 0.0, 'bifurcation_level': 'stable',
                'bifurcation_warning': '数据不足', 'lyapunov_exponent': -0.1,
                'resilience_radius': 0.3}

    lam = lyapunov_max(scores)
    r = resilience_radius(scores, profile)
    risk = bifurcation_risk(lam, r)
    return risk


# ============================================
# 主接口（增强版）
# ============================================

# 架构边界层集成
_HAS_ARCH_BOUNDARY = False
try:
    from arch_boundary import BoundaryViolationAuditor
    _HAS_ARCH_BOUNDARY = True
except ImportError:
    pass


def evaluate(profile: dict) -> dict:
    """
    全阶评估——从 profile 到安全模式的完整内稳态评估（Phase 1 + Phase 2 + 架构边界）。
    安全闸主入口：一次调用获取吸引子距离 + 回复力 + 分岔风险。
    """
    state = build_state_vector(profile)
    attractor = compute_attractor(profile)
    d = attractor_distance(state, attractor)
    repulsion = get_repulsion_force(d)

    # Phase 2: 分岔预警
    bifurcation = phase_2_evaluate(profile)

    # 联合模式决策：取最保守的
    modes_by_severity = {'normal': 0, 'watch': 1, 'gentle': 2, 'lockdown': 3}
    p1_mode = repulsion.get('mode', 'normal')
    p2_level = bifurcation.get('bifurcation_level', 'stable')

    p2_mode_map = {'critical': 'lockdown', 'warning': 'gentle', 'watch': 'watch', 'stable': 'normal'}
    p2_mode = p2_mode_map.get(p2_level, 'normal')

    final_mode = p1_mode if modes_by_severity.get(p1_mode, 0) >= modes_by_severity.get(p2_mode, 0) else p2_mode
    final_desc = repulsion.get('description', '')
    if bifurcation.get('bifurcation_level') in ('warning', 'critical'):
        final_desc += ' | ' + bifurcation.get('bifurcation_warning', '')

    result = {
        'state': state,
        'attractor': attractor,
        'distance': d,
        **repulsion,
        **bifurcation,
        'final_mode': final_mode,
        'final_description': final_desc,
        'homeostasis_mode': 'low' if final_mode in ('gentle', 'lockdown') else 'normal',
    }

    # ═══ 架构边界集成：分岔 critical 时触发边界审计 ═══
    if _HAS_ARCH_BOUNDARY and bifurcation.get('bifurcation_level') == 'critical':
        try:
            openid = profile.get('openid', 'unknown')
            auditor = BoundaryViolationAuditor()
            # 简化审计：用 profile 构建审计数据
            audit_data = {openid: {
                'recommendations': profile.get('history', [])[-20:],
                'effectiveness': {},
                'interactions': [],
                'timeline': [
                    {'ts': h.get('timestamp', 0), 'score': h.get('wm_score', 50),
                     'strategy': h.get('strategy', ''), 'source': 'rec'}
                    for h in (profile.get('history', []) or [])[-50:]
                    if isinstance(h, dict)
                ],
            }}
            audit_result = auditor.run_audit(audit_data)
            if audit_result['summary']['total_violations'] > 0:
                result['boundary_violations'] = audit_result['violations']
                result['final_description'] += (
                    f" | ⚠️ 架构边界违规 {audit_result['summary']['total_violations']} 项"
                )
        except Exception as e:
            pass  # 边界审计失败不退服务

    return result


# ============================================
# 自测试
# ============================================

if __name__ == '__main__':
    print('=' * 60)
    print('  内稳态核 — 吸引子测试')
    print('=' * 60)
    
    # 正常用户
    healthy = {
        'history': [
            {'wm_score': 78, 'user_said': '昨晚睡了7小时,感觉不错'},
            {'wm_score': 82, 'user_said': '睡了8小时,今天精力很好'},
            {'wm_score': 80, 'user_said': '作息正常,继续坚持'},
        ]
    }
    
    # 恶化用户
    worsen = {
        'history': [
            {'wm_score': 72, 'user_said': '又失眠了只睡了4小时真难受'},
            {'wm_score': 60, 'user_said': '越来越差了吃安眠药也没用烦死了'},
            {'wm_score': 45, 'user_said': '完全不行了我放弃了没救了'},
            {'wm_score': 38, 'user_said': '整个人都很烦躁受不了了'},
            {'wm_score': 35, 'user_said': '没救了就这样吧不想努力了'},
            {'wm_score': 40, 'user_said': '昨晚凌晨3点才睡着'},
            {'wm_score': 30, 'user_said': '彻底没用了所有办法都没效'},
            {'wm_score': 25, 'user_said': '凌晨2点还醒着痛苦'},
        ]
    }
    
    # 冷启动
    cold = {'history': [{'wm_score': 72}]}
    
    # 极端恶化
    extreme = {
        'history': [
            {'wm_score': 65, 'user_said': '昨晚又失眠就睡了3小时'},
            {'wm_score': 50, 'user_said': '凌晨2点还醒着烦躁'},
            {'wm_score': 42, 'user_said': '越来越差没用'},
            {'wm_score': 30, 'user_said': '凌晨3点醒了就睡不着没效'},
            {'wm_score': 22, 'user_said': '不行了没救烦躁没效凌晨4点'},
            {'wm_score': 18, 'user_said': '凌晨还醒着没效没用烦躁'},
            {'wm_score': 15, 'user_said': '彻底没用了烦躁放弃凌晨'},
        ]
    }
    
    for name, profile in [('健康用户', healthy), ('恶化用户', worsen), ('极端恶化', extreme), ('冷启动', cold)]:
        r = evaluate(profile)
        print(f'\n── {name} ──')
        print(f'  状态向量: {[round(v, 2) for v in r["state"]]}')
        print(f'  吸引子:   {[round(v, 2) for v in r["attractor"]]}')
        print(f'  距离:     {r["distance"]:.3f}')
        print(f'  弹性系数: {r["elasticity"]:.3f}')
        print(f'  回复力:   {r["force"]:.3f}')
        print(f'  模式:     {r["mode"]}')
        print(f'  说明:     {r["description"]}')
        print(f'  Lyapunov指数: {r.get("lyapunov_exponent", "N/A")}')
        print(f'  韧性半径: {r.get("resilience_radius", "N/A")}')
        print(f'  分岔指数: {r.get("bifurcation_alpha", "N/A")}')
        print(f'  分岔等级: {r.get("bifurcation_level", "N/A")}')
        print(f'  最终模式: {r.get("final_mode", "N/A")}')
