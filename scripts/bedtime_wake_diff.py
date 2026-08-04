# 睡前-睡后差值特征
import numpy as np, pandas as pd, sys, warnings, re
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
FEATS = ['roi_grad_forehead_jaw','roi_forehead_jaw_ratio','hsv_H_std',
         'freq_high_low_ratio','hsv_S_mean','roi_forehead_L','gabor_mean_00','gabor_std_00']

df = pd.read_csv(CSV)
df = df[df['face_detected'].astype(str).str.lower().str.strip()=='true'].copy()
df['date'] = df['date'].astype(str).str.strip()
df['gender'] = df['file'].str.contains('_man', case=False).map({True:'M', False:'F'})
dff = df[df['gender']=='F'].copy()

# 提取时间（小时），区分睡前(18-23点)和睡后(5-12点)
def get_hour(fname):
    m = re.search(r'(\d{6})', fname.replace('.jpg',''))
    return int(m.group(1)[:2]) if m else None

dff['hour'] = dff['file'].apply(get_hour)

# 对每张照片分类
dff['phase'] = ''
dff.loc[dff['hour'] >= 18, 'phase'] = 'bedtime'    # 睡前照
dff.loc[(dff['hour'] >= 5) & (dff['hour'] < 12), 'phase'] = 'wake'  # 起床照

# 看看分布
print('=== 照片时段分布 ===')
for d in sorted(dff['date'].unique()):
    day = dff[dff['date']==d]
    bt = len(day[day['phase']=='bedtime'])
    wk = len(day[day['phase']=='wake'])
    unk = len(day) - bt - wk
    score = SCORES.get(d, '?')
    print(f'  {d} (评分={score}): 睡前={bt} 起床={wk} 其他={unk}')

# 生成"睡前→睡后"差值特征
# 对每个"睡前日"，用当天的睡前照片均值 减去 下一天的起床照片均值
# 相当于：4219 起床的脸 - 0418 睡前脸 = 睡眠带来的变化

print()
print('=== 睡前-睡后差值数据集 ===')
dates_sorted = sorted(dff['date'].unique())
diff_rows = []

for i, d in enumerate(dates_sorted):
    # 只对有"次日"的数据
    if i + 1 >= len(dates_sorted):
        break
    d_next = dates_sorted[i + 1]
    
    # 当天睡前照
    bedtime = dff[(dff['date']==d) & (dff['phase']=='bedtime')]
    # 次日睡后照
    wake = dff[(dff['date']==d_next) & (dff['phase']=='wake')]
    
    if len(bedtime) == 0 or len(wake) == 0:
        continue
    
    bt_mean = bedtime[FEATS].astype(float).mean()
    wk_mean = wake[FEATS].astype(float).mean()
    
    # 差值 = 起床 - 睡前（正值=改善↑ 负值=变差↓）
    diff = wk_mean - bt_mean
    
    # 绝对特征也保留
    row_data = {'date': d_next}  # 标签是下一天的睡眠评分
    for f in FEATS:
        row_data[f'{f}_diff'] = diff[f]
        row_data[f'{f}_bt'] = bt_mean[f]
        row_data[f'{f}_wk'] = wk_mean[f]
    
    diff_rows.append(row_data)

df_diff = pd.DataFrame(diff_rows)
print(f'  生成 {len(df_diff)} 个差值样本')
print(f'  列: {sorted(df_diff.columns.tolist())}')

# 用差值特征跑 Ridge
print()
print('=== Ridge LOOCV: 睡前→睡后差值特征 ===')
# 特征集：只用差值
diff_feats = [f'{f}_diff' for f in FEATS]
# 特征集：差值 + 绝对值
all_feats = diff_feats + [f'{f}_bt' for f in FEATS] + [f'{f}_wk' for f in FEATS]

for label, feat_list in [('仅差值(8)', diff_feats), ('差值+原始(24)', all_feats)]:
    np.random.seed(42)
    daily = df_diff.copy()
    daily['score'] = daily['date'].map(SCORES)
    daily = daily[daily['score'].notna()].copy()
    dates = daily['date'].tolist()
    
    if len(daily) < 3:
        print(f'  {label}: 样本太少')
        continue
    
    preds, trues = [], []
    for te_idx in range(len(dates)):
        tr_mask = np.arange(len(dates)) != te_idx
        X_tr = daily.iloc[tr_mask][feat_list].values.astype(float)
        X_te = daily.iloc[te_idx:te_idx+1][feat_list].values.astype(float)
        y_tr = daily.iloc[tr_mask]['score'].values.astype(float)
        y_te = daily.iloc[te_idx]['score']
        s = StandardScaler()
        ridge = Ridge(alpha=10).fit(s.fit_transform(X_tr), y_tr)
        preds.append(ridge.predict(s.transform(X_te))[0])
        trues.append(y_te)
    
    r2 = r2_score(trues, preds)
    mae = mean_absolute_error(trues, preds)
    print(f'  {label}: {len(dates)}天  R²={r2:+.4f}  MAE={mae:.4f}')
    for i, d in enumerate(dates):
        print(f'    {d}: 真实={trues[i]:.0f} 预测={preds[i]:.2f} 偏差={preds[i]-trues[i]:+.2f}')
