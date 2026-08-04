# -*- coding: utf-8 -*-
"""
瑞奇流（Ricci Flow）曲率感知模块 — 几何与拓扑视角的专家多样性控制

核心思想：
  瑞奇流通过"曲率"描述流形的局部几何，高曲率区域收缩、低曲率区域展平。
  映射到专家会诊系统：
  - 高曲率 = 该专家的观点与众不同（有价值的分歧 → 保留/放大）
  - 低曲率 = 该专家的观点与群体趋同（可能搭便车 → 降权/压缩）

用法：
  from ricci_flow import RicciFlowCurvature
  curvature = RicciFlowCurvature()
  adjusted = curvature.adjust(round2)

参考：
  - 瑞奇流在深度学习中的理论解释：DNN逐层变换类似瑞奇流"磨平"流形
  - RFHND（里奇流引导的超图神经扩散）：自适应调节信息扩散
  - PIORF（物理信息奥利维尔-里奇流）：识别瓶颈建立"信息高速公路"
"""

import math
from collections import defaultdict
from typing import Dict, List, Optional, Tuple


class RicciFlowCurvature:
    """
    专家会诊的瑞奇曲率计算与调整器。

    通过三种曲率指标，量化每位专家的"几何角色"：
    1. score_curvature  — 评分空间的局部曲率（基于与相邻专家的评分差距）
    2. finding_curvature — 发现空间的语义曲率（基于文本相似度）
    3. temporal_curvature — 时间维度曲率（基于历史轨迹的摆动幅度）

    最终曲率 = 加权组合 → 用于调整专家权重
    """

    def __init__(self, k_neighbors: int = 3, epsilon: float = 1e-8):
        self.k = k_neighbors          # K近邻计算曲率
        self.epsilon = epsilon        # 防止除零
        # 曲率 → 置信度乘数的映射参数
        self.curvature_boost_factor = 0.15   # 高曲率加成幅度
        self.curvature_penalty_factor = 0.10 # 低曲率惩罚幅度
        # 曲率阈值
        self.high_curvature_threshold = 0.20  # 超过此值 → "有价值的分歧"
        self.low_curvature_threshold = 0.05   # 低于此值 → "搭便车/趋同"

    def _compute_score_curvature(
        self, expert_scores: Dict[str, float]
    ) -> Dict[str, float]:
        """
        计算每个专家的"评分曲率"。

        原理：
          在1维评分空间中，某点的曲率 ≈ 该点与相邻点的二阶差分。
          用K近邻的评分标准差作为曲率代理：
          - 高曲率 = 与周围专家评分差异大 → 独特视角
          - 低曲率 = 与周围专家评分几乎一致 → 从众

        数学形式（离散曲率）：
          κ_i = (1/K) * Σ (s_i - s_j)² / d(i,j)²
          其中 s 为评分，d 为索引距离（相邻专家索引差）
        """
        names = list(expert_scores.keys())
        scores = [expert_scores.get(n, 0.5) for n in names]
        n = len(names)
        curvature = {}

        for i, name_i in enumerate(names):
            # 找到当前专家的K近邻（按索引距离）
            # 在无天然拓扑时，用评分排序后的位置作为"流形坐标"
            neighbors = []
            for j in range(n):
                if i == j:
                    continue
                idx_dist = abs(i - j)
                score_dist = abs(scores[i] - scores[j])
                # 综合距离：索引距离 + 评分距离
                dist = math.sqrt(idx_dist ** 2 + score_dist ** 2 * 10)
                neighbors.append((dist, j))
            neighbors.sort(key=lambda x: x[0])
            k_nearest = neighbors[:min(self.k, len(neighbors))]

            # 计算K近邻加权曲率
            total_weight = 0.0
            weighted_curvature = 0.0
            for dist, j in k_nearest:
                if dist < self.epsilon:
                    continue
                # 评分二阶差分近似
                second_diff = (scores[i] - scores[j]) ** 2
                weight = 1.0 / max(dist, self.epsilon)
                weighted_curvature += second_diff * weight
                total_weight += weight

            curv = weighted_curvature / max(total_weight, self.epsilon)
            curvature[name_i] = curv

        return curvature

    def _compute_finding_curvature(
        self, expert_findings: Dict[str, List[str]]
    ) -> Dict[str, float]:
        """
        计算每位专家的"发现语义曲率"。

        用Token-Jaccard相似度的方差衡量某个专家的发现
        在群体中的独特性程度。

        高曲率 = 几乎没有人跟该专家说一样的话
        低曲率 = 该专家的话在群体中频繁出现
        """
        # tokenize所有发现
        token_sets = {}
        for name, findings in expert_findings.items():
            text = ' '.join(findings)
            tokens = set(
                text.replace('【', ' ').replace('】', ' ')
                    .replace('，', ' ').replace('。', ' ')
                    .replace('(', ' ').replace(')', ' ')
                    .split()
            )
            token_sets[name] = tokens

        names = list(token_sets.keys())
        n = len(names)
        curvature = {}

        for name_i in names:
            tokens_i = token_sets.get(name_i, set())
            if not tokens_i:
                curvature[name_i] = 0.0
                continue

            # 计算该专家与其他所有专家的Jaccard距离
            jaccard_dists = []
            for name_j in names:
                if name_i == name_j:
                    continue
                tokens_j = token_sets.get(name_j, set())
                if not tokens_j:
                    continue
                intersection = len(tokens_i & tokens_j)
                union = len(tokens_i | tokens_j)
                # Jaccard距离 = 1 - Jaccard相似度
                jd = 1.0 - (intersection / max(union, 1))
                jaccard_dists.append(jd)

            if not jaccard_dists:
                curvature[name_i] = 0.0
                continue

            # 曲率 = Jaccard距离的均值（平均而言，该专家与其他人有多不同）
            # 再用方差归一化：均值高但方差低 → 稳定地独特
            mean_jd = sum(jaccard_dists) / len(jaccard_dists)
            var_jd = sum((d - mean_jd) ** 2 for d in jaccard_dists) / len(jaccard_dists)
            # 稳定独特的专家曲率高；随机波动的曲率低
            stability = 1.0 / (1.0 + var_jd * 5)  # 稳定性因子
            finding_curv = mean_jd * (0.5 + 0.5 * stability)
            curvature[name_i] = finding_curv

        return curvature

    def compute_expert_curvatures(
        self, round2: Dict[str, Dict]
    ) -> Dict[str, Dict[str, float]]:
        """
        对给定的一轮专家输出，计算每位专家的多维曲率。

        返回:
          {
            'ClinicalPsychologist': {
              'score_curvature': 0.12,
              'finding_curvature': 0.35,
              'combined_curvature': 0.27,
              'curvature_scale': 'high' | 'medium' | 'low'
            },
            ...
          }
        """
        # 提取评分和发现
        expert_scores = {}
        expert_findings = {}
        for name, result in round2.items():
            expert_scores[name] = result.get('score', 0.5)
            expert_findings[name] = result.get('findings', [])

        # 计算两种曲率
        score_curv = self._compute_score_curvature(expert_scores)
        finding_curv = self._compute_finding_curvature(expert_findings)

        # 合并结果
        result_map = {}
        all_names = set(list(score_curv.keys()) + list(finding_curv.keys()))
        for name in all_names:
            sc = score_curv.get(name, 0.0)
            fc = finding_curv.get(name, 0.0)
            # 综合曲率：评分曲率权重0.4 + 发现曲率权重0.6
            # 发现曲率更可靠，因为文本空间比1维评分空间承载更多信息
            combined = sc * 0.4 + fc * 0.6

            # 定级
            if combined >= self.high_curvature_threshold:
                scale = 'high'
            elif combined <= self.low_curvature_threshold:
                scale = 'low'
            else:
                scale = 'medium'

            result_map[name] = {
                'score_curvature': round(sc, 4),
                'finding_curvature': round(fc, 4),
                'combined_curvature': round(combined, 4),
                'curvature_scale': scale,
            }

        return result_map

    def adjust(
        self, round2: Dict[str, Dict]
    ) -> Tuple[Dict[str, Dict], Dict[str, Dict[str, float]]]:
        """
        主入口：根据瑞奇曲率调整各专家的置信度。

        调整策略（类似瑞奇流的"曲率驱动收缩/膨胀"）：
          - 高曲率（独特观点） → 置信度提升（收缩区域需要更多关注）
          - 低曲率（趋同/搭便车） → 置信度降低（展平区域信息量少）
          - 中曲率 → 微调

        返回 (adjusted_round2, curvature_map)
        """
        curvature_map = self.compute_expert_curvatures(round2)

        for name, result in round2.items():
            if name not in curvature_map:
                continue

            curv_info = curvature_map[name]
            combined = curv_info['combined_curvature']

            original_conf = result.get('confidence', 0.5)
            is_risk_expert = name in ('RiskManager', 'CardiacMonitor', 'SleepPhysician')
            is_psych_expert = name in ('ClinicalPsychologist', 'CBT')
            is_physio_expert = name in ('LifeScientist', 'NutritionMetabolism')

            # --- 曲率驱动的权重调整 ---
            if combined >= self.high_curvature_threshold:
                # 高曲率 → 提升置信度
                # 但不同角色加成力度不同：
                # 风险专家和心理学家的分歧更值得重视
                if is_risk_expert:
                    boost = self.curvature_boost_factor * 1.5
                elif is_psych_expert:
                    boost = self.curvature_boost_factor * 1.2
                else:
                    boost = self.curvature_boost_factor

                new_conf = min(0.95, original_conf * (1.0 + boost))
                result['_ricci_curvature'] = combined
                result['_ricci_action'] = 'boost'

            elif combined <= self.low_curvature_threshold:
                # 低曲率 → 降低置信度
                # 但生理学家的低曲率可能是"公认常识"而非搭便车
                if is_physio_expert:
                    penalty = self.curvature_penalty_factor * 0.5  # 轻罚
                else:
                    penalty = self.curvature_penalty_factor

                new_conf = max(0.1, original_conf * (1.0 - penalty))
                result['_ricci_curvature'] = combined
                result['_ricci_action'] = 'penalize'

            else:
                # 中曲率 → 微调
                # 向均值的轻微偏移，幅度与曲率偏离中心的程度成正比
                mid = (self.high_curvature_threshold + self.low_curvature_threshold) / 2
                offset = (combined - mid) / mid  # 归一化偏移
                adjustment = 1.0 + offset * 0.05  # ±5% 微调
                new_conf = max(0.2, min(0.9, original_conf * adjustment))
                result['_ricci_curvature'] = combined
                result['_ricci_action'] = 'tweak'

            # 应用调整
            result['confidence'] = round(new_conf, 3)
            result['_ricci_conf_original'] = round(original_conf, 3)

        return round2, curvature_map


