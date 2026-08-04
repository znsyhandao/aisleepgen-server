# 最优配置 Ridge
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
BEST_FEATS = ['freq_high_low_ratio', 'hsv_H_std', 'gabor_mean_00', 'gabor_std_00']

df = pd.read_csv(CSV)
df = df[df['face_detected'].astype(str).str.lower().str.strip()=='true'].copy()
df['date'] = df['date'].astype(str).str.strip()
df['gender'] = df['file'].str.contains('_man', case=False).map({True:'M', False:'F'})
dff = df[df['gender']=='F'].copy()

# 过滤：只保留 >=2 张的天
day_counts = dff.groupby('date').size()
valid = day_counts[day_counts >= 2].index
dff = dff[dff['date'].isin(valid)]

# 数据增强
np.random.seed(42)
aug_rows = []
for _, row in dff.iterrows():
    for _ in range(5):
        aug = row.copy()
        for f in BEST_FEATS:
            v = row[f]
            if pd.isna(v) or v == '': continue
            try:
                val = float(v)
                noise = val * np.random.normal(1.0, 0.05) + np.random.normal(0, val*0.02)
                aug[f] = max(noise, 0)
            except: pass
        aug_rows.append(aug)
dfa = pd.concat([dff, pd.DataFrame(aug_rows)], ignore_index=True)

daily = dfa.groupby('date')[BEST_FEATS].mean().dropna()
daily['score'] = daily.index.map(SCORES)
daily = daily.dropna()
dates = daily.index.tolist()

preds, trues = [], []
for te_idx in range(len(dates)):
    tr_mask = np.arange(len(dates)) != te_idx
    X_tr = daily.iloc[tr_mask][BEST_FEATS].values.astype(float)
    X_te = daily.iloc[te_idx:te_idx+1][BEST_FEATS].values.astype(float)
    y_tr = daily.iloc[tr_mask]['score'].values.astype(float)
    y_te = daily.iloc[te_idx]['score']
    s = StandardScaler()
    ridge = Ridge(alpha=10).fit(s.fit_transform(X_tr), y_tr)
    preds.append(ridge.predict(s.transform(X_te))[0])
    trues.append(y_te)

r2 = r2_score(trues, preds)
mae = mean_absolute_error(trues, preds)
print(f'最优配置: >=2张/天 + 4特征 + 5x增强 + alpha=10')
print(f'结果: {len(dates)}天  R²={r2:+.4f}  MAE={mae:.4f}')
print()
for i, d in enumerate(dates):
    print(f'  {d}: 真实={trues[i]:.0f} 预测={preds[i]:.2f} 偏差={preds[i]-trues[i]:+.2f}')
