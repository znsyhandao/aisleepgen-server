import numpy as np, pandas as pd, sys, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error

BASE = r'D:/AISleepGen_Optimized'
CSV = BASE + '/sleep-skin features/facial_features_v9.csv'
SCORES = {'20260418':3,'20260419':8,'20260420':8,'20260421':6,'20260422':5,'20260423':7,'20260424':7,'20260425':4,
          '20260428':3,'20260429':7,'20260501':5,'20260502':5,'20260503':7,'20260427':5,'20260504':5,'20260505':6,
          '20260506':4,'20260507':5,'20260508':4,'20260509':4,'20260510':7,'20260430':4}
FEATS = ['roi_grad_forehead_jaw','roi_forehead_jaw_ratio','hsv_H_std',
         'freq_high_low_ratio','hsv_S_mean','roi_forehead_L','gabor_mean_00','gabor_std_00']

df = pd.read_csv(CSV)
df = df[df['face_detected'].astype(str).str.lower().str.strip()=='true'].copy()
df['date'] = df['date'].astype(str).str.strip()
df['gender'] = df['file'].str.contains('_man', case=False).map({True:'M', False:'F'})
df['score'] = df['date'].map(SCORES).astype(float)
df = df[df['score'].notna()].copy()

np.random.seed(42)
aug_rows = []
for _, row in df.iterrows():
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
df_aug = pd.concat([df, pd.DataFrame(aug_rows)], ignore_index=True)

daily = df_aug[df_aug['gender']=='F'].groupby('date')[FEATS].mean().dropna()
daily['score'] = daily.index.map(SCORES)
daily = daily.dropna()
dates = daily.index.tolist()

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
    pred = ridge.predict(X_te_s)[0]
    preds.append(pred); trues.append(y_te)

print(f'Ridge(alpha=10, 5x特征级增强): R²={r2_score(trues, preds):+.4f} MAE={mean_absolute_error(trues, preds):.4f}')
print()
print('逐日对比:')
for i, d in enumerate(dates):
    print(f'  {d}  真实={trues[i]:.0f}  预测={preds[i]:.2f}  偏差={preds[i]-trues[i]:+.2f}')
