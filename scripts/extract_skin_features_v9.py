# -*- coding: utf-8 -*-
"""
v9 皮肤特征提取 — v6 + AISkinHealth纹理增强 + 亮度归一化
"""
import os, sys, warnings, cv2, numpy as np
warnings.filterwarnings('ignore')

print('='*60)
print('  v9 皮肤特征提取 — v6 + AISkinHealth纹理增强')
print('='*60)

BASE = r'D:\AISleepGen_Optimized\sleep-skin image database'
OUT = r'D:\AISleepGen_Optimized\sleep-skin features'
WB_DIR = os.path.join(BASE, 'whitebalance_0425')

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# ========== 白平衡 ==========
def compute_white_balance_params(wb_dir):
    """从白纸照片计算白平衡校正参数"""
    if not os.path.isdir(wb_dir):
        print(f'  ⚠️ 白平衡目录不存在: {wb_dir}，跳过')
        return None
    files = [f for f in os.listdir(wb_dir) if f.lower().endswith(('.jpg','.png','.jpeg'))]
    if not files:
        print('  ⚠️ 白平衡目录无照片')
        return None
    r_avg, g_avg, b_avg = 0, 0, 0
    count = 0
    for f in files:
        img = cv2.imread(os.path.join(wb_dir, f))
        if img is None: continue
        b, g, r = cv2.split(img)
        r_avg += r.mean(); g_avg += g.mean(); b_avg += b.mean()
        count += 1
    if count == 0: return None
    r_avg /= count; g_avg /= count; b_avg /= count
    params = {'r_gain': g_avg/r_avg, 'b_gain': g_avg/b_avg}
    print(f'  📷 白平衡校正参数 (基于{count}张白纸):')
    print(f'     R/G = {r_avg/g_avg:.3f}, B/G = {b_avg/g_avg:.3f}')
    print(f'     校正系数: R×{params["r_gain"]:.3f}, B×{params["b_gain"]:.3f}')
    return params

def apply_white_balance(img, wb_params):
    if wb_params is None: return img
    result = img.copy().astype(np.float32)
    result[:,:,2] *= wb_params['r_gain']  # R
    result[:,:,0] *= wb_params['b_gain']  # B
    return np.clip(result, 0, 255).astype(np.uint8)

def apply_grayworld_balance(img):
    """Gray-World 白平衡：假设场景平均颜色是灰色的"""
    result = img.copy().astype(np.float32)
    b, g, r = cv2.split(result)
    avg_g = g.mean()
    r_gain = avg_g / (r.mean() + 1e-6)
    b_gain = avg_g / (b.mean() + 1e-6)
    # 融合纸白平衡和灰世界（50/50），仅在纸参数可用时
    return r_gain, b_gain

def compute_combined_wb(img, wb_paper_params):
    """融合纸白平衡 + GrayWorld，得到更鲁棒的白平衡系数"""
    gw_r_gain, gw_b_gain = apply_grayworld_balance(img)
    if wb_paper_params is None:
        return {'r_gain': gw_r_gain, 'b_gain': gw_b_gain}
    # 加权融合：纸参数 0.6 + GrayWorld 0.4（纸更可靠因为知道白纸是白的）
    r_gain = 0.6 * wb_paper_params['r_gain'] + 0.4 * gw_r_gain
    b_gain = 0.6 * wb_paper_params['b_gain'] + 0.4 * gw_b_gain
    return {'r_gain': r_gain, 'b_gain': b_gain}

def retinex_ssr(img, sigma=30):
    """单尺度 Retinex (SSR): S = R * I → 返回反射率 R
    反射率是光照不变表示，光照变了但皮肤本身的反射率不变。
    """
    img_float = img.astype(np.float32)
    # 对每个通道做 log-domain Retinex
    log_img = np.log1p(img_float)
    blur = cv2.GaussianBlur(log_img, (0, 0), sigma)
    log_reflectance = log_img - blur  # log(R) = log(S) - log(I)
    reflectance = np.expm1(log_reflectance)
    # 归一化到 0~255
    r_min, r_max = reflectance.min(), reflectance.max()
    if r_max > r_min:
        reflectance = (reflectance - r_min) / (r_max - r_min) * 255
    return np.clip(reflectance, 0, 255).astype(np.uint8)

