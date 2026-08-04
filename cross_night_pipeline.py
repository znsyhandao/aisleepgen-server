# -*- coding: utf-8 -*-
"""
跨夜皮肤变化模型管线 — 替代全天均值，使用睡前→睡后变化
每天新数据→自动计算变化→追加到cross-night数据集→更新模型

架构流程:
1. 新照片目录 → 分类evening/morning
2. 匹配前后夜对 → 计算d_特征 = morning - evening_prev
3. 追加到 cross_night_dataset.csv
4. 重新训练跨夜模型
"""
import os, json, pandas as pd, numpy as np
from datetime import datetime
import warnings; warnings.filterwarnings('ignore')

PROJECT = r'D:\AISleepGen_Optimized'
SKIN_DB = os.path.join(PROJECT, 'sleep-skin image database')
FEATURES = os.path.join(PROJECT, 'sleep-skin features')
SCRIPTS = os.path.join(PROJECT, 'scripts')
V9_SCRIPT = os.path.join(SCRIPTS, 'extract_skin_features_v9.py')

CN_DATA = os.path.join(FEATURES, 'cross_night_dataset.csv')
CN_MODEL = os.path.join(FEATURES, 'cross_night_model.json')

def classify_time(fname):
    """从文件名判断时间段"""
    for p in fname.upper().replace('IMG_','').replace('.JPG','').split('_'):
        if len(p) == 6 and p.isdigit():
            h = int(p[:2])
            if 21 <= h <= 23: return 'evening'
            if 5 <= h <= 8: return 'morning'
    return 'other'

def build_cross_night_dataset():
    """从v9特征CSV构建跨夜变化数据集"""
    csv_path = os.path.join(FEATURES, 'facial_features_v9.csv')
    if not os.path.exists(csv_path):
        print("[ERROR] facial_features_v9.csv not found")
        return None, None
    
    df = pd.read_csv(csv_path)
    feat_cols = [c for c in df.columns if c not in ['date','file','img_size','face_detected','face_area','gender']]
    
    # 分类时段
    df['time_slot'] = df['file'].apply(classify_time)
    
    # 按日期+时段聚合(均值)
    agg = df.groupby(['date','time_slot'])[feat_cols].mean().reset_index()
    ev = agg[agg['time_slot'] == 'evening'].copy()
    mo = agg[agg['time_slot'] == 'morning'].copy()
    
    # 交叉配对：今早的morning ⇔ 昨晚的evening
    pairs = []
    for _, mr in mo.iterrows():
        md = int(mr['date'])
        ev_match = ev[ev['date'] == md - 1]
        if len(ev_match) > 0:
            er = ev_match.iloc[0]
            change = {'date': str(md)}
            for c in feat_cols:
                change['d_' + c] = mr[c] - er[c]
            pairs.append(change)
    
    df_cn = pd.DataFrame(pairs)
    print(f"跨夜配对: {len(df_cn)} 对")
    
    # 合并睡眠评分
    sleep_path = os.path.join(SKIN_DB, 'sleep_all_days.json')
    if os.path.exists(sleep_path):
        with open(sleep_path, encoding='utf-8') as f: sd = json.load(f)
        scores = []
        for _, row in df_cn.iterrows():
            ds = row['date']
            scores.append(sd.get(ds, {}).get('sleep_score'))
        df_cn['sleep_score'] = scores
        print(f"有评分的: {df_cn['sleep_score'].notna().sum()} 对")
    
    # 保存
    df_cn.to_csv(CN_DATA, index=False)
    print(f"跨夜数据集保存: {CN_DATA}")
    return df_cn, feat_cols

