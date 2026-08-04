# -*- coding: utf-8 -*-
"""特征随日期漂移检测"""
import pandas as pd, os, numpy as np

FEAT = r'D:\AISleepGen_Optimized\sleep-skin features'
df = pd.read_csv(FEAT+'/facial_features_v9.csv')
fcols = [c for c in df.columns if c not in ['date','file','img_size','face_detected','face_area','gender']]
df = df[df['face_detected'] == True]
daily = df.groupby('date')[fcols].mean().reset_index()
daily = daily.sort_values('date')
dates = daily['date'].astype(str)

# 检查关键特征是否有线性趋势（漂移）
print("特征漂移检测 (线性趋势r)")
print("%-25s %10s %10s" % ('特征', '全量趋势r', 'p值'))
results = []
from scipy.stats import pearsonr, linregress
x = np.arange(len(dates))
for c in fcols:
    vals = daily[c].values
    mask = ~np.isnan(vals)
    if mask.sum() < 10: continue
    r, p = pearsonr(x[mask], vals[mask])
    results.append((abs(r), c, r, p))
    if abs(r) > 0.3:
        print("%-25s %+10.4f %10.4f" % (c[:25], r, p))

# 打印前5个漂移最大的特征
results.sort(reverse=True)
print("\n漂移最大的5个特征:")
for _, c, r, p in results[:5]:
    print("  %s: r=%.4f p=%.4f" % (c[:25], r, p))

# 每日特征变异系数(CV)趋势
print("\n总特征CV(随机噪声)趋势:")
cvs = []
for _, r in daily.iterrows():
    vals = r[fcols].values
    vals = vals[~np.isnan(vals)]
    if len(vals) > 0:
        cvs.append(np.std(vals)/max(abs(np.mean(vals)), 1e-6))
if len(cvs) > 5:
    r, p = pearsonr(np.arange(len(cvs)), cvs)
    print("  CV趋势r=%.4f p=%.4f" % (r, p))
    if abs(r) > 0.3:
        print("  [警告] 特征CV随时间显著变化(%.3f)，可能拍照条件漂移" % r)
