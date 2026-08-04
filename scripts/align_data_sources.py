# -*- coding: utf-8 -*-
"""数据科学专家：多源数据对齐与预处理管线
将所有数据源统一对齐到 daily 粒度，生成预处理特征矩阵

数据源:
  1. facial_features_v9.csv — 74列面部特征，503张有人脸
  2. sleep_data_log.json — 手环/用户反馈评分（0-100）
  3. sleep_record/analyzed/*.json — 85条录音分析
  4. skin_change_vs_sleep.json — 早晚皮肤对比（5月9日起）

输出:
  D:\AISleepGen_Optimized\sleep-skin features\aligned_features_v1.csv
  D:\AISleepGen_Optimized\sleep-skin features\aligned_meta_v1.json
"""
import os, sys, json, glob, warnings
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
from datetime import datetime

BASE = 'D:\\AISleepGen_Optimized'
OUTPUT_CSV = os.path.join(BASE, 'sleep-skin features', 'aligned_features_v1.csv')
OUTPUT_META = os.path.join(BASE, 'sleep-skin features', 'aligned_meta_v1.json')
FEATURES_CSV = os.path.join(BASE, 'sleep-skin features', 'facial_features_v9.csv')
LOG_PATH = os.path.join(BASE, 'sleep-skin features', 'sleep_data_log.json')
SKIN_CHANGE_PATH = os.path.join(BASE, 'sleep-skin features', 'skin_change_vs_sleep.json')
ANALYZED_DIR = os.path.join(BASE, 'sleep_record', 'analyzed')

sep = "=" * 70
print(sep)
print("数据科学专家报告：多源数据对齐管线 v1")
print(sep)

# ===== 1. 面部特征 =====
print("\n[1/5] 加载面部特征...")
df_face = pd.read_csv(FEATURES_CSV)
df_face['date_str'] = df_face['date'].astype(str)
detected = df_face[df_face['face_detected'] == True].copy()
print(f"  facial_features_v9.csv: {len(df_face)}行, 检测到人脸{len(detected)}行")
print(f"  覆盖天数: {len(detected['date_str'].unique())}天")

# ===== 2. 录音标签 =====
print("\n[2/5] 加载录音标签...")
analyzed_files = sorted(glob.glob(os.path.join(ANALYZED_DIR, '*_analysis.json')))
analyzed_files = [f for f in analyzed_files if os.path.basename(f).startswith('20')]

audio_agg = {}
for fp in analyzed_files:
    try:
        with open(fp, encoding='utf-8') as f:
            d = json.load(f)
        date_str = os.path.basename(fp)[:8]
        if date_str not in audio_agg:
            audio_agg[date_str] = {'eff': [], 'snore': [], 'stab': [], 'bpm': [], 'movement': []}
        eff = d.get('sleep_efficiency')
        if eff and eff > 0:
            audio_agg[date_str]['eff'].append(eff)
        snore = d.get('snore', {}).get('snore_pct')
        if snore is not None:
            audio_agg[date_str]['snore'].append(snore)
        stab = d.get('stability', {}).get('score')
        if stab is not None:
            audio_agg[date_str]['stab'].append(stab)
        bpm = d.get('breath', {}).get('estimated_bpm')
        if bpm is not None:
            audio_agg[date_str]['bpm'].append(bpm)
        mv = d.get('movement', {}).get('total_movement_min')
        if mv is not None:
            audio_agg[date_str]['movement'].append(mv)
    except:
        pass

audio_summary = {}
for d, v in audio_agg.items():
    audio_summary[d] = {
        'eff_mean': float(np.mean(v['eff'])) if v['eff'] else np.nan,
        'eff_std': float(np.std(v['eff'])) if len(v['eff']) > 1 else 0,
        'snore_mean': float(np.mean(v['snore'])) if v['snore'] else np.nan,
        'stab_mean': float(np.mean(v['stab'])) if v['stab'] else np.nan,
        'bpm_mean': float(np.mean(v['bpm'])) if v['bpm'] else np.nan,
        'movement_min': float(np.mean(v['movement'])) if v['movement'] else np.nan,
        'n_recordings': len(v['eff']),
    }
print(f"  录音分析: {len(analyzed_files)}条, {len(audio_summary)}天")

# ===== 3. 手环/反馈数据 =====
print("\n[3/5] 加载手环/反馈数据...")
if os.path.exists(LOG_PATH):
    with open(LOG_PATH, encoding='utf-8') as f:
        log_data = json.load(f)
    band_summary = {}
    for d, entry in log_data.items():
        rs = entry.get('real_score')
        ps = entry.get('predicted_score')
        if rs is not None or ps is not None:
            band_summary[d] = {
                'real_score': rs if rs is not None and rs > 0 else np.nan,
                'predicted_score': ps if ps is not None else np.nan,
            }
    print(f"  sleep_data_log.json: {len(log_data)}天, 有评分{sum(1 for v in band_summary.values() if not np.isnan(v['real_score']))}天")
else:
    band_summary = {}
    print("  无手环数据")