def retinex_msr(img, sigmas=[15, 80, 250]):
    """多尺度 Retinex (MSR)：融合多个尺度的反射率"""
    acc = np.zeros_like(img, dtype=np.float32)
    for s in sigmas:
        acc += retinex_ssr(img, sigma=s).astype(np.float32)
    acc /= len(sigmas)
    return np.clip(acc, 0, 255).astype(np.uint8)

def homomorphic_filter(gray, cutoff_radius=40):
    """同态滤波：频域高通去掉低频光照分量"""
    h, w = gray.shape
    gray_float = gray.astype(np.float64) + 1e-6
    # log 变换
    log_img = np.log(gray_float)
    # FFT
    f = np.fft.fft2(log_img)
    fshift = np.fft.fftshift(f)
    # 高通滤波器 (高斯高通)
    crow, ccol = h // 2, w // 2
    y, x = np.ogrid[:h, :w]
    dist = np.sqrt((x - ccol)**2 + (y - crow)**2)
    # 高斯高通：保留高频（纹理），抑制低频（光照）
    hpf = 1 - np.exp(-dist**2 / (2 * cutoff_radius**2))
    # 加一个偏移量保留部分低频，避免过度
    hpf = 0.8 * hpf + 0.2
    f_filtered = fshift * hpf
    # IFFT
    f_ishift = np.fft.ifftshift(f_filtered)
    img_back = np.fft.ifft2(f_ishift)
    img_back = np.exp(img_back.real) - 1e-6
    # 归一化到 0~255
    img_back = np.clip(img_back, 0, 255).astype(np.uint8)
    return img_back

wb_params = compute_white_balance_params(WB_DIR)

# ========== Retinex / 光照归一化参数 ==========
# MSR 三个尺度：精细纹理(15)、中等(sigma=80)、整体(250)
RETINEX_SIGMAS = [15, 80, 250]

# ========== 人脸检测 ==========
def detect_face_by_skin(img):
    """基于肤色 + Haar cascade 的人脸检测"""
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # 先缩小到 1000px max 再检测（提高检测率）
    h, w = gray.shape
    max_dim = max(h, w)
    if max_dim > 1000:
        scale = 1000.0 / max_dim
        gray_small = cv2.resize(gray, (int(w * scale), int(h * scale)))
        min_size = (30, 30)
    else:
        gray_small = gray
        min_size = (50, 50)
    faces = face_cascade.detectMultiScale(gray_small, 1.1, 3, minSize=min_size)
    if len(faces) == 0:
        return None, None, None
    (x_small, y_small, fw_small, fh_small) = max(faces, key=lambda r: r[2]*r[3])
    
    # 映射回原图坐标
    if max_dim > 1000:
        sf = max_dim / 1000.0  # 缩放因子
        x = int(x_small * sf)
        y = int(y_small * sf)
        fw = int(fw_small * sf)
        fh = int(fh_small * sf)
    else:
        x, y, fw, fh = x_small, y_small, fw_small, fh_small
    
    margin_x = int(fw * 0.15)
    margin_top = int(fh * 0.05)
    margin_bottom = int(fh * 0.25)
    x1 = max(0, x - margin_x)
    y1 = max(0, y - margin_top)
    x2 = min(w, x + fw + margin_x)
    y2 = min(h, y + fh + margin_bottom)
    face_roi = img[y1:y2, x1:x2]
    # 面部+额头 ROI
    fy1 = max(0, y - int(fh * 0.5))
    fy2 = min(h, y + int(fh * 0.8))
    fx1 = max(0, x - margin_x)
    fx2 = min(w, x + fw + margin_x)
    face_full_roi = img[fy1:fy2, fx1:fx2]
    return face_roi, face_full_roi, (x, y, fw, fh)

