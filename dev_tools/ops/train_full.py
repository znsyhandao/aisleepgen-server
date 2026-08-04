# -*- coding: utf-8 -*-
"""全量LOOCV训练——重新训练全量24天模型"""
import sys, os, json, numpy as np, pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import LeaveOneOut
from scipy.stats import pearsonr
import warnings; warnings.filterwarnings('ignore')

PROJECT = r'D:\AISleepGen_Optimized'
FEAT = os.path.join(PROJECT, 'sleep-skin features')
BASE = os.path.join(PROJECT, 'sleep-skin image database')
SR = os.path.join(PROJECT, 'sleep_record/analyzed')

with open(BASE + '/sleep_all_days.json', encoding='utf-8') as f: sd = json.load(f)
df = pd.read_csv(FEAT + '/facial_features_v9.csv')
fcols = [c for c in df.columns if c not in ['date','file','img_size','face_detected','face_area','gender']]
df = df[df['face_detected'] == True]
daily = df.groupby('date')[fcols].mean().reset_index()

raw_a = {}
for f in sorted(os.listdir(SR)):
    if not f.endswith('_analysis.json'): continue
    with open(SR+'/'+f, encoding='utf-8') as fh: d = json.load(fh)
    date = d.get('date'); dur = d.get('duration_hours', 0)
    if not date or len(date) != 8: continue
    if date < '20260505': continue
    s = 'night' if dur > 2 else 'morning'
    if date not in raw_a: raw_a[date] = {}
    if s not in raw_a[date] or dur > raw_a[date][s][0]: raw_a[date][s] = (dur, d)
af = {}
for date, slots in raw_a.items():
    fd = {}
    for s, (dur, d) in slots.items():
        p = s + '_'; fd[p+'dur'] = dur; fd[p+'eff'] = d.get('sleep_efficiency', 0)
        for sk in ['snore','breath','movement','silence','stability']:
            sub=d.get(sk,{})
            for k,v in sub.items():
                if isinstance(v,(int,float)) and 'interpretation' not in k: fd[p+sk+'_'+k]=v
    if fd: af[date]=fd

rows=[]
for _, r in daily.iterrows():
    ds=str(int(r['date'])) if isinstance(r['date'],(int,float)) else str(r['date'])
    if ds not in sd or sd[ds].get('sleep_score') is None: continue
    e={'score':sd[ds]['sleep_score']}
    for c in fcols: e['s_'+c]=r[c]
    if ds in af:
        for k,v in af[ds].items():
            if isinstance(v,(int,float)): e['a_'+k]=v
    rows.append(e)
df_all=pd.DataFrame(rows)
all_cols=[c for c in df_all.columns if c!='score' and np.issubdtype(df_all[c].dtype, np.number)]
X=df_all[all_cols].fillna(0); X=X.loc[:,X.std()>0]; y=df_all['score'].values

loo=LeaveOneOut()
models=[('GBR deep',GradientBoostingRegressor(n_estimators=10,max_depth=1,min_samples_leaf=3,random_state=42))]
for name,model in models:
    preds,truths=[],[]
    for ti,tei in loo.split(X):
        m=model.__class__(**model.get_params())
        m.fit(X.iloc[ti],y[ti]); preds.append(m.predict(X.iloc[tei].values.reshape(1,-1))[0]); truths.append(y[tei][0])
    r,_=pearsonr(preds,truths); rmse=np.sqrt(np.mean((np.array(preds)-np.array(truths))**2))
    w5=sum(1 for i in range(len(preds)) if abs(preds[i]-truths[i])<=5)
    print('LOOCV: R=%.3f RMSE=%.1f +/-5: %d/%d'%(r,rmse,w5,len(preds)))
