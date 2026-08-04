# -*- coding: utf-8 -*-
"""数据质量审计报告"""
import pandas as pd, json, os, numpy as np

FEAT = r'D:\AISleepGen_Optimized\sleep-skin features'
BASE = r'D:\AISleepGen_Optimized\sleep-skin image database'
SR = r'D:\AISleepGen_Optimized\sleep_record'
ANL = os.path.join(SR, 'analyzed')

print("="*50)
print("数据质量审计报告")
print("="*50)

# 1. 面部特征
df = pd.read_csv(FEAT + '/facial_features_v9.csv')
total = len(df)
detected = df['face_detected'].sum()
print("\n1. 面部特征 (facial_features_v9.csv)")
print("   总行数: %d" % total)
print("   人脸检测通过: %d (%.0f%%)" % (detected, detected/total*100))

by_date = df.groupby('date')['face_detected'].agg(['count','sum'])
by_date['pct'] = by_date['sum']/by_date['count']*100
low = by_date[by_date['pct'] < 60]
print("   检测率<60%%的日期: %d天" % len(low))
for d,r in low.iterrows():
    print("     %s: %d张/%d检测 (%.0f%%)" % (d, r['sum'], r['count'], r['pct']))

# 2. 评分覆盖
with open(BASE+'/sleep_all_days.json', encoding='utf-8') as f: sd = json.load(f)
scores = {k: v.get('sleep_score') for k,v in sd.items() if v.get('sleep_score')}
print("\n2. 睡眠评分覆盖")
print("   有评分天数: %d" % len(scores))
print("   评分范围: %.0f-%.0f" % (min(scores.values()), max(scores.values())))
print("   均值±标准差: %.1f±%.1f" % (np.mean(list(scores.values())), np.std(list(scores.values()))))

# 3. 音频分析
m4a = sorted([f for f in os.listdir(SR) if f.endswith('.m4a')])
ana = sorted([f.replace('_analysis.json','') for f in os.listdir(ANL) if f.endswith('_analysis.json')])
print("\n3. 音频分析覆盖")
print("   原始m4a: %d" % len(m4a))
print("   分析json: %d" % len(ana))
missing = [f for f in m4a if f.replace('.m4a','') not in str(ana)]
if missing:
    print("   未分析: %d个" % len(missing))
    for f in missing[:5]:
        sz = os.path.getsize(os.path.join(SR, f))/1e6
        print("     %s (%.0fMB)" % (f, sz))
else:
    print("   全覆盖 ✓")

# 4. 特征NaN检查
feat_cols = [c for c in df.columns if c not in ['date','file','img_size','face_detected','face_area','gender']]
nan_counts = df[feat_cols].isna().sum()
bad = nan_counts[nan_counts > total*0.1]
if len(bad) > 0:
    print("\n4. NaN特征 (>=10%%空值)")
    for c,v in bad.items():
        print("   %s: %.0f个空值 (%.0f%%)" % (c, v, v/total*100))

print("\n审计完成")