# ========== Lab 分析 ==========
def analyze_skin_lab(roi):
    h, w = roi.shape[:2]
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)
    # ROI 中心 50% 区域
    cy, cx = h//2, w//2
    rh, rw = h//4, w//4
    center_L = L[cy-rh:cy+rh, cx-rw:cx+rw]
    center_A = A[cy-rh:cy+rh, cx-rw:cx+rw]
    center_B = B[cy-rh:cy+rh, cx-rw:cx+rw]
    return {
        'lab_L_mean': float(L.mean()), 'lab_L_std': float(L.std()),
        'lab_A_mean': float(A.mean()), 'lab_A_std': float(A.std()),
        'lab_B_mean': float(B.mean()), 'lab_B_std': float(B.std()),
        'lab_L_center_mean': float(center_L.mean()),
        'lab_A_center_mean': float(center_A.mean()),
        'lab_B_center_mean': float(center_B.mean()),
    }

LAB_KEYS = ['lab_L_mean','lab_L_std','lab_A_mean','lab_A_std','lab_B_mean','lab_B_std',
            'lab_L_center_mean','lab_A_center_mean','lab_B_center_mean']

# ========== HSV 分析 ==========
def analyze_hsv(roi):
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    H, S, V = cv2.split(hsv)
    return {
        'hsv_H_mean': float(H.mean()), 'hsv_H_std': float(H.std()),
        'hsv_S_mean': float(S.mean()), 'hsv_S_std': float(S.std()),
        'hsv_V_mean': float(V.mean()), 'hsv_V_std': float(V.std()),
        'hsv_H_75': float(np.percentile(H, 75)),
        'hsv_S_25': float(np.percentile(S, 25)),
    }

HSV_KEYS = ['hsv_H_mean','hsv_H_std','hsv_S_mean','hsv_S_std','hsv_V_mean','hsv_V_std',
            'hsv_H_75','hsv_S_25']

# ========== 疲劳分析 ==========
def analyze_fatigue_signs(roi):
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    # 眉毛区域（上 30%）
    brow = gray[:int(h*0.35), :]
    # 眼周区域（中间 40%，从上 25% 开始）
    eye = gray[int(h*0.25):int(h*0.65), int(w*0.1):int(w*0.9)]
    # 眉毛纹理：Laplacian 方差
    brow_lap = cv2.Laplacian(brow, cv2.CV_64F).var()
    # 眼周纹理
    eye_lap = cv2.Laplacian(eye, cv2.CV_64F).var()
    # 整体锐度
    full_lap = cv2.Laplacian(gray, cv2.CV_64F).var()
    return {
        'fatigue_brow_texture': float(brow_lap),
        'fatigue_eye_texture': float(eye_lap),
        'fatigue_full_sharpness': float(full_lap),
    }

FATIGUE_KEYS = ['fatigue_brow_texture','fatigue_eye_texture','fatigue_full_sharpness']

# ========== ROI 特征 ==========
def analyze_roi_features(face_roi, face_full_roi):
    h, w = face_roi.shape[:2]
    gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
    # 额头 ROI（上 20%）
    forehead = gray[:int(h*0.2), :]
    # 下颌 ROI（下 25%）
    jaw = gray[int(h*0.75):, int(w*0.2):int(w*0.8)]
    # 梯度
    grad_forehead = cv2.Laplacian(forehead, cv2.CV_64F).var()
    grad_jaw = cv2.Laplacian(jaw, cv2.CV_64F).var()
    grad_ratio = grad_forehead / (grad_jaw + 1e-6)
    # 额头亮度
    fh, fw = face_full_roi.shape[:2]
    f_gray = cv2.cvtColor(face_full_roi, cv2.COLOR_BGR2GRAY)
    f_forehead = f_gray[:int(fh*0.3), :]
    forehead_L = float(f_forehead.mean())
    return {
        'roi_grad_forehead_jaw': float(grad_ratio),
        'roi_forehead_jaw_ratio': float(grad_ratio),
        'roi_forehead_L': float(forehead_L),
    }

