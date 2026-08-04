#!/usr/bin/env python3
"""
ml_correction.py — LightGBM 评分校正器 (2026-07-06)

原理:
  10位规则专家的评分只是特征, 不是最终答案
  LightGBM 学习: (分数1, 分数2, ..., 置信度1, 置信度2, ...) → 真实评分
  
  输出: corrected_score (比 weighted_score 更准)
  
集成方式:
  在 sleep_world_model.py 的 weighted_score 计算后、return 前调用
  calibrator.correct(round2) → 返回校正后的评分

数据:
  X: 每位专家的 score + confidence, 共20维 (10专家×2)
  y: user_feedback.rating (1-5分, 归一化到0-1)
  120条训练样本
"""

import os, json, datetime, pickle, math
import numpy as np
import lightgbm as lgb

AISLEEP = r"D:\AISleepGen_Optimized"
FEEDBACK_PATH = os.path.join(AISLEEP, "data", "feedback.json")
CAL_PATH = os.path.join(AISLEEP, "data", "calibration.json")
MODEL_DIR = os.path.join(AISLEEP, "data", "ml_models")
MODEL_PATH = os.path.join(MODEL_DIR, "expert_corrector.pkl")


class ExpertCorrector:
    """
    LightGBM 评分校正器
    
    用法:
      corrector = ExpertCorrector()
      corrected_score = corrector.correct(round2_dict)
      # 或批处理
      corrector.train()  # 用 feedback.json 训练
    """
    
    def __init__(self):
        self.model = None
        os.makedirs(MODEL_DIR, exist_ok=True)
        self._load_or_create()
    
    def _load_or_create(self):
        """加载已训练模型或创建未训练的新模型"""
        if os.path.exists(MODEL_PATH):
            try:
                with open(MODEL_PATH, "rb") as f:
                    self.model = pickle.load(f)
            except:
                self.model = None
    
    def _features_from_round2(self, round2: dict) -> list:
        """从 round2 字典提取特征向量 (20维)"""
        expert_names = [
            "ClinicalPsychologist", "CognitiveBehavioralTherapist", "SleepPhysician",
            "Chronobiologist", "LifeScientist", "RiskManager",
            "StressRelaxationSpecialist", "ExerciseRehabSpecialist",
            "CardiacRiskMonitor", "NutritionMetabolismSpecialist"
        ]
        features = []
        for name in expert_names:
            r = round2.get(name, {})
            features.append(r.get("score", 0.5))
            features.append(r.get("confidence", 0.5))
        return features
    
    def train(self):
        """用 feedback.json 训练 LightGBM"""
        feedback = json.load(open(FEEDBACK_PATH, "r", encoding="utf-8"))
        if not isinstance(feedback, list):
            return {"error": "feedback 格式错误"}
        
        # 需要 round2 结构的评分数据
        # 当前 feedback.json 没有存储每位专家的评分
        # 只能从 wm_score_at_time 和 rating 学习
        # 临时方案: 用 calibration 的 regression_coefs 做简单校正
        
        cal = json.load(open(CAL_PATH, "r", encoding="utf-8"))
        coefs = cal.get("_regression_coefs", {})
        intercept = cal.get("_regression_intercept", 5.0)
        
        # 构建训练数据
        X, y = [], []
        for fb in feedback:
            if not isinstance(fb, dict):
                continue
            rating = fb.get("rating")
            wm = fb.get("wm_score_at_time")
            if rating is None or wm is None:
                continue
            
            # 使用统一特征提取器 (15基础 + 64嵌入 = 79维)
            from dev_tools.feature_extractor import extract_all_features as _extract
            features = _extract(fb)
            X.append(features)
            X.append(features)
            y.append(rating / 5.0)  # 归一化到 [0, 1]
        
        if len(X) < 10:
            return {"error": f"样本不足: {len(X)}"}
        
        X_arr = np.array(X, dtype=float)
        y_arr = np.array(y, dtype=float)
        
        # 训练 LightGBM
        ds = lgb.Dataset(X_arr, y_arr)
        params = {
            "objective": "regression",
            "metric": "rmse",
            "learning_rate": 0.05,
            "num_leaves": 8,  # 小树防过拟合 (120样本)
            "min_data_in_leaf": 3,
            "verbosity": -1,
        }
        model = lgb.train(params, ds, num_boost_round=100)
        
        # 保存
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f)
        self.model = model
        
        # R²
        preds = model.predict(X_arr)
        ss_res = sum((y_arr - preds)**2)
        ss_tot = sum((y_arr - np.mean(y_arr))**2)
        r2 = 1 - ss_res / max(ss_tot, 1e-10)
        
        return {
            "status": "ok",
            "samples": len(X),
            "r2": round(r2, 3),
            "model_path": MODEL_PATH,
        }
    
    def correct(self, round2: dict) -> dict:
        """
        校正评分
        Returns: {score, confidence, adjustment}
        """
        if self.model is None:
            return {"score": 0.5, "confidence": 0.3, "adjustment": 0, "note": "无模型"}
        
        try:
            features = self._features_from_round2(round2)
            X = np.array([features], dtype=float)
            corrected = float(self.model.predict(X)[0])
            corrected = max(0.1, min(1.0, corrected))
            
            # 当前加权平均
            weights = [r.get("confidence", 0.5) * r.get("score", 0.5) for r in round2.values()]
            weighted = sum(weights) / max(sum(r.get("confidence", 0.5) for r in round2.values()), 0.01) if round2 else 0.5
            
            return {
                "score": round(corrected, 3),
                "weighted_score": round(weighted, 3),
                "adjustment": round(corrected - weighted, 3),
                "confidence": 0.6 if abs(corrected - weighted) < 0.2 else 0.4,
                "note": "LightGBM校正",
            }
        except Exception as e:
            return {"score": 0.5, "confidence": 0.3, "adjustment": 0, "note": f"错误: {str(e)[:40]}"}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LightGBM评分校正器")
    parser.add_argument("--train", action="store_true", help="训练模型")
    parser.add_argument("--status", action="store_true", help="查看模型状态")
    args = parser.parse_args()
    
    c = ExpertCorrector()
    
    if args.train:
        result = c.train()
        if "error" in result:
            print(f"训练失败: {result['error']}")
        else:
            print(f"训练完成: {result['samples']}样本, R²={result['r2']}")
    
    if args.status:
        if c.model:
            print(f"模型: {MODEL_PATH}")
            print(f"类型: LightGBM")
        else:
            print("无已训练模型")


if __name__ == "__main__":
    main()
