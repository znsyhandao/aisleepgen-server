# -*- coding: utf-8 -*-
"""第一步：训练分类器并保存模型"""
import os, cv2, numpy as np, pickle
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler

BASE = r'D:\AISleepGen_Optimized\sleep-skin image database'

def extract_gf(gray):
    f = [float(np.mean(gray)), float(np.std(gray)), float(np.percentile(gray, 25)), float(np.percentile(gray, 75))]
    h, w = gray.shape
    for i in range(4):
        for j in range(4):
            b = gray[i*h//4:(i+1)*h//4, j*w//4:(j+1)*w//4]
            f.extend([float(np.mean(b)), float(np.std(b))] if b.size > 0 else [0.0, 0.0])
    return f

def extract_af(gray):
    h, w = gray.shape
    f = [float(np.mean(gray[:, :w//2])), float(np.mean(gray[:, w//2:])),
         float(np.mean(gray[:, :w//2]) - np.mean(gray[:, w//2:])),
         float(np.std(gray[:, :w//2]) - np.std(gray[:, w//2:]))]
    try:
        sx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
        sy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
        f.extend([float(np.mean(np.abs(sx))), float(np.mean(np.abs(sy)))])
        f.extend([float(np.mean(np.abs(sx[:,:w//2]))), float(np.mean(np.abs(sx[:,w//2:])))])
    except:
        f.extend([0.0]*4)
    return f

print("Collecting training data...", flush=True)
gX, gy, aX, ay = [], [], [], []
for d in sorted([x for x in os.listdir(BASE) if x.isdigit() and len(x)==8]):
    dp = os.path.join(BASE, d)
    for root, dirs_inner, files in os.walk(dp):
        sub = os.path.basename(root)
        for fn in files:
            if not fn.lower().endswith('.jpg'): continue
            fl = fn.lower()
            fp = os.path.join(root, fn)
            has_w = 'woman' in fl
            has_m = sub == 'man' or ('_man_' in fl or fl.startswith('man_'))
            if not has_w and not has_m: continue
            is_f, is_l, is_r = 'front' in fl, 'left' in fl, 'right' in fl
            if not is_f and not is_l and not is_r: continue
            g = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
            if g is None or g.size < 100: continue
            gf, af = extract_gf(g), extract_af(g)
            if gf is None or af is None: continue
            gX.append(gf); gy.append(0 if has_m else 1)
            aX.append(af); ay.append(0 if is_f else 1 if is_l else 2)

print("gX=%d aX=%d" % (len(gX), len(aX)), flush=True)

gs = StandardScaler()
gc = SVC(kernel='rbf', probability=True, random_state=42)
gc.fit(gs.fit_transform(np.array(gX)), gy)

ass = StandardScaler()
ac = SVC(kernel='rbf', probability=True, random_state=42)
ac.fit(ass.fit_transform(np.array(aX)), ay)

with open('gender_model.pkl', 'wb') as f: pickle.dump((gs, gc), f)
with open('angle_model.pkl', 'wb') as f: pickle.dump((ass, ac), f)
print("Models saved to gender_model.pkl, angle_model.pkl", flush=True)