ROI_KEYS = ['roi_grad_forehead_jaw','roi_forehead_jaw_ratio','roi_forehead_L']

# ========== LBP 纹理 ==========
from skimage.feature import local_binary_pattern

def extract_lbp_features(gray, P=8, R=1):
    lbp = local_binary_pattern(gray, P, R, method='uniform')
    n_bins = P + 2
    hist, _ = np.histogram(lbp.ravel(), bins=n_bins, range=(0, n_bins), density=True)
    features = {}
    for i in range(16):
        features[f'lbp_bin_{i:02d}'] = float(hist[i]) if i < len(hist) else 0.0
    return features

LBP_KEYS = [f'lbp_bin_{i:02d}' for i in range(16)]

# ========== Gabor 滤波 ==========
def gabor(kernel_size=31, sigma=4.0, theta=0, lambd=10.0, gamma=0.5, psi=0):
    return cv2.getGaborKernel((kernel_size, kernel_size), sigma, theta, lambd, gamma, psi, ktype=cv2.CV_32F)

def extract_gabor_features(gray):
    thetas = [0, np.pi/4, np.pi/2, 3*np.pi/4]
    features = {}
    for i, theta in enumerate(thetas):
        kernel = gabor(theta=theta)
        filtered = cv2.filter2D(gray, cv2.CV_32F, kernel)
        features[f'gabor_mean_{i:02d}'] = float(np.mean(filtered))
        features[f'gabor_std_{i:02d}'] = float(np.std(filtered))
    return features

GABOR_KEYS = [f'gabor_mean_{i:02d}' for i in range(4)] + [f'gabor_std_{i:02d}' for i in range(4)]

# ========== GLCM 纹理 ==========
from skimage.feature import graycomatrix, graycoprops

def extract_glcm_features(gray):
    if gray.max() <= 1:
        gray = (gray * 255).astype(np.uint8)
    g = gray.astype(np.uint8)
    glcm = graycomatrix(g, [1], [0, np.pi/4, np.pi/2, 3*np.pi/4], 256, symmetric=True, normed=True)
    gmean = glcm.mean(axis=3).squeeze()
    gstd = glcm.std(axis=3).squeeze()
    features = {}
    for prop in ['contrast', 'dissimilarity', 'homogeneity', 'energy', 'correlation', 'ASM']:
        val = graycoprops(glcm, prop)
        features[f'glcm_{prop}_mean'] = float(val.mean())
        features[f'glcm_{prop}_std'] = float(val.std())
    return features

GLCM_KEYS = [f'glcm_{p}_{s}' for p in ['contrast','dissimilarity','homogeneity','energy','correlation','ASM'] for s in ['mean','std']]

# ========== 泛红分析 ==========
def analyze_redness_advanced(roi):
    h, w = roi.shape[:2]
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    H, S, V = cv2.split(hsv)
    # A通道（红绿轴）在皮肤上的分布
    A_skin = A[L > 30]
    a_mean = float(A_skin.mean()) if len(A_skin) > 0 else 0
    a_std = float(A_skin.std()) if len(A_skin) > 0 else 0
    # 红色区域比例（V通道低+高饱和度 = 泛红）
    redness_mask = (V < 180) & (S > 40) & (A > 5)
    redness_pct = float(redness_mask.sum() / (h*w) * 100)
    # 红色区域平均强度
    redness_intensity = float(A[redness_mask].mean()) if redness_mask.sum() > 0 else 0
    return {
        'redness_A_mean': a_mean,
        'redness_A_std': a_std,
        'redness_pct': redness_pct,
        'redness_intensity': redness_intensity,
        'redness_a': a_mean,
        'redness_b': float(B[L > 30].mean()) if (L > 30).sum() > 0 else 0,
        'redness_saturation': float(S[L > 30].mean()) if (L > 30).sum() > 0 else 0,
        'redness_variation': a_std,
    }

