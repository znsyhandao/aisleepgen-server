#!/usr/bin/env python3
"""
uncertainty_calibration.py — 专家不确定性校准 (2026-07-06)

论文: UA-ChatDev (arXiv 2607.02186) 
核心: 不确定性感知多Agent协作

问题: 10位专家的 confidence 全部固定为 0.78, 不反映数据充分度

方案:
  1. 数据量不足 → 降低 confidence (线性插值: 3条=0.3, 30+=0.8)
  2. 数据波动大 → 降低 confidence (高std = 低置信)
  3. 交叉会诊不充分 → 降低 confidence (peer_findings 少)
  4. 历史预测误差大 → 降低 confidence (avg_err 从 personal_bias 提取)
  
注入方式:
  不改每位专家 analyze() (每人改一遍重复劳动)
  改为在 WorldModelEngine 汇总专家评分时, 用校准后的 confidence 重新加权
"""

import os, json, datetime, math

AISLEEP = r"D:\AISleepGen_Optimized"
SLEEP_WORLD = os.path.join(AISLEEP, "sleep_world_model.py")
RADAR = r"D:\super_frontier_radar"


class UncertaintyCalibrator:
    """
    不确定性校准器
    
    用法: 在专家评分汇总时调用 calibrate()
    预期: confidence 从 0.78 固定值 → [0.3, 0.9] 动态值
    """
    
    @staticmethod
    def calibrate(
        expert_name: str,
        data_fields: int,
        data_variance: float,
        peer_count: int,
        avg_err: float,
        learning_confidence: str = "low",
        sample_count: int = 0,
    ) -> float:
        """
        计算校准后的 confidence
        
        Args:
            expert_name: 专家名
            data_fields: 数据中填充的字段数 (0-6)
            data_variance: 历史评分波动 (std)
            peer_count: 交叉会诊引用的专家数
            avg_err: personal_bias[3] 历史预测误差 [0.1, 0.3]
            learning_confidence: "high" / "medium" / "low"
            sample_count: 该用户的feedback条数
            
        Returns:
            calibrated_confidence: [0.3, 0.9]
        """
        # 基础值
        base = 0.78
        
        # 1. 数据量惩罚
        data_penalty = 0.0
        if data_fields < 3:
            data_penalty = 0.25  # 数据严重不足
        elif data_fields < 5:
            data_penalty = 0.10
        
        # 2. 数据波动惩罚: 高波动 = 低置信
        var_penalty = 0.0
        if data_variance > 0.3:
            var_penalty = 0.15
        elif data_variance > 0.2:
            var_penalty = 0.08
        
        # 3. 交叉会诊惩罚: 没有peer看法的专家更孤立
        peer_bonus = min(0.05, peer_count * 0.02)
        
        # 4. avg_err 惩罚: 历史误差大 = 低置信
        err_penalty = min(0.20, avg_err * 0.5)
        
        # 5. learning_confidence 调整
        lc_bonus = {"high": 0.05, "medium": 0.0, "low": -0.05}.get(learning_confidence, -0.05)
        
        # 6. 样本量惩罚
        sample_penalty = 0.0
        if sample_count == 0:
            sample_penalty = 0.20  # 无历史反馈
        elif sample_count < 5:
            sample_penalty = 0.10
        
        calibrated = base - data_penalty - var_penalty - err_penalty - sample_penalty + peer_bonus + lc_bonus
        
        return round(max(0.3, min(0.9, calibrated)), 2)
    
    @staticmethod
    def weight_from_confidence(confidence: float) -> float:
        """confidence → 加权权重 (非线性: 高conf权重大)"""
        return round(confidence ** 1.5, 3)
    
    @staticmethod
    def ensemble_weight(
        scores: list,
        confidences: list,
        method: str = "confidence_weighted"
    ) -> dict:
        """
        用校准后的 confidence 加权聚合多位专家评分
        
        Returns:
            {
                "weighted_score": float,
                "ensemble_confidence": float,
                "lowest_conf": float,
                "spread": float  # 分歧度
            }
        """
        if not scores:
            return {"weighted_score": 0.5, "ensemble_confidence": 0.3, "spread": 0, "lowest_conf": 0.3}
        
        weights = [UncertaintyCalibrator.weight_from_confidence(c) for c in confidences]
        total_w = sum(weights)
        if total_w == 0:
            return {"weighted_score": sum(scores)/len(scores), "ensemble_confidence": 0.3, "spread": 0, "lowest_conf": 0.3}
        
        weighted = sum(s * w for s, w in zip(scores, weights)) / total_w
        ensemble_conf = sum(c * w for c, w in zip(confidences, weights)) / total_w
        
        # 分歧度: 评分标准差
        spread = math.sqrt(sum((s - weighted)**2 for s in scores) / len(scores)) if len(scores) > 1 else 0
        
        return {
            "weighted_score": round(weighted, 3),
            "ensemble_confidence": round(ensemble_conf, 3),
            "spread": round(spread, 3),
            "lowest_conf": round(min(confidences), 3),
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="不确定性校准")
    parser.add_argument("--demo", action="store_true", help="演示校准效果")
    parser.add_argument("--patch", action="store_true", help="生成patch建议")
    args = parser.parse_args()
    
    if args.demo:
        print("=== 不确定性校准 Demo ===")
        c = UncertaintyCalibrator.calibrate
        
        cases = [
            # (expert, fields, variance, peers, avgerr, lc_confidence, samples)
            ("ClinicalPsychologist", 6, 0.15, 2, 0.3, "high", 20),   # 多数据,低波动
            ("StressRelaxation",    2, 0.35, 0, 0.3, "low", 1),       # 少数据,高波动
            ("CardiacMonitor",      3, 0.20, 0, 0.3, "low", 0),       # 新用户,无反馈
            ("CBT",                 5, 0.10, 3, 0.1, "high", 50),     # 完美数据
            ("LifeScientist",       4, 0.25, 1, 0.2, "medium", 5),   # 中等
        ]
        
        for name, fields, var, peers, err, lc, samples in cases:
            conf = c(name, fields, var, peers, err, lc, samples)
            weight = UncertaintyCalibrator.weight_from_confidence(conf)
            print(f"  {name:22s}: field={fields} var={var:.2f} peers={peers} err={err} lc={lc} samples={samples}")
            print(f"                    conf={conf} weight={weight}")
            print()
        
        # 演示 ensemble
        print("--- Ensemble 聚合 ---")
        scores = [0.72, 0.65, 0.81, 0.58]
        confs = [0.85, 0.45, 0.88, 0.35]
        result = UncertaintyCalibrator.ensemble_weight(scores, confs)
        for k, v in result.items():
            print(f"  {k}: {v}")
        print(f"  对比简单平均: {round(sum(scores)/len(scores), 3)}")
    
    if args.patch:
        print("=== 注入点分析 ===")
        print("""
注入点: sleep_world_model.py L2238-2250 (10位专家评分汇总处)
当前: confidence 固定 0.78, 简单平均
修改: 
  1. 在每位专家调用前提取 data_fields / variance / peer_count / avg_err
  2. 用 UncertaintyCalibrator.calibrate() 替换固定 0.78
  3. ensemble_weight() 替代简单平均

预期:
  - 数据充分的专家权重↑ (score影响力↑)
  - 数据不足的专家权重↓ (不污染聚合)
  - 总 confidence 动态反映真实不确定性
  - 用户感知: 评分更准确 (其实是不确定时更保守)

风险:
  - 专家间方差可能增大 (高conf专家太主导)
  - 需要边界 case: 所有专家都低conf时不用降权
""")

    if not args.demo and not args.patch:
        parser.print_help()


if __name__ == "__main__":
    main()
