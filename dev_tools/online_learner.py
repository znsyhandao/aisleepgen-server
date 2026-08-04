#!/usr/bin/env python3
"""
online_learner.py — 在线学习引擎 (2026-07-06 14:53)

LightGBM 无法增量学习, 但 SGDRegressor 可以。
策略:
  1. 启动时用 LightGBM 的预测作为 baseline
  2. 每次新 feedback 到达: SGDRegressor.partial_fit(X, y)
  3. 不再需要全量重训练

X: 15维特征 (和 LightGBM 一样)
学习策略: 弹性学习率 + 缓冲区批处理

ML 管线:
  ml_correction.py (LightGBM 批训练, 强而慢)
  online_learner.py  (SGD 在线学习, 弱而快, 持续修正)
  ml_optimizer.py    (超参搜索, 定期触发)
"""

import os, json, datetime, pickle
import numpy as np
from sklearn.linear_model import SGDRegressor

AISLEEP = r"D:\AISleepGen_Optimized"
FEEDBACK_PATH = os.path.join(AISLEEP, "data", "feedback.json")
CAL_PATH = os.path.join(AISLEEP, "data", "calibration.json")
MODEL_DIR = os.path.join(AISLEEP, "data", "ml_models")
ONLINE_MODEL_PATH = os.path.join(MODEL_DIR, "online_corrector.pkl")
STATE_PATH = os.path.join(MODEL_DIR, "online_state.json")
RADAR = r"D:\super_frontier_radar"


