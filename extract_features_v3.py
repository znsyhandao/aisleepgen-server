#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_features_v3.py - 基于 AISkinHealth 算法的面部特征提取器
===========================================================
算法来源: D:\AISkinHealth1210\backend\deep_skin_analyzer.py
核心改进:
1. 人脸检测: Haar cascade + 降级皮肤分割 + 多参数尝试
2. 颜色特征: 复用 AISkinHealth (LAB 9 + HSV 7 + YCrCb 4 + Redness 10 = 30维)
3. 纹理特征: 复用 AISkinHealth (LBP 16 + Gabor 24 + GLCM 12 + LBPV 1 = 53维)
4. 区域特征: 复用 AISkinHealth (皮肤分割 4 + 区域红斑 8 + 形状 2 = 13维)
5. ROI特征: 检测到脸时额外提取 (前额/下颌梯度 3 + 脸颊对称 1 + 疲劳 3)
总计: 30 + 53 + 13 + 7 = 103 维
"""

import os, sys, json, time, warnings, gc
warnings.filterwarnings('ignore')
import numpy as np
import cv2
from skimage.feature import local_binary_pattern, graycomatrix, graycoprops
from skimage.filters import gabor
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
PHOTO_DB = os.path.join(BASE, 'sleep-skin image database')
OUT_DIR = os.path.join(BASE, 'sleep-skin features')
OUT_CSV = os.path.join(OUT_DIR, 'facial_features_v10.csv')
OUT_LOG = os.path.join(OUT_DIR, 'extract_v10_log.json')
os.makedirs(OUT_DIR, exist_ok=True)

# ==================== 模型初始化 ====================
HAAR_PATH = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
_models_loaded = False
_face_cascade = None

def _load_models():
    global _face_cascade, _models_loaded
    if _models_loaded:
        return
    _face_cascade = cv2.CascadeClassifier(HAAR_PATH)
    _models_loaded = True
    print('[init] Haar cascade loaded')

# ==================== 人脸检测 ====================
def detect_face(img):
    """Haar cascade + 多参数降级"""
    _load_models()
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 多参数尝试
    params = [
        (1.1, 3, (50, 50)),   # 标准
        (1.05, 2, (30, 30)),  # 宽松
        (1.15, 4, (40, 40)),  # 严格
        (1.03, 1, (20, 20)),  # 极宽松
    ]
    
    for scale, min_nei, min_sz in params:
        faces = _face_cascade.detectMultiScale(gray, scale, min_nei, minSize=min_sz)
        if len(faces) > 0:
            best = max(faces, key=lambda r: r[2] * r[3])
            x, y, fw, fh = best
            return (max(0, x), max(0, y), min(w, x+fw), min(h, y+fh))
    
    return None

# ==================== 光照预处理 (复用 AISkinHealth) ====================
LIGHT_PARAMS = {'brightness_threshold': 100, 'contrast_threshold': 50}

def _adaptive_light_correction(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    brightness = np.mean(gray)
    if brightness < LIGHT_PARAMS['brightness_threshold']:
        gamma = 1.5
        img_corrected = np.power(img / 255.0, gamma) * 255
        img_corrected = np.uint8(img_corrected)
    else:
        img_corrected = img
    return img_corrected

def _normalize_illumination(gray):
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)

# ==================== 颜色特征 (30维, 复用 AISkinHealth) ====================
def extract_color_features(img):
    img_lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    img_ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    features = []
    
    # 1. LAB (9维)
    features.extend([
        np.mean(img_lab[:,:,0]), np.std(img_lab[:,:,0]),
        np.mean(img_lab[:,:,1]), np.std(img_lab[:,:,1]),
        np.mean(img_lab[:,:,2]), np.std(img_lab[:,:,2]),
        np.percentile(img_lab[:,:,1], 75),
        np.percentile(img_lab[:,:,1], 90),
        np.median(img_lab[:,:,1]),
    ])
    
    # 2. HSV (7维)
    features.extend([
        np.mean(img_hsv[:,:,0]), np.std(img_hsv[:,:,0]),
        np.mean(img_hsv[:,:,1]), np.std(img_hsv[:,:,1]),
        np.mean(img_hsv[:,:,2]), np.std(img_hsv[:,:,2]),
        np.percentile(img_hsv[:,:,1], 75),
    ])
    
    # 3. YCrCb (4维)
    features.extend([
        np.mean(img_ycrcb[:,:,1]), np.std(img_ycrcb[:,:,1]),
        np.mean(img_ycrcb[:,:,2]), np.std(img_ycrcb[:,:,2]),
    ])
    
    # 4. Redness (10维, 复用AISkinHealth)
    a_channel = img_lab[:,:,1]
    saturation_mean = np.mean(img_hsv[:,:,1])
    base_threshold = 135 if saturation_mean > 80 else 125
    
    for t in range(5):
        th = base_threshold + t * 10
        mask = a_channel > th
        features.append(float(np.sum(mask)) / mask.size)
    
    redness_pix = a_channel[a_channel > base_threshold]
    if len(redness_pix) > 0:
        features.extend([
            float(np.mean(redness_pix)), float(np.std(redness_pix)),
            float(len(redness_pix)) / a_channel.size,
            float(np.percentile(redness_pix, 75)),
            float(np.percentile(redness_pix, 90)),
        ])
    else:
        features.extend([0.0] * 5)
    
    # 裁剪到30维
    if len(features) < 30:
        features.extend([0.0] * (30 - len(features)))
    return features[:30]

# ==================== 纹理特征 (53维, 复用 AISkinHealth) ====================
def extract_texture_features(gray_normalized):
    features = []
    
    # 1. LBP (16维)
    try:
        radius, n_points = 3, 24
        lbp = local_binary_pattern(gray_normalized, n_points, radius, method='uniform')
        hist, _ = np.histogram(lbp.ravel(), bins=int(lbp.max() + 1), range=(0, n_points + 2))
        hist = hist.astype(float) / max(hist.sum(), 1e-7)
        lbp_feats = hist.tolist() if len(hist) <= 16 else hist[:16].tolist()
        if len(lbp_feats) < 16:
            lbp_feats.extend([0.0] * (16 - len(lbp_feats)))
        features.extend(lbp_feats[:16])
    except Exception:
        features.extend([0.0] * 16)
    
    # 2. Gabor (24维, 3频率x4方向x2sigma, 用256x256加速)
    try:
        gabor_small = cv2.resize(gray_normalized, (256, 256))
        gabor_feats = []
        for freq in [0.1]:
            for theta in [0, np.pi/4, np.pi/2, 3*np.pi/4]:
                for sigma in [3, 5]:
                    real, imag = gabor(gabor_small, freq, theta=theta,
                                       sigma_x=sigma, sigma_y=sigma)
                    real, imag = gabor(gabor_small, freq, theta=theta,
                                       sigma_x=sigma, sigma_y=sigma)
                    gabor_feats.extend([
                        float(np.mean(real)), float(np.std(real)),
                        float(np.mean(imag)), float(np.std(imag)),
                    ])
        if len(gabor_feats) < 24:
            gabor_feats.extend([0.0] * (24 - len(gabor_feats)))
        features.extend(gabor_feats[:24])
    except Exception:
        features.extend([0.0] * 24)
    
    # 3. GLCM (12维, 512px以下)
    try:
        gs_glcm = cv2.resize(gray_normalized, (256, 256))
        gray_q = np.clip(gs_glcm, 0, 255).astype(np.uint8) // 16
        glcm = graycomatrix(gray_q, [1, 3], [0, np.pi/4, np.pi/2, 3*np.pi/4],
                            levels=16, symmetric=True, normed=True)
        glcm_feats = []
        for prop in ['contrast', 'dissimilarity', 'homogeneity', 'energy', 'correlation', 'ASM']:
            vals = graycoprops(glcm, prop)
            glcm_feats.extend([float(np.mean(vals)), float(np.std(vals))])
        if len(glcm_feats) < 12:
            glcm_feats.extend([0.0] * (12 - len(glcm_feats)))
        features.extend(glcm_feats[:12])
    except Exception:
        features.extend([0.0] * 12)
    
    # 4. LBPV (1维)
    try:
        lbpv = local_binary_pattern(gray_normalized, 8, 1, method='uniform')
        features.append(float(np.var(gray_normalized)))
    except Exception:
        features.append(0.0)
    
    if len(features) < 53:
        features.extend([0.0] * (53 - len(features)))
    return features[:53]

# ==================== 区域特征 (13维, 复用 AISkinHealth) ====================
def _skin_segmentation(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    
    mask_hsv = cv2.inRange(hsv, np.array([0, 20, 70], dtype=np.uint8),
                           np.array([20, 255, 255], dtype=np.uint8))
    mask_ycrcb = cv2.inRange(ycrcb, np.array([0, 133, 77], dtype=np.uint8),
                             np.array([255, 173, 127], dtype=np.uint8))
    skin_mask = cv2.bitwise_and(mask_hsv, mask_ycrcb)
    
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_CLOSE, k)
    skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, k)
    
    quality = []
    if np.sum(skin_mask) > 0:
        num_l, stats = cv2.connectedComponentsWithStats(skin_mask, 8)[:2]
        if num_l > 1:
            largest = np.max(stats[1:, cv2.CC_STAT_AREA])
            quality.append(float(largest) / max(np.sum(skin_mask), 1))
        else:
            quality.append(0.0)
        skin_r = cv2.bitwise_and(img, img, mask=skin_mask)
        gray_s = cv2.cvtColor(skin_r, cv2.COLOR_BGR2GRAY)
        skin_pix = gray_s[gray_s > 0]
        quality.append(float(np.std(skin_pix)) if len(skin_pix) > 0 else 0.0)
    else:
        quality = [0.0, 0.0]
    
    return skin_mask, quality

def _region_redness(img, skin_mask):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    a_ch = lab[:,:,1]
    pix = a_ch[skin_mask > 0]
    
    if len(pix) == 0:
        return [0.0] * 8
    
    a_mean = np.mean(pix)
    a_std = np.std(pix)
    ths = [a_mean + a_std, a_mean + 2*a_std, a_mean + 3*a_std]
    red = [float(np.sum(pix > t)) / len(pix) for t in ths]
    
    intense = pix[pix > ths[0]]
    if len(intense) > 0:
        red.extend([float(np.mean(intense)), float(np.std(intense)),
                    float(len(intense)) / len(pix)])
    else:
        red.extend([0.0, 0.0, 0.0])
    
    if len(red) < 8:
        red.extend([0.0] * (8 - len(red)))
    return red[:8]

def extract_region_features(img):
    features = []
    skin_mask, quality = _skin_segmentation(img)
    
    # 1. 皮肤比例+质量 (4维)
    skin_ratio = float(np.sum(skin_mask)) / skin_mask.size
    features.append(skin_ratio)
    q = quality + [0.0] * max(0, 3 - len(quality))
    features.extend(q[:3])
    
    # 2. 区域红斑 (8维)
    features.extend(_region_redness(img, skin_mask))
    
    # 3. 形状特征 (2维)
    try:
        contours, _ = cv2.findContours(skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            max_cont = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(max_cont)
            perimeter = cv2.arcLength(max_cont, True)
            features.append(float(area) / max(skin_mask.size, 1))
            features.append(float(perimeter * perimeter) / max(area * 4 * np.pi, 1e-6))
        else:
            features.extend([0.0, 0.0])
    except Exception:
        features.extend([0.0, 0.0])
    
    if len(features) < 13:
        features.extend([0.0] * (13 - len(features)))
    return features[:13]

# ==================== ROI特征 (7维, 检测到人脸时额外提取) ====================
def extract_roi_features(img, bbox):
    x1, y1, x2, y2 = bbox
    h, w = img.shape[:2]
    face_w = min(x2 - x1, w - x1)
    face_h = min(y2 - y1, h - y1)
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray_float = gray.astype(float)
    
    # 前额 ROI
    fx1 = max(0, x1 + face_w // 6)
    fx2 = min(w, x1 + 5 * face_w // 6)
    fy1 = max(0, y1)
    fy2 = min(h, y1 + face_h // 3)
    forehead = gray_float[fy1:fy2, fx1:fx2]
    
    # 下颌 ROI
    jy1 = max(0, y1 + 2 * face_h // 3)
    jy2 = min(h, y2)
    jaw = gray_float[jy1:jy2, fx1:fx2]
    
    fl = float(np.mean(forehead)) if forehead.size > 0 else 0.0
    jl = float(np.mean(jaw)) if jaw.size > 0 else 0.0
    
    feats = {
        'roi_forehead_L': fl,
        'roi_grad_forehead_jaw': fl - jl,
        'roi_forehead_jaw_ratio': fl / max(jl, 1e-6),
    }
    
    # 脸颊对称性
    cx = x1 + face_w // 2
    l_cheek = gray_float[max(0, y1 + face_h//3):min(h, y1 + 2*face_h//3),
                          max(0, x1):max(0, cx - face_w//6)]
    r_cheek = gray_float[max(0, y1 + face_h//3):min(h, y1 + 2*face_h//3),
                          cx + face_w//6:min(w, x2)]
    if l_cheek.size > 0 and r_cheek.size > 0:
        feats['cheek_symmetry'] = abs(float(np.mean(l_cheek)) - float(np.mean(r_cheek)))
    else:
        feats['cheek_symmetry'] = 0.0
    
    # 疲劳指标
    face_region = gray_float[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    try:
        feats['fatigue_full_sharpness'] = float(cv2.Laplacian(face_region.astype(np.uint8), cv2.CV_64F).var())
    except Exception:
        feats['fatigue_full_sharpness'] = 0.0
    
    fh2, fw2 = face_region.shape
    eye_r = face_region[max(0, fh2//6):min(fh2, fh2//2), max(0, fw2//6):min(fw2, 5*fw2//6)]
    brow_r = face_region[:min(fh2, fh2//4), max(0, fw2//6):min(fw2, 5*fw2//6)]
    feats['fatigue_eye_texture'] = float(np.std(eye_r)) if eye_r.size > 0 else 0.0
    feats['fatigue_brow_texture'] = float(np.std(brow_r)) if brow_r.size > 0 else 0.0
    
    return feats

# ==================== 白平衡 ====================
def auto_white_balance(img):
    f = img.astype(np.float32)
    h, w = f.shape[:2]
    center = f[h//4:3*h//4, w//4:3*w//4]
    avg_r = np.mean(center[:,:,2])
    avg_g = np.mean(center[:,:,1])
    avg_b = np.mean(center[:,:,0])
    gray = (avg_r + avg_g + avg_b) / 3.0
    if avg_g > 1:
        f[:,:,2] = np.clip(f[:,:,2] * (gray / max(avg_r, 1)), 0, 255)
        f[:,:,0] = np.clip(f[:,:,0] * (gray / max(avg_b, 1)), 0, 255)
    return f.astype(np.uint8)

# ==================== 主处理循环 ====================
def _extract_single(fn, fp, date_str):
    """单张图片特征提取（内存隔离）"""
    buf = np.fromfile(fp, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        return None, None
    
    # 白平衡
    img = auto_white_balance(img)
    
    # 降采样
    h, w = img.shape[:2]
    if max(h, w) > 640:
        scale = 640.0 / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale)
    
    # 人脸检测
    bbox = detect_face(img)
    
    row = {
        'date': date_str, 'file': fn,
        'img_size': os.path.getsize(fp) if os.path.exists(fp) else 0,
        'face_detected': bbox is not None,
    }
    
    # 光照校正
    img_corrected = _adaptive_light_correction(img)
    gray = cv2.cvtColor(img_corrected, cv2.COLOR_BGR2GRAY)
    gray_norm = _normalize_illumination(gray)
    
    # 特征提取
    color_f = extract_color_features(img_corrected)
    texture_f = extract_texture_features(gray_norm)
    region_f = extract_region_features(img_corrected)
    
    for i in range(30):
        row[f'color_{i:02d}'] = color_f[i]
    for i in range(53):
        row[f'tex_{i:02d}'] = texture_f[i]
    for i in range(13):
        row[f'region_{i:02d}'] = region_f[i]
    
    if bbox:
        row['face_area'] = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        roi = extract_roi_features(img, bbox)
        row.update(roi)
    else:
        row['face_area'] = 0
        row.update({
            'roi_forehead_L': 0.0, 'roi_grad_forehead_jaw': 0.0,
            'roi_forehead_jaw_ratio': 0.0, 'cheek_symmetry': 0.0,
            'fatigue_full_sharpness': 0.0, 'fatigue_eye_texture': 0.0,
            'fatigue_brow_texture': 0.0,
        })
    
    return row, bbox


_COLUMN_ORDER = ['date', 'file', 'img_size', 'face_detected', 'face_area',
                 'roi_forehead_L', 'roi_grad_forehead_jaw', 'roi_forehead_jaw_ratio',
                 'cheek_symmetry', 'fatigue_full_sharpness', 'fatigue_eye_texture',
                 'fatigue_brow_texture']
_EXTRA_COLS = sorted(
    [f'color_{i:02d}' for i in range(30)] +
    [f'tex_{i:02d}' for i in range(53)] +
    [f'region_{i:02d}' for i in range(13)]
)
_COLUMN_ORDER = _COLUMN_ORDER[:5] + _EXTRA_COLS + _COLUMN_ORDER[5:]


def process_all_images():
    print('=' * 70, flush=True)
    print('  extract_features_v3.py (基于 AISkinHealth 算法)', flush=True)
    print(f'  Input : {PHOTO_DB}', flush=True)
    print(f'  Output: {OUT_CSV}', flush=True)
    print('=' * 70, flush=True)
    
    all_dirs = sorted([
        d for d in os.listdir(PHOTO_DB)
        if os.path.isdir(os.path.join(PHOTO_DB, d)) and len(d) == 8 and d.isdigit()
    ])
    print(f'Found {len(all_dirs)} date directories', flush=True)
    
    total_imgs = 0
    face_detected = 0
    start_time = time.time()
    
    # 初始化CSV（写表头）
    all_cols = _COLUMN_ORDER
    pd.DataFrame(columns=all_cols).to_csv(OUT_CSV, index=False, encoding='utf-8')
    
    for date_str in all_dirs:
        folder = os.path.join(PHOTO_DB, date_str)
        photos = sorted([
            f for f in os.listdir(folder)
            if f.lower().endswith(('.jpg', '.jpeg', '.png'))
            and 'whitebalance' not in f.lower()
        ])
        if not photos:
            continue
        
        print(f'\n[{date_str}] {len(photos)} images...', flush=True)
        date_rows = []
        
        for fn in photos:
            fp = os.path.join(folder, fn)
            total_imgs += 1
            
            try:
                row, bbox = _extract_single(fn, fp, date_str)
                if row is None:
                    continue
                if bbox:
                    face_detected += 1
                date_rows.append(row)
                
                if total_imgs % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = total_imgs / max(elapsed, 1)
                    print(f'  ...{total_imgs} processed, {face_detected}/{total_imgs} face, {rate:.1f} img/s', flush=True)
            
            except Exception as e:
                print(f'  [ERR] {fn}: {e}', flush=True)
                date_rows.append({
                    'date': date_str, 'file': fn,
                    'img_size': os.path.getsize(fp) if os.path.exists(fp) else 0,
                    'face_detected': False,
                })
        
        # 每日期写入CSV
        if date_rows:
            df_date = pd.DataFrame(date_rows)
            df_date.to_csv(OUT_CSV, mode='a', header=False, index=False, encoding='utf-8')
        
        # 强制GC
        del date_rows
        gc.collect()
    
    # 输出汇总
    elapsed = time.time() - start_time
    print(f'\n{"=" * 70}', flush=True)
    print(f'Done: {total_imgs} images, {face_detected} face ({face_detected/max(total_imgs,1)*100:.1f}%)', flush=True)
    print(f'Time: {elapsed:.1f}s', flush=True)
    
    df = pd.read_csv(OUT_CSV)
    print(f'Saved: {OUT_CSV} ({len(df)} rows x {len(df.columns)} cols)', flush=True)
    
    log = {
        'version': 'v10', 'algorithm': 'AISkinHealth',
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_images': total_imgs, 'face_detected': face_detected,
        'detection_rate': round(face_detected / max(total_imgs, 1) * 100, 1),
        'duration_sec': round(elapsed, 1),
        'feature_dims': 103,
        'color_dims': 30, 'texture_dims': 53, 'region_dims': 13, 'roi_dims': 7,
    }
    with open(OUT_LOG, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    
    return df


if __name__ == '__main__':
    df = process_all_images()
    detected = df[df['face_detected'] == True]
    print(f'\n=== Summary ===', flush=True)
    print(f'Detection rate: {len(detected)}/{len(df)} = {len(detected)/len(df)*100:.1f}%', flush=True)
    print(f'Dates with detection: {len(detected.groupby("date"))}', flush=True)
    
    print(f'\n=== Degradation check ===', flush=True)
    late = df[df['date'].astype(int) >= 20260522]
    early = df[df['date'].astype(int) < 20260522]
    for c in ['color_00', 'color_01', 'color_02', 'tex_00', 'tex_01', 'region_00']:
        if c in df.columns:
            em = early[c].mean()
            lm = late[c].mean()
            print(f'  {c}: early={em:.4f} late={lm:.4f}', flush=True)
    # 检查所有特征不能全零
    all_zero_cols = [c for c in df.columns if c not in ['date','file','file','img_size'] and df[c].sum() == 0]
    if all_zero_cols:
        print(f'\n  ❌ ZERO columns: {all_zero_cols}', flush=True)
    else:
        print(f'\n  ✅ No zero columns detected', flush=True)
