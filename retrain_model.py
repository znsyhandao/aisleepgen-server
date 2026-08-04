# -*- coding: utf-8 -*-
"""
retrain_model.py — 基于历史数据重新训练 Ridge 模型
每次有新的真实评分反馈后运行，用 log_sleep_data.py 积累的数据增量更新 Ridge 权重。

突变动力学：模型参数在时间上渐进更新，不搞一次性大改。
"""

import os, json, sys
import warnings
warnings.filterwarnings('ignore')

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import LeaveOneOut
from sklearn.metrics import r2_score, mean_absolute_error

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

# 导入日志模块
from log_sleep_data import get_training_data, get_stats

# 特征顺序（与 face_analyzer 的 _extract 返回一致）
FEATURE_NAMES = [
    'roi_grad_forehead_jaw', 'roi_forehead_jaw_ratio',
    'hsv_H_std', 'freq_high_low_ratio',
    'hsv_S_mean', 'roi_forehead_L',
    'gabor_mean_00', 'gabor_std_00',
]


def retrain(alpha=100.0):
    """
    基于已标真实分的数据重新训练 Ridge 模型。
    
    参数:
        alpha: float, Ridge 正则化强度（越大越保守）
    
    返回: dict 训练结果
    """
    X_raw, y, dates = get_training_data()
    X = np.array(X_raw, dtype=float)
    y = np.array(y, dtype=float)
    
    if len(X) < 5:
        return {
            'status': 'insufficient_data',
            'n_samples': len(X),
            'message': f'至少需要5个有真实评分的数据点，当前{len(X)}个'
        }
    
    if X.shape[1] != len(FEATURE_NAMES):
        return {
            'status': 'feature_mismatch',
            'expected': len(FEATURE_NAMES),
            'got': X.shape[1],
            'message': '特征维度不匹配'
        }
    
    # 标准化 + LOOCV
    scaler = StandardScaler()
    
    loocv_preds, loocv_trues = [], []
    for i in range(len(X)):
        tr_idx = [j for j in range(len(X)) if j != i]
        te_idx = [i]
        X_tr = scaler.fit_transform(X[tr_idx])
        X_te = scaler.transform(X[te_idx])
        model = Ridge(alpha=alpha, random_state=42)
        model.fit(X_tr, y[tr_idx])
        loocv_preds.append(float(model.predict(X_te)[0]))
        loocv_trues.append(float(y[te_idx][0]))
    
    loocv_preds = np.array(loocv_preds)
    loocv_trues = np.array(loocv_trues)
    loocv_r2 = r2_score(loocv_trues, loocv_preds)
    loocv_mae = mean_absolute_error(loocv_trues, loocv_preds)
    
    # 最终模型（全量数据）
    X_scaled = scaler.fit_transform(X)
    final_model = Ridge(alpha=alpha, random_state=42)
    final_model.fit(X_scaled, y)
    train_preds = final_model.predict(X_scaled)
    train_r2 = r2_score(y, train_preds)
    train_mae = mean_absolute_error(y, train_preds)
    
    # 保存模型
    model_data = {
        'version': 'ridge_v9_8feat_retrained',
        'alpha': alpha,
        'features': FEATURE_NAMES,
        'coefs': [round(float(c), 8) for c in final_model.coef_],
        'intercept': float(final_model.intercept_),
        'scaler_mean': [round(float(m), 6) for m in scaler.mean_],
        'scaler_scale': [round(float(s), 6) for s in scaler.scale_],
        'loocv_r2': round(loocv_r2, 4),
        'loocv_mae': round(loocv_mae, 4),
        'train_r2': round(train_r2, 4),
        'train_mae': round(train_mae, 4),
        'n_samples': len(X),
        'dates': dates,
        'trained_at': __import__('time').strftime('%Y-%m-%d %H:%M:%S'),
    }
    
    # 写入文件
    output_path = os.path.join(BASE, 'sleep-skin features', 'ridge_model_v9.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(model_data, f, ensure_ascii=False, indent=2)
    
    return {
        'status': 'ok',
        'n_samples': len(X),
        'loocv_r2': round(loocv_r2, 4),
        'loocv_mae': round(loocv_mae, 4),
        'train_r2': round(train_r2, 4),
        'train_mae': round(train_mae, 4),
        'output': output_path,
        'coefs': dict(zip(FEATURE_NAMES, [round(float(c), 6) for c in final_model.coef_])),
    }


def auto_retrain_if_needed(min_new_samples=3):
    """
    如果积累的新数据足够，自动触发重训练。
    由 /api/sleep-from-face 在每次预测后检查。
    """
    stats = get_stats()
    total = stats.get('with_feedback', 0)
    
    # 检查上次训练时的样本数
    model_path = os.path.join(BASE, 'sleep-skin features', 'ridge_model_v9.json')
    last_n = 0
    if os.path.exists(model_path):
        try:
            with open(model_path, 'r') as f:
                m = json.load(f)
            last_n = m.get('n_samples', 0)
        except:
            last_n = 0
    
    if total - last_n >= min_new_samples and total >= 5:
        return retrain()
    return {'status': 'skipped', 'n_samples': total, 'last_trained': last_n}


if __name__ == '__main__':
    print('=== retrain_model 测试 ===')
    result = retrain(alpha=100.0)
    if result['status'] == 'ok':
        print(f'训练完成: {result["n_samples"]} 样本')
        print(f'  LOOCV R²={result["loocv_r2"]:.4f} MAE={result["loocv_mae"]:.4f}')
        print(f'  Train R²={result["train_r2"]:.4f} MAE={result["train_mae"]:.4f}')
        for f, c in result['coefs'].items():
            print(f'  {f:30s}: {c:+.6f}')
    else:
        print(f'状态: {result["status"]} - {result["message"]}')
