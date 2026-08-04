# 特征重要性分析 + 异常检测
import numpy as np, pandas as pd, sys, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error

CSV = r'D:/AISleepGen_Optimized/sleep-skin features/facial_features_v9.csv'
SCORES = {'20260418':3,'20260419':8,'20260420':8,'20260421':6,'20260422':5,'20260423':7,'20260424':7,
          '20260425':4,'20260427':5,'20260428':3,'20260429':7,'20260430':4,
          '20260501':5,'20260502':5,'20260503':7,'20260504':5,'20260505':6,
          '20260506':4,'20260507':5,'20260508':4,'20260509':4,'20260510':7}
ALL_FEATS = ['roi_grad_forehead_jaw','roi_forehead_jaw_ratio','hsv_H_std',
         'freq_high_low_ratio','hsv_S_mean','roi_forehead_L','gabor_mean_00','gabor_std_00']

df = pd.read_csv(CSV)
df = df[df['face_detected'].astype(str).str.lower().str.strip()=='true'].copy()
df['date'] = df['date'].astype(str).str.strip()
df['gender'] = df['file'].str.contains('_man', case=False).map({True:'M', False:'F'})
dff = df[df['gender']=='F'].copy()

# === 1. 单特征 Ridge 预测力 ===
print('=== 单特征预测力 ===')
daily = dff.groupby('date')[ALL_FEATS].mean().dropna()
daily['score'] = daily.index.map(SCORES)
daily = daily.dropna()
dates = daily.index.tolist()

for feat in ALL_FEATS:
    X = daily[[feat]].values.astype(float)
    y = daily['score'].values.astype(float)
    preds, trues = [], []
    for te_idx in range(len(dates)):
        tr_mask = np.arange(len(dates)) != te_idx
        X_tr, X_te = X[tr_mask], X[te_idx:te_idx+1]
        y_tr, y_te = y[tr_mask], y[te_idx]
        s = StandardScaler()
        ridge = Ridge(alpha=10).fit(s.fit_transform(X_tr), y_tr)
        preds.append(ridge.predict(s.transform(X_te))[0])
        trues.append(y_te)
    r2 = r2_score(trues, preds)
    mae = mean_absolute_error(trues, preds)
    # 与特征值的相关性
    corr = np.corrcoef(X.flatten(), y)[0, 1]
    print(f'  {feat:28s}: R²={r2:+.4f} MAE={mae:.4f} corr={corr:+.3f}')

# === 2. 照片级分析：异常天数有哪几天 ===
print()
print('=== 每天标准差分析（照片间变异度）===')
for d in sorted(dff['date'].unique()):
    day = dff[dff['date']==d]
    feats = []
    for _, row in day.iterrows():
        fvals = [float(row[f]) for f in ALL_FEATS if row[f] not in (None,'','nan') and not pd.isna(row[f])]
        feats.append(fvals)
    feats = np.array(feats)
    if len(feats) > 1:
        stds = feats.std(axis=0).mean()
    else:
        stds = 0
    score = SCORES.get(d, '?')
    print(f'  {d} (评分={score}): {len(feats)}张  avg_std={stds:.4f}')

