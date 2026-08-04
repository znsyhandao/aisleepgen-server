"""
retrain_model.py - 基于历史数据重新训练 Ridge 模型

用法：
    python retrain_model.py                    # 使用所有有真实评分的数据训练
    python retrain_model.py --alpha 50.0       # 自定义正则化强度
    python retrain_model.py --save-only        # 不进行 LOOCV，只训练并保存
"""

import os
import sys
import pickle
import argparse
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.model_selection import LeaveOneOut

# 路径配置（需与 log_sleep_data.py 一致）
DATA_DIR = "./data"
CSV_PATH = os.path.join(DATA_DIR, "sleep_log.csv")
MODEL_DIR = "./models"
MODEL_PATH = os.path.join(MODEL_DIR, "ridge_model.pkl")
SCALER_PATH = os.path.join(MODEL_DIR, "scaler.pkl")   # 保存标准化器

os.makedirs(MODEL_DIR, exist_ok=True)

# 必须与 log_sleep_data.py 中完全一致
FEATURE_COLS = [
    "fatigue_brow_texture",
    "roi_grad_forehead_jaw",
    "roi_forehead_jaw_ratio",
    "hsv_H_std",
    "hsv_S_p75",
    "freq_high_low_ratio",
    "lab_redness",
    "glcm_contrast"
]

def load_data():
    """加载有真实评分的样本，并检查缺失值"""
    if not os.path.exists(CSV_PATH):
        print(f"❌ 数据文件 {CSV_PATH} 不存在，请先记录数据。")
        sys.exit(1)
    df = pd.read_csv(CSV_PATH)
    # 只保留 real_score 非空的行
    df = df.dropna(subset=["real_score"])
    if len(df) == 0:
        print("❌ 没有包含真实评分的数据，无法训练。")
        sys.exit(1)
    
    # 检查特征列是否都存在
    missing = [col for col in FEATURE_COLS if col not in df.columns]
    if missing:
        print(f"❌ CSV 中缺少特征列: {missing}")
        sys.exit(1)
    
    X = df[FEATURE_COLS].values.astype(float)
    y = df["real_score"].values.astype(float)
    return X, y, df

def loocv_evaluate(X, y, alpha):
    """留一交叉验证，返回平均 R² 和 MAE"""
    n = len(X)
    r2_list = []
    mae_list = []
    loo = LeaveOneOut()
    
    for train_idx, test_idx in loo.split(X):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        
        # 标准化（每折独立，避免数据泄露）
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        model = Ridge(alpha=alpha)
        model.fit(X_train_scaled, y_train)
        y_pred = model.predict(X_test_scaled)[0]
        
        r2_list.append(r2_score([y_test[0]], [y_pred]))
        mae_list.append(abs(y_test[0] - y_pred))
    
    return np.mean(r2_list), np.mean(mae_list)

def train_full_model(X, y, alpha):
    """在全量数据上训练最终模型，并返回标准化器、模型"""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    model = Ridge(alpha=alpha)
    model.fit(X_scaled, y)
    return scaler, model

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--alpha", type=float, default=100.0, help="Ridge 正则化强度")
    parser.add_argument("--save-only", action="store_true", help="只训练不评估")
    args = parser.parse_args()
    
    X, y, df = load_data()
    print(f"📊 加载数据: {len(y)} 个样本，特征数 {X.shape[1]}")
    
    if not args.save_only:
        print(f"🔄 执行留一交叉验证 (alpha={args.alpha})...")
        r2, mae = loocv_evaluate(X, y, args.alpha)
        print(f"✅ LOOCV R² = {r2:.4f}, MAE = {mae:.4f}")
    
    print("🏋️ 在全量数据上重新训练模型...")
    scaler, model = train_full_model(X, y, args.alpha)
    
    # 保存模型和标准化器
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)
    print(f"✅ 模型已保存至 {MODEL_PATH}")
    print(f"✅ 标准化器已保存至 {SCALER_PATH}")
    
    # 输出特征重要性（仅作参考，Ridge 系数受缩放影响，需在标准化空间解释）
    coef = model.coef_
    print("\n📈 特征系数（标准化空间）:")
    for name, c in zip(FEATURE_COLS, coef):
        print(f"   {name}: {c:.4f}")

if __name__ == "__main__":
    main()