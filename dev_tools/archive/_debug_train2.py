"""调试：测试完整训练"""
import os, cv2, numpy as np
print("Step 0: import ok", flush=True)
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
    left, right = gray[:, :w//2], gray[:, w//2:]
    f = [float(np.mean(left)), float(np.mean(right)), float(np.mean(left)-np.mean(right)), float(np.std(left)-np.std(right))]
    sx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
    sy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    f.extend([float(np.mean(np.abs(sx))), float(np.mean(np.abs(sy)))])
    f.extend([float(np.mean(np.abs(sx[:,:w//2]))), float(np.mean(np.abs(sx[:,w//2:])))])
    return f

print("Step 1: scanning dirs", flush=True)
gX, gy, aX, ay = [], [], [], []
dirs = sorted([d for d in os.listdir(BASE) if d.isdigit() and len(d)==8])
print("  dirs:", len(dirs), flush=True)

for d in dirs:
    dp = os.path.join(BASE, d)
    for fn in os.listdir(dp):
        if not fn.lower().endswith('.jpg'): continue
        fl = fn.lower()
        if not any(k in fl for k in ['woman','man','front','left','right']): continue
        fp = os.path.join(dp, fn)
        g = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
        if g is None: continue
        gf = extract_gf(g)
        af = extract_af(g)
        has_w, has_m = 'woman' in fl, ('_man_' in fl or fl.startswith('man_'))
        if has_w or has_m:
            gX.append(gf); gy.append(0 if has_m else 1)
        is_f, is_l, is_r = 'front' in fl, 'left' in fl, 'right' in fl
        if is_f or is_l or is_r:
            aX.append(af); ay.append(0 if is_f else 1 if is_l else 2)

print("Step 2: train data g=%d a=%d" % (len(gX), len(aX)), flush=True)

from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler

print("Step 3: sklearn imported", flush=True)

gs = StandardScaler()
print("Step 4: scaler created", flush=True)
Xg = gs.fit_transform(np.array(gX))
print("Step 5: gender X transformed, shape=%s" % str(Xg.shape), flush=True)

gc = SVC(kernel='rbf', probability=True, random_state=42)
gc.fit(Xg, gy)
print("Step 6: gender classifier trained", flush=True)

ass = StandardScaler()
Xa = ass.fit_transform(np.array(aX))
ac = SVC(kernel='rbf', probability=True, random_state=42)
ac.fit(Xa, ay)
print("Step 7: angle classifier trained", flush=True)

# 测试预测一个已有标签的照片
print("Step 8: testing prediction...", flush=True)
g_pred = gc.predict([Xg[0]])[0]
a_pred = ac.predict([Xa[0]])[0]
print("  gender: %s (expected %s)" % (['man','woman'][g_pred], ['man','woman'][gy[0]]), flush=True)
print("  angle: %s (expected %s)" % (['front','left','right'][a_pred], ['front','left','right'][ay[0]]), flush=True)
print("DONE", flush=True)