REDNESS_KEYS = ['redness_A_mean','redness_A_std','redness_pct','redness_intensity',
                'redness_a','redness_b','redness_saturation','redness_variation']

# ========== 频率分析 ==========
def analyze_freq(gray):
    dft = np.fft.fft2(gray)
    dft_shift = np.fft.fftshift(dft)
    magnitude = np.abs(dft_shift)
    h, w = gray.shape
    cy, cx = h//2, w//2
    radius = min(cy, cx)
    low_r = radius // 3
    high_r = radius * 2 // 3
    low_mask = np.zeros((h, w), dtype=bool)
    high_mask = np.zeros((h, w), dtype=bool)
    y, x = np.ogrid[:h, :w]
    mask_center = (y - cy)**2 + (x - cx)**2
    low_mask = mask_center <= low_r**2
    high_mask = (mask_center >= high_r**2) & (mask_center <= radius**2)
    low_energy = magnitude[low_mask].sum()
    high_energy = magnitude[high_mask].sum()
    ratio = high_energy / (low_energy + 1e-6)
    return {'freq_high_low_ratio': float(ratio)}

FREQ_KEYS = ['freq_high_low_ratio']

# ========== 特征总数 ==========
ALL_KEYS = LAB_KEYS + ROI_KEYS + FATIGUE_KEYS + HSV_KEYS + LBP_KEYS + GABOR_KEYS + GLCM_KEYS + REDNESS_KEYS + FREQ_KEYS
FEATURE_KEYS = ALL_KEYS
# 去重
seen = set()
FEATURE_KEYS = [k for k in ALL_KEYS if not (k in seen or seen.add(k))]
print(f'\n  v9特征总数: {len(FEATURE_KEYS)} 维')

# ========== 提取函数 ==========
def extract_features(img_path):
    """对单张图片提取全部v9特征"""
    result = {'file': os.path.basename(img_path)}
    img = cv2.imread(img_path)
    if img is None:
        result['face_detected'] = False
        result['error'] = '无法读取图片'
        for k in FEATURE_KEYS:
            result[k] = ''
        return result
    
    ok = True
    img_wb = apply_white_balance(img, wb_params)
    face_roi, face_full_roi, bbox = detect_face_by_skin(img_wb)
    
    if face_roi is None:
        result['face_detected'] = False
        result['error'] = '未检测到人脸'
        for k in FEATURE_KEYS:
            result[k] = ''
        return result
    
    result['face_detected'] = True
    result['face_area'] = bbox[2] * bbox[3] if bbox else 0
    result['img_size'] = f'{img.shape[1]}x{img.shape[0]}'
    
    # ===== 光照鲁棒特征管线 v2.0 =====
    # 第1步: 融合白平衡（纸参数 + GrayWorld）
    combined_wb = compute_combined_wb(face_roi, wb_params)
    face_roi_wb = apply_white_balance(face_roi, combined_wb)
    
    # 第2步: Retinex 单尺度反射率（光照不变表示）
    # 单尺度速度 ~3x 快于 MSR，在 3648x2736 的 ROI 上延迟从 3s 降到 1s
    face_retinex = retinex_ssr(face_roi_wb, sigma=30)
    
    # 第3步: 同态滤波（频域去光照，用于纹理分析）
    face_gray = cv2.cvtColor(face_roi_wb, cv2.COLOR_BGR2GRAY)
    face_homomorphic = homomorphic_filter(face_gray, cutoff_radius=40)
    
    # 提取各模块特征（使用 Retinex 反射率，光照无关）
    try:
        lab = analyze_skin_lab(face_retinex)
        for k, v in lab.items(): result[k] = v
    except Exception as e:
        print(f'  ⚠️ Lab分析失败: {e}')
        for k in LAB_KEYS: result[k] = ''
    
    try:
        roi = analyze_roi_features(face_retinex, face_full_roi)
        for k, v in roi.items(): result[k] = v
    except Exception as e:
        print(f'  ⚠️ ROI分析失败: {e}')
        for k in ROI_KEYS: result[k] = ''
    
    try:
        fatigue = analyze_fatigue_signs(face_retinex)
        for k, v in fatigue.items(): result[k] = v
    except Exception as e:
        print(f'  ⚠️ 疲劳分析失败: {e}')
        for k in FATIGUE_KEYS: result[k] = ''
    
    try:
        hsv = analyze_hsv(face_retinex)
        for k, v in hsv.items(): result[k] = v
    except Exception:
        for k in HSV_KEYS: result[k] = ''
    
    # 纹理分析使用同态滤波（频域去光照后更干净）
    try:
        small = cv2.resize(face_homomorphic, (256, 256))
    except:
        small = cv2.resize(face_gray, (256, 256))
    
    try:
        lbp = extract_lbp_features(small)
        for k, v in lbp.items(): result[k] = v
    except Exception:
        for k in LBP_KEYS: result[k] = ''
    
    try:
        gabor_f = extract_gabor_features(small)
        for k, v in gabor_f.items(): result[k] = v
    except Exception:
        for k in GABOR_KEYS: result[k] = ''
    
    try:
        glcm = extract_glcm_features(small)
        for k, v in glcm.items(): result[k] = v
    except Exception:
        for k in GLCM_KEYS: result[k] = ''
    
    try:
        redness = analyze_redness_advanced(face_roi)
        for k, v in redness.items(): result[k] = v
    except Exception:
        for k in REDNESS_KEYS: result[k] = ''
    
    try:
        gray_face = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        if gray_face.max() > 1:
            gray_face = gray_face / 255.0
        freq = analyze_freq(gray_face)
        for k, v in freq.items(): result[k] = v
    except Exception:
        for k in FREQ_KEYS: result[k] = ''
    
    return result

