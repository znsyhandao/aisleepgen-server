# -*- coding: utf-8 -*-
"""诊断全量训练：数据是怎么流的、特征是什么、哪里断了"""
import sys, os, json, numpy as np
sys.path.insert(0, r'D:\AISleepGen_Optimized')

PROJECT = r'D:\AISleepGen_Optimized'
FEAT = os.path.join(PROJECT, 'sleep-skin features')
BASE = os.path.join(PROJECT, 'sleep-skin image database')
SR = os.path.join(PROJECT, 'sleep_record/analyzed')

import pandas as pd

# === 1. 睡眠标签 ===
with open(BASE + '/sleep_all_days.json', encoding='utf-8') as f:
    sd = json.load(f)

with_score = [(d, sd[d]['sleep_score']) for d in sorted(sd) if sd[d].get('sleep_score') is not None]
print(f'=== 睡眠标签 ===')
print(f'有评分天数: {len(with_score)}')
scores = [s for _, s in with_score]
print(f'评分分布: min={min(scores)} max={max(scores)} mean={np.mean(scores):.1f} std={np.std(scores):.1f}')
print(f'评分列表: {scores}')
print()

# === 2. 特征矩阵 ===
df = pd.read_csv(FEAT + '/facial_features_v9.csv')
print(f'=== 面部特征 ===')
print(f'总记录: {len(df)}')
print(f'检测到人脸: {df["face_detected"].sum()}/{len(df)}')

fcols = [c for c in df.columns if c not in ['date','file','img_size','face_detected','face_area','gender']]
print(f'特征维数: {len(fcols)}')

# 按日期聚合
daily = df[df['face_detected'] == True].groupby('date')[fcols].mean().reset_index()
print(f'聚合后天数: {len(daily)}')
print(f'聚合覆盖日期: {sorted(daily["date"].astype(str).tolist())}')
print()

# === 3. 音频特征 ===
raw_a = {}
for f in sorted(os.listdir(SR)):
    if not f.endswith('_analysis.json'):
        continue
    with open(SR+'/'+f, encoding='utf-8') as fh:
        d = json.load(fh)
    date = d.get('date')
    dur = d.get('duration_hours', 0)
    if not date or len(date) != 8:
        continue
    if date < '20260505':
        continue
    s = 'night' if dur > 2 else 'morning'
    if date not in raw_a:
        raw_a[date] = {}
    if s not in raw_a[date] or dur > raw_a[date][s][0]:
        raw_a[date][s] = (dur, d)

af = {}
for date, slots in raw_a.items():
    fd = {}
    for s, (dur, d) in slots.items():
        p = s + '_'
        fd[p+'dur'] = dur
        fd[p+'eff'] = d.get('sleep_efficiency', 0)
        for sk in ['snore','breath','movement','silence','stability']:
            sub = d.get(sk, {})
            for k, v in sub.items():
                if isinstance(v, (int, float)) and 'interpretation' not in k:
                    fd[p+sk+'_'+k] = v
    if fd:
        af[date] = fd

print(f'=== 音频特征 ===')
print(f'有音频分析的天数: {len(af)}')
print(f'音频覆盖: {sorted(af.keys())}')
# 看看音频特征维度
if af:
    sample_date = list(af.keys())[0]
    print(f'音频特征维数: {len(af[sample_date])}')
    print(f'音频特征名: {list(af[sample_date].keys())[:10]}')
print()

# === 4. 合并后的最终训练集 ===
rows = []
for _, r in daily.iterrows():
    ds = str(int(r['date'])) if isinstance(r['date'], (int,float)) else str(r['date'])
    if ds not in sd or sd[ds].get('sleep_score') is None:
        continue
    e = {'score': sd[ds]['sleep_score']}
    for c in fcols:
        e['s_'+c] = r[c]
    if ds in af:
        for k, v in af[ds].items():
            if isinstance(v, (int, float)):
                e['a_'+k] = v
    rows.append(e)

df_all = pd.DataFrame(rows)
print(f'=== 最终训练集 ===')
print(f'样本数: {len(df_all)}')
print(f'评分分布: {sorted(df_all["score"].tolist())}')

all_cols = [c for c in df_all.columns if c != 'score' and np.issubdtype(df_all[c].dtype, np.number)]
print(f'总特征数: {len(all_cols)}')
X = df_all[all_cols].fillna(0)
non_zero_cols = X.columns[X.std() > 0].tolist()
zero_std_cols = [c for c in all_cols if c not in non_zero_cols]
print(f'有效特征(方差>0): {len(non_zero_cols)}')
print(f'零方差特征: {len(zero_std_cols)}')

if zero_std_cols:
    print(f'零方差特征示例: {zero_std_cols[:5]}')

# 检查是否真的有音频特征存活
audio_cols = [c for c in non_zero_cols if c.startswith('a_')]
print(f'存活音频特征: {len(audio_cols)}')
face_cols = [c for c in non_zero_cols if c.startswith('s_')]
print(f'存活面部特征: {len(face_cols)}')

print(f'\nX shape: {X.shape}')
print(f'X 非NaN比例: {1 - X[non_zero_cols].isna().sum().sum() / X[non_zero_cols].size:.3f}')

# === 5. 检查特征值与评分的关系（皮尔逊相关系数）===
print(f'\n=== 特征与评分相关系数 Top15 ===')
corrs = []
for c in non_zero_cols:
    mask = ~(X[c].isna() | df_all['score'].isna())
    if mask.sum() > 2:
        r = np.corrcoef(X[c][mask], df_all['score'][mask])[0,1]
        corrs.append((c, r, mask.sum()))

corrs.sort(key=lambda x: abs(x[1]), reverse=True)
for name, r, n in corrs[:15]:
    print(f'  {name:40s} R={r:+.4f}  n={n}')