# ===== 4. 早晚皮肤对比 =====
print("\n[4/5] 加载早晚皮肤对比...")
if os.path.exists(SKIN_CHANGE_PATH):
    with open(SKIN_CHANGE_PATH, encoding='utf-8') as f:
        skin_change = json.load(f)
    skin_summary = {}
    if isinstance(skin_change, list):
        for item in skin_change:
            d = str(item.get('date', ''))
            if d:
                skin_summary[d] = {
                    'bedtime_photos': item.get('b_photos', 0),
                    'wake_photos': item.get('w_photos', 0),
                    'change': item.get('change', {}),
                }
        print(f"  skin_change_vs_sleep.json: {len(skin_change)}天")
    else:
        print(f"  skin_change_vs_sleep.json: dict, keys={list(skin_change.keys())[:5]}")
else:
    skin_summary = {}
    print("  无皮肤对比数据")

# ===== 5. 对齐构建 =====
print("\n[5/5] 构建对齐数据矩阵...")

all_dates = sorted(set(detected['date_str'].unique()) | set(audio_summary.keys()) | set(band_summary.keys()) | set(skin_summary.keys()))

rows = []
for date_str in all_dates:
    row = {'date': date_str}
    sources = []
    if date_str in set(detected['date_str'].unique()):
        sources.append('face')
    if date_str in audio_summary:
        sources.append('audio')
    if date_str in band_summary:
        sources.append('band')
    if date_str in skin_summary:
        sources.append('skin_change')
    row['data_sources'] = '+'.join(sources)
    row['n_sources'] = len(sources)

    day_faces = detected[detected['date_str'] == date_str]
    if len(day_faces) > 0:
        numeric_cols = day_faces.select_dtypes(include=[np.number]).columns
        numeric_cols = [c for c in numeric_cols if c not in ['date', 'face_area', 'total_algorithms']]
        for c in numeric_cols:
            row[c] = float(day_faces[c].mean())  # 保持原始列名，不加前缀
            row[f'{c}_daily_std'] = float(day_faces[c].std()) if day_faces[c].std() > 0 else 0.0
    row['n_faces'] = len(day_faces)

    if date_str in audio_summary:
        for k, v in audio_summary[date_str].items():
            row[f'audio_{k}'] = v if not np.isnan(v) else 0.0
    else:
        for k in ['eff_mean', 'eff_std', 'snore_mean', 'stab_mean', 'bpm_mean', 'movement_min', 'n_recordings']:
            row[f'audio_{k}'] = 0.0

    if date_str in band_summary:
        for k, v in band_summary[date_str].items():
            row[f'band_{k}'] = v if not np.isnan(v) else 0.0
    else:
        row['band_real_score'] = 0.0
        row['band_predicted_score'] = 0.0

    if date_str in skin_summary:
        s = skin_summary[date_str]
        row['skin_bedtime_photos'] = s['bedtime_photos']
        row['skin_wake_photos'] = s['wake_photos']
        change = s.get('change', {})
        for ck, cv in change.items():
            if isinstance(cv, (int, float)):
                row[f'skin_{ck}'] = cv
    else:
        row['skin_bedtime_photos'] = 0
        row['skin_wake_photos'] = 0

    rows.append(row)

df_aligned = pd.DataFrame(rows)
df_aligned = df_aligned.sort_values('date').reset_index(drop=True)
df_aligned.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')

n_face = int(df_aligned['n_faces'].sum())
n_face_days = int((df_aligned['n_faces'] > 0).sum())
n_audio_days = int((df_aligned['audio_n_recordings'] > 0).sum())
n_band_days = int((~df_aligned['band_real_score'].isna() & (df_aligned['band_real_score'] > 0)).sum())
n_triple = int(((df_aligned['n_faces'] > 0) & (df_aligned['audio_n_recordings'] > 0) & (df_aligned['band_real_score'] > 0)).sum())

meta = {
    'version': 'v1',
    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'n_days': int(len(df_aligned)),
    'n_columns': int(len(df_aligned.columns)),
    'date_range': f"{df_aligned['date'].min()}~{df_aligned['date'].max()}",
    'n_face_photos': n_face,
    'n_face_days': n_face_days,
    'n_audio_days': n_audio_days,
    'n_band_days': n_band_days,
    'n_triple_aligned': n_triple,
    'feature_columns': [c for c in df_aligned.columns if c not in ['date', 'data_sources', 'n_sources']],
}

with open(OUTPUT_META, 'w', encoding='utf-8') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print(f"\n  CSV: {OUTPUT_CSV}")
print(f"  Meta: {OUTPUT_META}")
print(f"\n{sep}")
print("数据科学专家报告：处理完成")
print(sep)
print(f"  总天数: {len(df_aligned)}天")
print(f"    面部: {n_face_days}天 ({n_face}张照片)")
print(f"    录音: {n_audio_days}天")
print(f"    手环: {n_band_days}天")
print(f"    三源对齐: {n_triple}天")
print(f"  特征维度: {len(meta['feature_columns'])}列")
print(f"  日期范围: {meta['date_range']}")
print(sep)
