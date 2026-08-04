# 照片-标签错位分析
# 所有照片都是 20:xx 拍的（睡前）
# 目前 label 用的是当天日期的评分（对应"今早起床的睡眠质量"）
# 但睡前拍的脸，应该预测的是"今晚的睡眠质量"（即明天的评分）

import numpy as np, pandas as pd, sys, re, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error

CSV = r'D:/AISleepGen_Optimized/sleep-skin features/facial_features_v9.csv'
SCORES = {
    '20260418':3,'20260419':8,'20260420':8,'20260421':6,'20260422':5,'20260423':7,'20260424':7,
    '20260425':4,'20260427':5,'20260428':3,'20260429':7,'20260430':4,
    '20260501':5,'20260502':5,'20260503':7,'20260504':5,'20260505':6,
    '20260506':4,'20260507':5,'20260508':4,'20260509':4,'20260510':7,
}
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

print('=== 照片时间分布 ===')
for d in sorted(df['date'].unique()):
    rows = df[(df['date']==d) & (df['gender']=='F')]
    hours = rows['hour'].dropna()
    print(f'  {d} (评分={SCORES.get(d,"?")}): {len(rows)}张, 时间={sorted(hours.tolist())}')

# 错位后的评分映射
# 20260418 20:xx 拍 → 预测 20260419 的评分 = 8
# 20260419 20:xx 拍 → 预测 20260420 的评分 = 8
# ...
# 最后一天(20260510) 20:xx 拍 → 没有明天的评分了
SHIFTED = {}
dates = sorted(SCORES.keys())
for i, d in enumerate(dates):
    if i + 1 < len(dates):
        SHIFTED[d] = SCORES[dates[i + 1]]
    else:
        SHIFTED[d] = None  # 最后一天无下一日评分

print()
print('=== 评分错位对比 ===')
for d in dates:
    orig = SCORES[d]
    shifted = SHIFTED[d]
    diff = shifted - orig if shifted else None
    if diff != 0:
        print(f'  {d}: 原评分={orig} → 错位={shifted} 差异={diff}') if shifted else print(f'  {d}: 原评分={orig} → 错位=无')
    else:
        print(f'  {d}: 原评分={orig} → 错位={shifted} (不变)')

# === 用错位评分跑 Ridge ===
print()
print('=== Ridge alpha=10 + 5x增强 + 错位评分 ===')
dff = df[df['gender']=='F'].copy()
dff['score'] = dff['date'].map(SHIFTED)
dff = dff[dff['score'].notna()].copy()

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
dfa = pd.concat([dff, pd.DataFrame(aug_rows)], ignore_index=True)

daily = dfa.groupby('date')[FEATS].mean().dropna()
daily['score'] = daily.index.map(SHIFTED)
daily = daily.dropna()
dates = sorted(daily.index.tolist())

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
print(f'  错位评分: {len(dates)}天  R²={r2:+.4f}  MAE={mae:.4f}')
print()
print(f'  {"日期":>8s} {"真实(错位)":>10s} {"预测":>6s} {"偏差":>6s}')
for i, d in enumerate(dates):
    print(f'  {d:>8s} {trues[i]:>10.0f} {preds[i]:>6.2f} {preds[i]-trues[i]:>+6.2f}')
