# -*- coding: utf-8 -*-
"""
v9 数据增强 v2 — 光照/对比度变体生成
每张检测到人脸的原始照片生成 4 种光照变体 → 扩充训练集
优化：只 import 提取模块一次，大幅加速
"""
import os, sys, cv2, numpy as np, pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

BASE = r'D:\AISleepGen_Optimized\sleep-skin image database'
CSV = r'D:\AISleepGen_Optimized\sleep-skin features\facial_features_v9.csv'
OUT_CSV = r'D:\AISleepGen_Optimized\sleep-skin features\facial_features_v9_augmented.csv'

# 只提取 Ensemble 使用的 8 个核心特征
CORE_FEATS = ['roi_grad_forehead_jaw','roi_forehead_jaw_ratio','hsv_H_std',
              'freq_high_low_ratio','hsv_S_mean','roi_forehead_L',
              'gabor_mean_00','gabor_std_00']

# 提前导入提取模块（只一次）
sys.path.insert(0, r'D:\AISleepGen_Optimized')
import importlib.util
spec = importlib.util.spec_from_file_location('v9', 
    r'D:\AISleepGen_Optimized\scripts\extract_skin_features_v9.py')
v9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v9)
# 抑制后续 banner 输出
v9.QUIET = True

# 光照变体参数
VARIANTS = [
    ('dark', 0.7, 1.0),
    ('bright', 1.3, 1.0),
    ('low_contrast', 1.0, 0.8),
    ('high_contrast', 1.0, 1.2),
]

def main():
    df = pd.read_csv(CSV, encoding='utf-8')
    detected = df[df['face_detected'].astype(str).str.lower().str.strip() == 'true'].copy()
    print(f'基础: {len(detected)} 张可增强')

    rows = []
    total = len(detected)
    for idx, (_, row) in enumerate(detected.iterrows()):
        date = str(row['date']).strip()
        fname = row['file']
        img_path = os.path.join(BASE, date, fname)
        if not os.path.exists(img_path):
            continue
        
        try:
            from PIL import Image
            pil = Image.open(img_path)
            img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        except:
            continue

        for var_name, brightness, contrast in VARIANTS:
            try:
                # 亮度/对比度变换
                alpha = contrast
                beta = 128 * (1 - alpha) + alpha * (brightness - 1.0) * 128
                aug = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)
                
                # 临时保存（cv2.imread 不支持中文路径，PIL 写回）
                temp_path = os.path.join(BASE, f'_aug_temp_{np.random.randint(10000)}.jpg')
                cv2.imwrite(temp_path, aug)
                
                result = v9.extract_features(temp_path)
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
                if result.get('face_detected') == True:
                    # 只取核心 8 个特征
                    feat_row = {'date': date, 'file': f'{var_name}_{fname}',
                                'gender': 'M' if '_man' in fname.lower() else 'F'}
                    for k in CORE_FEATS:
                        feat_row[k] = result.get(k, '')
                    rows.append(feat_row)
                    non_empty = sum(1 for k in CORE_FEATS if feat_row.get(k) not in (None, '', 'nan'))
                    if non_empty < 8:
                        print(f'  ! {var_name} {fname} 特征缺失: {non_empty}/8')
                else:
                    print(f'  x {var_name} {fname} 检测不到')
            except Exception as e:
                print(f'  ! {var_name} {fname} 失败: {e}')
        
        if (idx + 1) % 20 == 0:
            print(f'  [进度] {idx+1}/{total}', flush=True)

    print(f'\n增强完成: {len(rows)} 个变体')

    # 合并到原始 CSV（仅核心特征）
    df_aug = pd.DataFrame(rows)
    common_cols = ['date', 'file', 'gender'] + CORE_FEATS
    # 原始数据也取相同的列
    df_base = detected[common_cols].copy()
    df_combined = pd.concat([df_base, df_aug[common_cols]], ignore_index=True)
    df_combined.to_csv(OUT_CSV, index=False, encoding='utf-8')
    
    female_base = len(detected[detected['gender'] == 'F'])
    female_aug = len(df_aug[df_aug['gender'] == 'F'])
    print(f'女性: {female_base} → {female_base + female_aug}')
    male_base = len(detected[detected['gender'] == 'M'])
    male_aug = len(df_aug[df_aug['gender'] == 'M'])
    print(f'男性: {male_base} → {male_base + male_aug}')
    print(f'输出: {OUT_CSV}')

if __name__ == '__main__':
    main()