class CurvatureLogger:
    """
    曲率历史追踪器 — 检测专家角色的"时间曲率"变化。
    
    如果某专家的曲率在多次运行中持续衰减（从高曲率→低曲率），
    说明该专家正在"退化"为群体克隆体。
    反之，如果曲率持续升高，说明该专家正在发现新的独特领域。
    """

    def __init__(self, max_history: int = 20):
        self.history = defaultdict(list)  # {expert_name: [curvature_values]}
        self.max_history = max_history

    def log(self, curvatures: Dict[str, Dict[str, float]]) -> None:
        """记录本轮曲率"""
        for name, info in curvatures.items():
            combined = info['combined_curvature']
            self.history[name].append(combined)
            # 限制历史长度
            if len(self.history[name]) > self.max_history:
                self.history[name] = self.history[name][-self.max_history:]

    def get_temporal_curvature(self, name: str) -> Optional[float]:
        """
        计算时间曲率：最近N次曲率的标准差。
        高时间曲率 = 该专家在"稳定独特"和"突然趋同"之间波动 → 不稳定信号
        低时间曲率 = 该专家的角色稳定
        """
        vals = self.history.get(name, [])
        if len(vals) < 3:
            return None
        mean_v = sum(vals) / len(vals)
        var_v = sum((v - mean_v) ** 2 for v in vals) / len(vals)
        return var_v ** 0.5

    def get_trend(self, name: str) -> str:
        """判断曲率趋势"""
        vals = self.history.get(name, [])
        if len(vals) < 3:
            return 'insufficient'
        recent = vals[-3:]
        earlier = vals[:-3] if len(vals) > 3 else vals[:1]
        if not earlier:
            return 'stable'
        avg_recent = sum(recent) / len(recent)
        avg_earlier = sum(earlier) / len(earlier)
        diff = avg_recent - avg_earlier
        if diff > 0.05:
            return 'rising'    # 越来越独特
        elif diff < -0.05:
            return 'falling'   # 越来越趋同
        return 'stable'