def train_cross_night_model(df_cn):
    """训练跨夜变化模型"""
    if df_cn is None or len(df_cn) == 0:
        print("[WARN] 无跨夜数据，跳过训练")
        return
    
    from sklearn.linear_model import Ridge, Lasso
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import LeaveOneOut, cross_val_score, KFold
    from scipy.stats import pearsonr
    
    # 只取有评分的行
    df_model = df_cn.dropna(subset=['sleep_score']).copy()
    if len(df_model) < 5:
        print(f"[WARN] 评分数据太少: {len(df_model)}")
        return
    
    feat_cols = [c for c in df_model.columns if c.startswith('d_')]
    X = df_model[feat_cols].fillna(0)
    X = X.loc[:, X.std() > 0]
    y = df_model['sleep_score'].values
    
    print(f"\n=== 跨夜模型训练 ===")
    print(f"样本: {len(X)}, 特征: {X.shape[1]}")
    
    loo = LeaveOneOut()
    models = {
        'Ridge': Ridge(alpha=5.0),
        'Lasso': Lasso(alpha=0.05, max_iter=10000),
        'GBR_deep': GradientBoostingRegressor(n_estimators=10, max_depth=1, min_samples_leaf=3, random_state=42),
    }
    
    best_rmse = 999
    best_name = ''
    results = {}
    
    for name, model in models.items():
        preds, truths = [], []
        for ti, tei in loo.split(X):
            m = model.__class__(**model.get_params())
            m.fit(X.iloc[ti], y[ti])
            preds.append(m.predict(X.iloc[tei].values.reshape(1, -1))[0])
            truths.append(y[tei][0])
        
        r, _ = pearsonr(preds, truths)
        rmse = np.sqrt(np.mean((np.array(preds) - np.array(truths))**2))
        within5 = sum(1 for i in range(len(preds)) if abs(preds[i]-truths[i]) <= 5)
        print(f"  {name:15s} R={r:.3f}  RMSE={rmse:.1f}  +/-5: {within5}/{len(preds)}")
        
        results[name] = {'R': round(r, 3), 'RMSE': round(rmse, 1), 'within5': within5}
        
        if rmse < best_rmse:
            best_rmse = rmse
            best_name = name
    
    # Train best model for feature importance
    if best_name in models:
        m = models[best_name]
        m.fit(X, y)
        importances = sorted(zip(X.columns, m.feature_importances_ if hasattr(m, 'feature_importances_') else abs(m.coef_)), key=lambda x: x[1], reverse=True)
    else:
        importances = []
    
    # Save model results
    model_out = {
        'training_date': datetime.now().isoformat(),
        'n_samples': len(X),
        'n_features': X.shape[1],
        'best_model': best_name,
        'results': results,
        'feature_importance': [{'name': n, 'importance': float(i)} for n, i in importances[:15]]
    }
    with open(CN_MODEL, 'w', encoding='utf-8') as f:
        json.dump(model_out, f, ensure_ascii=False, indent=2)
    
    print(f"\n最佳模型: {best_name} (RMSE={best_rmse:.1f})")
    if 'importances' in dir():
        print("Top跨夜特征:")
        for name, imp in importances[:10]:
            print(f"  {name[:40]:<40} importance={imp:.4f}")

def update_from_new_photos():
    """增量更新：处理新照片目录"""
    today = datetime.now().strftime('%Y%m%d')
    yesterday = (datetime.now().replace(day=datetime.now().day-1)).strftime('%Y%m%d')
    
    # 检查新照片目录
    for d in [today, yesterday]:
        photo_dir = os.path.join(SKIN_DB, d)
        if os.path.isdir(photo_dir) and len(os.listdir(photo_dir)) > 0:
            print(f"新照片: {photo_dir}")
            # 调用v9特征提取
            if os.path.exists(V9_SCRIPT):
                import subprocess, sys
                subprocess.run([sys.executable, V9_SCRIPT], cwd=PROJECT, check=True, timeout=600)
                print("特征提取完成")
    
    # 重新构建跨夜数据集
    df_cn, _ = build_cross_night_dataset()
    train_cross_night_model(df_cn)

if __name__ == '__main__':
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else 'rebuild'
    
    if mode == 'rebuild':
        df_cn, _ = build_cross_night_dataset()
        train_cross_night_model(df_cn)
    elif mode == 'update':
        update_from_new_photos()
    else:
        print(f"用法: python {__file__} [rebuild|update]")
        print("  rebuild: 从已有CSV重建跨夜数据集并训练")
        print("  update: 检查新照片→提取特征→更新数据集→训练")
