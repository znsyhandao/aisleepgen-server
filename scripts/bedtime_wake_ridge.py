# -*- coding: utf-8 -*-
"""
睡前-睡后差值 Ridge 模型
使用 pre-post 差值特征（睡前特征 → 睡后特征的变化量）预测睡眠质量
比绝对值特征更鲁棒（差分掉个体不变噪声）

用法:
  python bedtime_wake_ridge.py
  
输出:
  - 打印 LOOCV 结果
  - 保存 bedtime_wake_ridge_model.json（当数据 >= 5 组时）
"""

import os, sys, json, warnings, re
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error

BASE = r'D:\AISleepGen_Optimized'
CSV = os.path.join(BASE, 'sleep-skin features', 'facial_features_v9.csv')
SCORES = {'20260418':3,'20260419':8,'20260420':8,'20260421':6,'20260422':5,'20260423':7,'20260424':7,
          '20260425':4,'20260427':5,'20260428':3,'20260429':7,'20260430':4,
          '20260501':5,'20260502':5,'20260503':7,'20260504':5,'20260505':6,
          '20260506':4,'20260507':5,'20260508':4,'20260509':4,'20260510':7}
FEATS = ['freq_high_low_ratio', 'hsv_H_std', 'gabor_mean_00', 'gabor_std_00']

def get_hour(fname):
    m = re.search(r'_(\d{6})\.jpg', fname)
    return int(m.group(1)[:2]) if m else None

def main():
    df = pd.read_csv(CSV, low_memory=False)
    df = df[df['face_detected'].astype(str).str.lower().str.strip()=='true'].copy()
    df['date'] = df['date'].astype(str).str.strip()
    df['gender'] = df['file'].str.contains('_man', case=False).map({True:'M', False:'F'})
    dff = df[df['gender']=='F'].copy()
    dff['hour'] = dff['file'].apply(get_hour)
    
    # 对每个日期标记睡前(>=18点) / 睡后(5-12点)
    dff['phase'] = 'other'
    dff.loc[dff['hour'] >= 18, 'phase'] = 'bedtime'
    dff.loc[(dff['hour'] >= 5) & (dff['hour'] < 12), 'phase'] = 'wake'
    
    # 跨天配对：X日晚间睡前 → X+1日早晨睡后
    dates = sorted(dff['date'].unique())
    pairs = []
    
    for i, d in enumerate(dates):
        if i + 1 >= len(dates):
            break
        d_next = dates[i+1]
        
        bedtime = dff[(dff['date']==d) & (dff['phase']=='bedtime')]
        wake = dff[(dff['date']==d_next) & (dff['phase']=='wake')]
        
        if len(bedtime) >= 1 and len(wake) >= 1:
            bt = bedtime[FEATS].astype(float).mean()
            wk = wake[FEATS].astype(float).mean()
            diff = wk - bt
            
            row = {'date': d_next}
            for f in FEATS:
                row[f'{f}_diff'] = diff[f]
            pairs.append(row)
    
    if len(pairs) == 0:
        print('没有睡前-睡后对照数据')
        print('提示: 每晚 22:xx 拍睡前照，次日 7:xx 拍睡后照')
        print('      睡前照放在当日目录，睡后照放在次日目录')
        return
    
    print(f'睡前-睡后对照: {len(pairs)} 组')
    for p in pairs:
        score = SCORES.get(p['date'], '?')
        print(f'  配对 → {p["date"]} (评分={score})')
    
    if len(pairs) < 5:
        print(f'\n数据量不足({len(pairs)} < 5)，无法训练可靠的 Ridge 模型')
        print('继续积累数据...')
        return
    
    # 差值 Ridge LOOCV
    diff_feats = [f'{f}_diff' for f in FEATS]
    daily = pd.DataFrame(pairs)
    daily['score'] = daily['date'].map(SCORES)
    daily = daily[daily['score'].notna()].copy()
    dates = daily['date'].tolist()
    
    preds, trues = [], []
    for te_idx in range(len(dates)):
        tr_mask = np.arange(len(dates)) != te_idx
        X_tr = daily.iloc[tr_mask][diff_feats].values.astype(float)
        X_te = daily.iloc[te_idx:te_idx+1][diff_feats].values.astype(float)
        y_tr = daily.iloc[tr_mask]['score'].values.astype(float)
        y_te = daily.iloc[te_idx]['score']
        
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_te_s = scaler.transform(X_te)
        
        ridge = Ridge(alpha=10).fit(X_tr_s, y_tr)
        preds.append(ridge.predict(X_te_s)[0])
        trues.append(y_te)
    
    r2 = r2_score(trues, preds)
    mae = mean_absolute_error(trues, preds)
    
    print(f'\n{"="*50}')
    print(f'  睡前-睡后差值 Ridge LOOCV')
    print(f'{"="*50}')
    print(f'  样本: {len(dates)} 组对照')
    print(f'  R²={r2:+.4f}  MAE={mae:.4f}')
    print()
    for i, d in enumerate(dates):
        print(f'  {d}: 真实={trues[i]:.0f}  预测={preds[i]:.2f}  偏差={preds[i]-trues[i]:+.2f}')
    
    # 保存模型（当数据足够）
    scaler_final = StandardScaler()
    X_final = scaler_final.fit_transform(daily[diff_feats].values.astype(float))
    ridge_final = Ridge(alpha=10).fit(X_final, daily['score'].values.astype(float))
    
    model = {
        'version': 'bedtime_wake_diff_v1',
        'features': diff_feats,
        'scaler_mean': [round(float(v), 6) for v in scaler_final.mean_],
        'scaler_scale': [round(float(v), 6) for v in scaler_final.scale_],
        'ridge_coefs': [round(float(c), 8) for c in ridge_final.coef_],
        'ridge_intercept': float(ridge_final.intercept_),
        'ridge_alpha': 10,
        'loocv_r2': round(float(r2), 4),
        'loocv_mae': round(float(mae), 4),
        'n_pairs': len(daily),
    }
    
    out = os.path.join(BASE, 'sleep-skin features', 'bedtime_wake_diff_model.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(model, f, ensure_ascii=False, indent=2)
    print(f'\n已保存: {out} ({os.path.getsize(out):,}B)')

if __name__ == '__main__':
    main()
