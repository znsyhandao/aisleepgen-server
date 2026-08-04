# 分析睡前照片 vs 起床后照片的特征差异
import numpy as np, pandas as pd, sys, re, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

CSV = r'D:/AISleepGen_Optimized/sleep-skin features/facial_features_v9.csv'
SCORES = {'20260418':3,'20260419':8,'20260420':8,'20260421':6,'20260422':5,'20260423':7,'20260424':7,'20260425':4,
          '20260428':3,'20260429':7,'20260501':5,'20260502':5,'20260503':7,'20260427':5,'20260504':5,'20260505':6,
          '20260506':4,'20260507':5,'20260508':4,'20260509':4,'20260510':7,'20260430':4}
FEATS = ['roi_grad_forehead_jaw','roi_forehead_jaw_ratio','hsv_H_std',
         'freq_high_low_ratio','hsv_S_mean','roi_forehead_L','gabor_mean_00','gabor_std_00']

df = pd.read_csv(CSV)
df = df[df['face_detected'].astype(str).str.lower().str.strip()=='true'].copy()
df['date'] = df['date'].astype(str).str.strip()
df['gender'] = df['file'].str.contains('_man', case=False).map({True:'M', False:'F'})

# 提取照片时间
def get_hour(fname):
    m = re.search(r'(\d{6})', fname.replace('.jpg',''))
    return int(m.group(1)[:2]) if m else None

df['hour'] = df['file'].apply(get_hour)

# === 看看每天照片的时间分布 ===
print('=== 每天女性照片时间分布 ===')
for d in sorted(df['date'].unique()):
    day = df[(df['date']==d) & (df['gender']=='F')]
    hours = day['hour'].dropna().tolist()
    evening = sum(1 for h in hours if h >= 18)
    morning = sum(1 for h in hours if h < 12)  # 早晨
    midday = sum(1 for h in hours if 12 <= h < 18)
    print(f'  {d}: 共{len(day)}张 早{morning} 午{midday} 晚{evening}  hours={sorted(hours)}')

# === 分析：只留早晨照的照片 ===
print()
print('=== Ridge alpha=10 LOOCV 对比 ===')
for use_only_morning in [False, True]:
    np.random.seed(42)
    dff = df[df['gender']=='F'].copy()
    if use_only_morning:
        # 只留 6-12 点的照片（早晨起床后，非睡前）
        dff = dff[(dff['hour'] >= 6) & (dff['hour'] < 12)].copy()
    
    aug_rows = []
    for _, row in dff.iterrows():
        for _ in range(5):
            aug = row.copy()
            for f in FEATS:
                v = row[f]
                if pd.isna(v) or v == '': continue
                try:
                    val = float(v)
                    noise = val * np.random.normal(1.0, 0.05) + np.random.normal(0, val*0.02)
                    aug[f] = max(noise, 0)
                except: pass
            aug_rows.append(aug)
    dfa = pd.concat([dff, pd.DataFrame(aug_rows)], ignore_index=True)
    
    daily = dfa.groupby('date')[FEATS].mean().dropna()
    daily['score'] = daily.index.map(SCORES)
    daily = daily.dropna()
    dates = daily.index.tolist()
    
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import r2_score, mean_absolute_error
    
    preds, trues = [], []
    for te_idx in range(len(dates)):
        tr_mask = np.arange(len(dates)) != te_idx
        X_tr = daily.iloc[tr_mask][FEATS].values
        X_te = daily.iloc[te_idx:te_idx+1][FEATS].values
        y_tr = daily.iloc[tr_mask]['score'].values
        y_te = daily.iloc[te_idx]['score']
        
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_te_s = scaler.transform(X_te)
        
        ridge = Ridge(alpha=10, random_state=42).fit(X_tr_s, y_tr)
        preds.append(ridge.predict(X_te_s)[0])
        trues.append(y_te)
    
    r2 = r2_score(trues, preds)
    mae = mean_absolute_error(trues, preds)
    label = '仅早晨(6-12点)' if use_only_morning else '所有照片'
    print(f'  {label}: {len(dates)}天  R²={r2:+.4f}  MAE={mae:.4f}')
    if use_only_morning:
        for i, d in enumerate(dates):
            real = trues[i]
            pred = preds[i]
            print(f'    {d}: 真实={real:.0f} 预测={pred:.2f} 偏差={pred-real:+.2f}')

# === 别的方法1：照片级（非日均）Ridge ===
print()
print('=== 照片级 Ridge alpha=10 LOOCV（不聚合到日均值） ===')
dff = df[df['gender']=='F'].copy()
dff = dff[(dff['hour'] >= 6) & (dff['hour'] < 12)].copy()
dff['score'] = dff['date'].map(SCORES)
dff = dff.dropna(subset=FEATS + ['score'])
dates = sorted(dff['date'].unique())

preds, trues = [], []
for te_date in dates:
    tr = dff[dff['date'] != te_date]
    te = dff[dff['date'] == te_date]
    
    # 照片级训练（每张照片一个样本=同一天有多个样本但标签相同）
    X_tr = np.array([[float(v) for v in row[FEATS]] for _, row in tr.iterrows()], dtype=float)
    y_tr = tr['score'].values
    X_te = np.array([[float(v) for v in row[FEATS]] for _, row in te.iterrows()], dtype=float)
    y_te = te['score'].values
    
    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_te_s = scaler.transform(X_te)
    
    ridge = Ridge(alpha=10, random_state=42).fit(X_tr_s, y_tr)
    pred = ridge.predict(X_te_s).mean()  # 同一天多张照片取平均
    trues.append(y_te[0])
    preds.append(pred)

r2 = r2_score(trues, preds)
mae = mean_absolute_error(trues, preds)
print(f'  照片级(无增强): {len(dates)}天  R²={r2:+.4f}  MAE={mae:.4f}')
for i, d in enumerate(dates):
    print(f'    {d}: 真实={trues[i]:.0f} 预测={preds[i]:.2f} 偏差={preds[i]-trues[i]:+.2f}')
