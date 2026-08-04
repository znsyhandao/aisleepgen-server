#!/usr/bin/env python3
"""
ml_optimizer.py — LightGBM 自动超参 + 自动重训练 (2026-07-06)

三件事:
  A. LightGBM 超参搜索 (贝叶斯/网格)
  B. 新 feedback 自动重训练
  C. 特征扩展

集成: 心跳阶段2, 每次有新增feedback时触发
"""

import os, json, datetime, pickle
import numpy as np
import lightgbm as lgb

AISLEEP = r"D:\AISleepGen_Optimized"
FEEDBACK_PATH = os.path.join(AISLEEP, "data", "feedback.json")
CAL_PATH = os.path.join(AISLEEP, "data", "calibration.json")
MODEL_DIR = os.path.join(AISLEEP, "data", "ml_models")
MODEL_PATH = os.path.join(MODEL_DIR, "expert_corrector.pkl")
RADAR = r"D:\super_frontier_radar"


class MLOptimizer:
    def __init__(self):
        self.model = None
        self.last_trained = None
        self.last_sample_count = 0
        self._load_state()
        self._load_model()
    
    def _load_state(self):
        """加载训练状态"""
        state_path = os.path.join(MODEL_DIR, "train_state.json")
        if os.path.exists(state_path):
            try:
                state = json.load(open(state_path, "r", encoding="utf-8"))
                self.last_trained = state.get("last_trained")
                self.last_sample_count = state.get("samples", 0)
            except:
                pass
    
    def _save_state(self, samples, r2, params):
        state = {
            "last_trained": datetime.datetime.now().isoformat(),
            "samples": samples,
            "r2": r2,
            "params": params,
        }
        json.dump(state, open(os.path.join(MODEL_DIR, "train_state.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    
    def _load_model(self):
        if os.path.exists(MODEL_PATH):
            try:
                with open(MODEL_PATH, "rb") as f:
                    self.model = pickle.load(f)
            except:
                self.model = None
    
    def _get_training_data(self):
        """提取训练数据"""
        feedback = json.load(open(FEEDBACK_PATH, "r", encoding="utf-8"))
        if not isinstance(feedback, list):
            return [], []
        
        cal = json.load(open(CAL_PATH, "r", encoding="utf-8"))
        coefs = cal.get("_regression_coefs", {})
        
        X, y = [], []
        for fb in feedback:
            if not isinstance(fb, dict):
                continue
            rating = fb.get("rating")
            if rating is None:
                continue
            
            features = [
                fb.get("wm_score_at_time", 50) / 100.0,
                fb.get("sleep_latency", 30) / 120.0,
                fb.get("awake_times", 1) / 10.0,
                fb.get("total_duration", 7) / 10.0,
                fb.get("stress_level", 5) / 10.0,
                1.0 if fb.get("pain") else 0.0,
                # 评分趋势: 最近3条/所有
                coefs.get("wm_score", 0),
                coefs.get("latency", 0),
                coefs.get("awake", 0),
                coefs.get("duration", 0),
                coefs.get("stress", 0),
                coefs.get("pain_flag", 0),
                # 扩展特征 3个
                fb.get("happy_ratio", 0.5),
                fb.get("pain_penalty_base", 0.1),
                1.0 if fb.get("awake_times", 0) >= 3 else 0.0,  # 频繁夜醒
            ]
            X.append(features)
            y.append(rating / 5.0)
        
        return X, y
    
    def hyperopt_search(self):
        """搜索最优超参 (有限网格, 不依赖外部库)"""
        X, y = self._get_training_data()
        if len(X) < 10:
            return {"error": f"样本不足: {len(X)}"}
        
        X_arr = np.array(X, dtype=float)
        y_arr = np.array(y, dtype=float)
        
        # 网格搜索
        best_r2 = -1
        best_params = None
        
        # 只搜3个关键参数: 树数/叶数/学习率
        configs = [
            {"num_leaves": 4, "learning_rate": 0.03, "num_boost_round": 50},
            {"num_leaves": 4, "learning_rate": 0.05, "num_boost_round": 80},
            {"num_leaves": 6, "learning_rate": 0.03, "num_boost_round": 80},
            {"num_leaves": 6, "learning_rate": 0.05, "num_boost_round": 100},
            {"num_leaves": 8, "learning_rate": 0.03, "num_boost_round": 100},
            {"num_leaves": 8, "learning_rate": 0.05, "num_boost_round": 120},
            {"num_leaves": 10, "learning_rate": 0.02, "num_boost_round": 100},
            {"num_leaves": 10, "learning_rate": 0.05, "num_boost_round": 150},
            {"num_leaves": 12, "learning_rate": 0.03, "num_boost_round": 120},
        ]
        
        for params in configs:
            ds = lgb.Dataset(X_arr, y_arr)
            base_params = {
                "objective": "regression",
                "metric": "rmse",
                "min_data_in_leaf": 3,
                "verbosity": -1,
            }
            base_params.update(params)
            try:
                model = lgb.train(base_params, ds, num_boost_round=params["num_boost_round"])
                preds = model.predict(X_arr)
                ss_res = sum((y_arr - preds)**2)
                ss_tot = sum((y_arr - np.mean(y_arr))**2)
                r2 = 1 - ss_res / max(ss_tot, 1e-10)
                
                if r2 > best_r2:
                    best_r2 = r2
                    best_params = params
            except:
                continue
        
        return {"best_r2": round(best_r2, 3), "best_params": best_params, "n_configs": len(configs)}
    
    def train_with_params(self, params=None):
        """用指定超参训练并保存"""
        X, y = self._get_training_data()
        if len(X) < 10:
            return {"error": f"样本不足: {len(X)}"}
        
        X_arr = np.array(X, dtype=float)
        y_arr = np.array(y, dtype=float)
        
        default_params = {
            "objective": "regression",
            "metric": "rmse",
            "num_leaves": 8,
            "learning_rate": 0.05,
            "min_data_in_leaf": 3,
            "verbosity": -1,
        }
        if params:
            default_params.update(params)
        
        ds = lgb.Dataset(X_arr, y_arr)
        model = lgb.train(default_params, ds, num_boost_round=100)
        
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f)
        self.model = model
        
        preds = model.predict(X_arr)
        ss_res = sum((y_arr - preds)**2)
        ss_tot = sum((y_arr - np.mean(y_arr))**2)
        r2 = 1 - ss_res / max(ss_tot, 1e-10)
        
        self._save_state(len(X), r2, default_params)
        return {"samples": len(X), "r2": round(r2, 3), "params": default_params}
    
    def auto_retrain_if_needed(self):
        """新数据到达时自动重训练"""
        feedback = json.load(open(FEEDBACK_PATH, "r", encoding="utf-8"))
        fb = feedback if isinstance(feedback, list) else []
        current_count = len(fb)
        
        if current_count <= self.last_sample_count:
            return {"note": "无新数据", "samples": current_count, "last": self.last_sample_count}
        
        # 有新增 → 重新训练
        result = self.train_with_params()
        
        # 写告警
        try:
            sys.path.insert(0, RADAR)
            from _pending_alerts import PendingAlerts
            pa = PendingAlerts()
            pa.add(
                f"ml_retrain_{datetime.datetime.now().strftime('%Y%m%d')}",
                f"[ML] LightGBM 自动重训练: R²={result.get('r2', '?')} ({current_count}样本)",
                "INFO"
            )
        except:
            pass
        
        # 如果 R² 提升了, 更新 calibration
        try:
            cal = json.load(open(CAL_PATH, "r", encoding="utf-8"))
            old_r2 = cal.get("_regression_score", 0)
            new_r2 = result.get("r2", 0)
            if new_r2 > old_r2:
                cal["_regression_score"] = new_r2
                cal["_ml_correction"] = {
                    "model": "LightGBM",
                    "r2": new_r2,
                    "trained_at": datetime.datetime.now().isoformat(),
                    "samples": current_count,
                }
                json.dump(cal, open(CAL_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        except:
            pass
        
        result["delta_samples"] = current_count - self.last_sample_count
        self.last_sample_count = current_count
        return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ML优化器")
    parser.add_argument("--retrain", action="store_true", help="检查新数据+自动训练")
    parser.add_argument("--hyperopt", action="store_true", help="超参搜索")
    parser.add_argument("--train", action="store_true", help="重新训练")
    args = parser.parse_args()
    
    opt = MLOptimizer()
    
    if args.hyperopt:
        res = opt.hyperopt_search()
        if "error" in res:
            print(f"搜索失败: {res['error']}")
        else:
            print(f"最优 R²: {res['best_r2']}")
            print(f"最优参数: {res['best_params']}")
    
    if args.train or args.retrain:
        if args.hyperopt:
            # 先超参搜索再用最优参数训练
            hp = opt.hyperopt_search()
            if "error" not in hp and hp["best_params"]:
                # 用最优参数重新训练
                base = {"objective": "regression", "metric": "rmse", "min_data_in_leaf": 3, "verbosity": -1}
                base.update(hp["best_params"])
                res = opt.train_with_params(base)
                print(f"超参最优训练: {res['samples']}样本, R²={res['r2']}")
            else:
                print(f"超参搜索失败, 用默认参数: {hp}")
        elif args.retrain:
            res = opt.auto_retrain_if_needed()
            if "delta_samples" in res:
                print(f"自动重训练: +{res['delta_samples']}条 → R²={res['r2']}")
            else:
                print(f"未训练: {res.get('note', '?')}")
        else:
            res = opt.train_with_params()
            print(f"训练: {res['samples']}样本, R²={res['r2']}")


if __name__ == "__main__":
    import sys
    main()
