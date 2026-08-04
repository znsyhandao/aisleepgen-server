# 照片级模型 vs 日聚合模型对比
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
FEATS = ['freq_high_low_ratio', 'hsv_H_std', 'gabor_mean_00', 'gabor_std_00']

df = pd.read_csv(CSV)
df = df[df['face_detected'].astype(str).str.lower().str.strip()=='true'].copy()
df['date'] = df['date'].astype(str).str.strip()
df['gender'] = df['file'].str.contains('_man', case=False).map({True:'M', False:'F'})
dff = df[df['gender']=='F'].copy()

# 过滤 >=2张/天
day_counts = dff.groupby('date').size()
valid = day_counts[day_counts >= 2].index
dff = dff[dff['date'].isin(valid)]
dff['score'] = dff['date'].map(SCORES)
dff = dff.dropna(subset=FEATS + ['score'])

dates = sorted(dff['date'].unique())

print(f'日期数: {len(dates)}')
print(f'照片总数: {len(dff)}')
print()

# === 方案A: 照片级 LOOCV ===
print('=== 方案A: 照片级 Ridge（191张照片作为独立样本）===')
preds, trues = [], []
for te_date in dates:
    tr = dff[dff['date'] != te_date]
    te = dff[dff['date'] == te_date]
    
    X_tr = tr[FEATS].values.astype(float)
    y_tr = tr['score'].values.astype(float)
    X_te = te[FEATS].values.astype(float)
    y_te = te['score'].values.astype(float)
    
    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_te_s = scaler.transform(X_te)
    
    ridge = Ridge(alpha=10).fit(X_tr_s, y_tr)
    # 同一天多张预测取中位数（比均值鲁棒）
    te_pred = np.median(ridge.predict(X_te_s))
    
    preds.append(te_pred)
    trues.append(y_te[0])

r2 = r2_score(trues, preds)
mae = mean_absolute_error(trues, preds)
print(f'  照片级(预测取中位数): R²={r2:+.4f}  MAE={mae:.4f}')

# === 方案B: 照片级 + 增强 ===
print()
print('=== 方案B: 照片级 + 5x增强 ===')
np.random.seed(42)
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
dff_aug = pd.concat([dff, pd.DataFrame(aug_rows)], ignore_index=True)

preds, trues = [], []
for te_date in dates:
    tr = dff_aug[dff_aug['date'] != te_date]
    te = dff[dff['date'] == te_date]  # 验证只用原始
    
    X_tr = tr[FEATS].values.astype(float)
    y_tr = tr['score'].values.astype(float)
    X_te = te[FEATS].values.astype(float)
    
    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    
    ridge = Ridge(alpha=10).fit(X_tr_s, y_tr)
    te_pred = np.median(ridge.predict(scaler.transform(X_te)))
    
    preds.append(te_pred)
    trues.append(te['score'].values[0])

r2 = r2_score(trues, preds)
mae = mean_absolute_error(trues, preds)
print(f'  照片级+5x增强(预测取中位数): R²={r2:+.4f}  MAE={mae:.4f}')

# === 方案C: 照片级 - 取每张照片预测值，不聚合 ===
print()
print('=== 方案C: 照片级 + 5x增强 + 每张照片单独评估 ===')
np.random.seed(42)
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
dff_aug = pd.concat([dff, pd.DataFrame(aug_rows)], ignore_index=True)

all_preds, all_trues = [], []
for te_date in dates:
    tr = dff_aug[dff_aug['date'] != te_date]
    te = dff[dff['date'] == te_date]
    
    X_tr = tr[FEATS].values.astype(float)
    y_tr = tr['score'].values.astype(float)
    
    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    ridge = Ridge(alpha=10).fit(X_tr_s, y_tr)
    
    for _, te_row in te.iterrows():
        X_single = scaler.transform(np.array([[float(te_row[f]) for f in FEATS]]))
        pred = ridge.predict(X_single)[0]
        all_preds.append(pred)
        all_trues.append(te_row['score'])

r2 = r2_score(all_trues, all_preds)
mae = mean_absolute_error(all_trues, all_preds)
print(f'  照片级(每张独立预测, 共{len(all_preds)}次): R²={r2:+.4f}  MAE={mae:.4f}')