# ========== 批量处理 ==========
def batch_process():
    import pandas as pd
    
    date_dirs = sorted([d for d in os.listdir(BASE) if os.path.isdir(os.path.join(BASE, d)) and d.startswith('20')])
    
    all_rows = []
    total = 0
    detected = 0
    
    for date_dir in date_dirs:
        full_dir = os.path.join(BASE, date_dir)
        for fname in sorted(os.listdir(full_dir)):
            if not fname.lower().endswith(('.jpg','.png','.jpeg')): continue
            if 'whitebalance' in fname.lower(): continue
            if 'face' in fname.lower(): continue
            fpath = os.path.join(full_dir, fname)
            result = extract_features(fpath)
            result['date'] = date_dir
            result['file'] = fname
            
            gender = 'M' if '_man' in fname.lower() else 'F'
            result['gender'] = gender
            
            total += 1
            if total % 10 == 0:
                print(f'  [进度] 已处理 {total} 张...', flush=True)
            if result['face_detected']:
                detected += 1
                print(f'  {fname} ✅ ', end='')
                non_empty = sum(1 for k in FEATURE_KEYS if result.get(k) not in (None, '', 'nan'))
                n_all = len(FEATURE_KEYS)
                pct = non_empty / n_all * 100
                print(f'(特征: {non_empty}/{n_all}, {pct:.0f}%)', flush=True)
            else:
                print(f'  {fname} ❌ {result.get("error", "")}', flush=True)
            
            all_rows.append(result)
    
    print(f'\n{"="*60}')
    print(f'  v9 统计: 共{total}张, 检测到人脸{detected}张 ({detected/total*100:.0f}%)')
    
    df = pd.DataFrame(all_rows)
    out_path = os.path.join(OUT, 'facial_features_v9.csv')
    meta_cols = ['date','file','img_size','face_detected','face_area','total_algorithms','gender']
    val_cols = [c for c in FEATURE_KEYS if c in df.columns]
    cols = [c for c in meta_cols if c in df.columns] + val_cols
    df = df[cols]
    df.to_csv(out_path, index=False, encoding='utf-8')
    print(f'  输出: {out_path}')
    print(f'  列数: {len(cols)}')
    print(f'  [OK] v9 批量提取完成！')

if __name__ == '__main__':
    batch_process()