class OnlineLearner:
    """SGD 在线学习引擎"""
    
    def __init__(self):
        os.makedirs(MODEL_DIR, exist_ok=True)
        self.model = None
        self.last_feedback_id = None
        self.total_updates = 0
        self.recent_rmse = []
        self._load()
    
    def _load(self):
        if os.path.exists(ONLINE_MODEL_PATH):
            try:
                with open(ONLINE_MODEL_PATH, "rb") as f:
                    self.model = pickle.load(f)
            except:
                pass
        if os.path.exists(STATE_PATH):
            try:
                state = json.load(open(STATE_PATH, "r", encoding="utf-8"))
                self.last_feedback_id = state.get("last_feedback_id")
                self.total_updates = state.get("total_updates", 0)
            except:
                pass
        if self.model is None:
            self.model = SGDRegressor(
                loss="squared_error",
                penalty="l2",
                alpha=0.001,
                learning_rate="adaptive",
                eta0=0.01,
                warm_start=False,
                random_state=42,
            )
    
    def _save(self):
        with open(ONLINE_MODEL_PATH, "wb") as f:
            pickle.dump(self.model, f)
        state = {
            "last_feedback_id": self.last_feedback_id,
            "total_updates": self.total_updates,
        }
        json.dump(state, open(STATE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    
    def _extract_features(self, fb: dict) -> list:
        """从单条 feedback 提取特征 (15维)"""
        cal = json.load(open(CAL_PATH, "r", encoding="utf-8"))
        coefs = cal.get("_regression_coefs", {})
        
        return [
            fb.get("wm_score_at_time", 50) / 100.0,
            fb.get("sleep_latency", 30) / 120.0,
            fb.get("awake_times", 1) / 10.0,
            fb.get("total_duration", 7) / 10.0,
            fb.get("stress_level", 5) / 10.0,
            1.0 if fb.get("pain") else 0.0,
            coefs.get("wm_score", 0),
            coefs.get("latency", 0),
            coefs.get("awake", 0),
            coefs.get("duration", 0),
            coefs.get("stress", 0),
            coefs.get("pain_flag", 0),
            fb.get("happy_ratio", 0.5),
            fb.get("pain_penalty_base", 0.1),
            1.0 if fb.get("awake_times", 0) >= 3 else 0.0,
        ]
    
    def ingest(self, fb: dict) -> dict:
        """接收一条新 feedback, 增量学习"""
        rating = fb.get("rating")
        if rating is None:
            return {"note": "无评分, 跳过"}
        
        fid = fb.get("id") or fb.get("_id") or fb.get("timestamp") or str(hash(str(fb)))
        if fid == self.last_feedback_id:
            return {"note": "重复, 跳过"}
        
        features = self._extract_features(fb)
        X = np.array([features], dtype=float)
        y = np.array([rating / 5.0], dtype=float)
        
        try:
            self.model.partial_fit(X, y)
            self.last_feedback_id = fid
            self.total_updates += 1
            
            # 评估
            pred = float(self.model.predict(X)[0])
            pred = max(0.1, min(1.0, pred))
            actual = y[0]
            
            self._save()
            
            return {
                "note": "在线学习",
                "update_count": self.total_updates,
                "pred": round(pred, 3),
                "actual": round(actual, 3),
                "error": round(abs(pred - actual), 3),
            }
        except Exception as e:
            return {"error": str(e)[:50]}
    
    def scan_and_learn(self) -> dict:
        """扫描 feedback.json, 增量学习所有新数据"""
        feedback = json.load(open(FEEDBACK_PATH, "r", encoding="utf-8"))
        fb = feedback if isinstance(feedback, list) else []
        
        learned = 0
        errors = []
        
        for f in fb:
            result = self.ingest(f)
            if "error" in result:
                errors.append(result["error"])
            elif result.get("note") == "在线学习":
                learned += 1
        
        return {
            "learned": learned,
            "total_updates": self.total_updates,
            "errors": errors[:3],
            "model": "SGDRegressor",
        }
    
    def predict(self, features: list) -> float:
        """在线预测 (单条)"""
        if self.model is None or not hasattr(self.model, "coef_"):
            return 0.5
        try:
            X = np.array([features], dtype=float)
            pred = float(self.model.predict(X)[0])
            return max(0.1, min(1.0, pred))
        except:
            return 0.5
    
    def evaluate(self) -> dict:
        """评估在线模型的全量 R²"""
        feedback = json.load(open(FEEDBACK_PATH, "r", encoding="utf-8"))
        fb = feedback if isinstance(feedback, list) else []
        
        if not fb or not hasattr(self.model, "coef_"):
            return {"r2": 0, "samples": 0}
        
        preds, actuals = [], []
        for f in fb:
            rating = f.get("rating")
            if rating is None:
                continue
            features = self._extract_features(f)
            X = np.array([features], dtype=float)
            try:
                pred = float(self.model.predict(X)[0])
                preds.append(max(0.1, min(1.0, pred)))
                actuals.append(rating / 5.0)
            except:
                continue
        
        if len(preds) < 5:
            return {"r2": 0, "samples": len(preds)}
        
        arr_p = np.array(preds)
        arr_a = np.array(actuals)
        ss_res = sum((arr_a - arr_p)**2)
        ss_tot = sum((arr_a - np.mean(arr_a))**2)
        r2 = 1 - ss_res / max(ss_tot, 1e-10)
        
        return {"r2": round(r2, 3), "samples": len(preds)}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="在线学习引擎")
    parser.add_argument("--scan", action="store_true", help="扫描+学习所有新数据")
    parser.add_argument("--eval", action="store_true", help="评估R²")
    args = parser.parse_args()
    
    o = OnlineLearner()
    
    if args.scan:
        res = o.scan_and_learn()
        print(f"在线学习: +{res.get('learned', 0)}条, 总计{res.get('total_updates', 0)}次更新")
    
    if args.eval:
        res = o.evaluate()
        print(f"在线评估: R²={res.get('r2', 0)}, {res.get('samples', 0)}样本")
    
    if not args.scan and not args.eval:
        print("用法: python online_learner.py --scan  # 在线学习")
        print("      python online_learner.py --eval  # 评估R²")


if __name__ == "__main__":
    main()