# === 3. 照片数过滤：只留>=3张的天，剔除单张噪声 ===
print()
print('=== 照片数>=3张过滤 ===')
for min_photos in [1, 2, 3]:
    np.random.seed(42)
    dff2 = dff.copy()
    # 去掉照片数少于min_photos的天
    day_counts = dff2.groupby('date').size()
    valid_days = day_counts[day_counts >= min_photos].index
    dff2 = dff2[dff2['date'].isin(valid_days)]
    
    aug_rows = []
    for _, row in dff2.iterrows():
        for _ in range(5):
            aug = row.copy()
            for f in ALL_FEATS:
                v = row[f]
                if pd.isna(v) or v == '': continue
                try:
                    val = float(v)
                    noise = val * np.random.normal(1.0, 0.05) + np.random.normal(0, val*0.02)
                    aug[f] = max(noise, 0)
                except: pass
            aug_rows.append(aug)
    dfa = pd.concat([dff2, pd.DataFrame(aug_rows)], ignore_index=True)
    
    daily2 = dfa.groupby('date')[ALL_FEATS].mean().dropna()
    daily2['score'] = daily2.index.map(SCORES)
    daily2 = daily2.dropna()
    dates2 = daily2.index.tolist()
    
    preds, trues = [], []
    for te_idx in range(len(dates2)):
        tr_mask = np.arange(len(dates2)) != te_idx
        X_tr, X_te = daily2.iloc[tr_mask][ALL_FEATS].values, daily2.iloc[te_idx:te_idx+1][ALL_FEATS].values
        y_tr, y_te = daily2.iloc[tr_mask]['score'].values, daily2.iloc[te_idx]['score']
        s = StandardScaler()
        ridge = Ridge(alpha=10).fit(s.fit_transform(X_tr), y_tr)
        preds.append(ridge.predict(s.transform(X_te))[0])
        trues.append(y_te)
    r2 = r2_score(trues, preds)
    print(f'  >= {min_photos}张/天: {len(dates2)}天  R²={r2:+.4f}')

# === 4. 剔除标准差最大的几天（照片间不一致=那天拍得不好） ===
print()
print('=== 剔除高变异天数 ===')
day_std = {}
for d in dff['date'].unique():
    day = dff[dff['date']==d]
    fvals = []
    for _, row in day.iterrows():
        vals = [float(row[f]) for f in ALL_FEATS if row[f] not in (None,'','nan') and not pd.isna(row[f])]
        fvals.append(vals)
    if len(fvals) > 1:
        day_std[d] = np.array(fvals).std(axis=0).mean()
    else:
        day_std[d] = float('inf')

for pct in [0, 20, 40, 60]:  # 剔除最不稳定的百分之... 
    n_remove = max(0, int(len(day_std) * pct / 100))
    worst_days = set(sorted(day_std, key=day_std.get, reverse=True)[:n_remove])
    
    np.random.seed(42)
    dff2 = dff[~dff['date'].isin(worst_days)].copy()
    if len(dff2) == 0: continue
    
    aug_rows = []
    for _, row in dff2.iterrows():
        for _ in range(5):
            aug = row.copy()
            for f in ALL_FEATS:
                v = row[f]
                if pd.isna(v) or v == '': continue
                try:
                    val = float(v)
                    noise = val * np.random.normal(1.0, 0.05) + np.random.normal(0, val*0.02)
                    aug[f] = max(noise, 0)
                except: pass
            aug_rows.append(aug)
    dfa = pd.concat([dff2, pd.DataFrame(aug_rows)], ignore_index=True)
    
    daily2 = dfa.groupby('date')[ALL_FEATS].mean().dropna()
    daily2['score'] = daily2.index.map(SCORES)
    daily2 = daily2.dropna()
    dates2 = daily2.index.tolist()
    if len(dates2) < 3: continue
    
    preds, trues = [], []
    for te_idx in range(len(dates2)):
        tr_mask = np.arange(len(dates2)) != te_idx
        X_tr, X_te = daily2.iloc[tr_mask][ALL_FEATS].values, daily2.iloc[te_idx:te_idx+1][ALL_FEATS].values
        y_tr, y_te = daily2.iloc[tr_mask]['score'].values, daily2.iloc[te_idx]['score']
        s = StandardScaler()
        ridge = Ridge(alpha=10).fit(s.fit_transform(X_tr), y_tr)
        preds.append(ridge.predict(s.transform(X_te))[0])
        trues.append(y_te)
    r2 = r2_score(trues, preds)
    removed = ','.join(sorted(worst_days)[:5])
    print(f'  剔除最差{pct}%({n_remove}天={removed}...): {len(dates2)}天  R²={r2:+.4f}')
