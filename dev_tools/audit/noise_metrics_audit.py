# -*- coding: utf-8 -*-
"""连拍噪声指标分析（PCA burst）"""
import pandas as pd, json, os, numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

FEAT = r'D:\AISleepGen_Optimized\sleep-skin features'
BASE = r'D:\AISleepGen_Optimized\sleep-skin image database'
SR = r'D:\AISleepGen_Optimized\sleep_record\analyzed'

with open(BASE+'/sleep_all_days.json', encoding='utf-8') as f: sd = json.load(f)
df = pd.read_csv(FEAT+'/facial_features_v9.csv')
fcols = [c for c in df.columns if c not in ['date','file','img_size','face_detected','face_area','gender']]
df = df[df['face_detected'] == True]
import re
def get_time(fname):
    parts = fname.replace('.jpg','').replace('IMG_','').split('_')
    for p in parts:
        if len(p)==6 and p.isdigit() and int(p[:2]) in [5,6,7,8,9,21,22,23]: return p
    return '000000'
df['time'] = df['file'].apply(get_time)
df['period'] = df['time'].apply(lambda t: 'morning' if 5<=int(t[:2])<=9 else 'evening' if 21<=int(t[:2])<=23 else 'other')

results=[]
for (date,prd),grp in df[df['period'].isin(['morning','evening'])].groupby(['date','period']):
    if len(grp)<3: continue
    X=grp[fcols].values; mask=~np.isnan(X).any(axis=0); X=X[:,mask]
    if X.shape[1]<2 or X.shape[0]<2: continue
    Xs=StandardScaler().fit_transform(X)
    pca=PCA()
    pca.fit_transform(Xs)
    ds=str(int(date)) if isinstance(date,(int,float)) else str(date)
    sc=None
    if ds in sd: sc=sd[ds].get('sleep_score')
    results.append({'date':ds,'period':prd,'n':len(grp),
        'pc1_var':round(pca.explained_variance_ratio_[0]*100,1),
        'pc2_var':round(pca.explained_variance_ratio_[1]*100,1),
        'noise_ratio':round(pca.explained_variance_ratio_[0]/max(pca.explained_variance_ratio_[1],1e-6),2),
        'sleep_score':sc})

print("连拍噪声指标分析:")
print("%-10s %-8s %5s %8s %8s %10s %8s" % ('日期','时段','张数','PC1%','PC2%','噪声比','评分'))
for r in sorted(results, key=lambda x: x['date']):
    print("%-10s %-8s %5d %8.1f %8.1f %10.2f %8s" % (r['date'],r['period'],r['n'],r['pc1_var'],r['pc2_var'],r['noise_ratio'],r['sleep_score'] or '-'))

# Key correlations
dfr=pd.DataFrame(results).dropna(subset=['sleep_score'])
for c in ['n','pc1_var','pc2_var','noise_ratio']:
    sub=dfr[[c,'sleep_score']].dropna()
    if len(sub)>3: print("\n%s vs 评分: r=%.4f (n=%d)" % (c,sub[c].corr(sub['sleep_score']),len(sub)))
