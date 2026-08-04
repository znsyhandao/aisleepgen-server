"""全量预测未标注照片"""
import os, cv2, numpy as np
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler

BASE = r'D:\AISleepGen_Optimized\sleep-skin image database'

def extract_gf(gray):
    if gray is None or gray.size == 0: return None
    f = [float(np.mean(gray)), float(np.std(gray)), 
         float(np.percentile(gray, 25)), float(np.percentile(gray, 75))]
    h, w = gray.shape
    for i in range(4):
        for j in range(4):
            b = gray[i*h//4:(i+1)*h//4, j*w//4:(j+1)*w//4]
            if b.size > 0:
                f.extend([float(np.mean(b)), float(np.std(b))])
            else:
                f.extend([0.0, 0.0])
    return f

def extract_af(gray):
    if gray is None or gray.size == 0: return None
    h, w = gray.shape
    left, right = gray[:, :w//2], gray[:, w//2:]
    f = [float(np.mean(left)), float(np.mean(right)), 
         float(np.mean(left) - np.mean(right)),
         float(np.std(left) - np.std(right))]
    sx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
    sy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    f.extend([float(np.mean(np.abs(sx))), float(np.mean(np.abs(sy)))])
    f.extend([float(np.mean(np.abs(sx[:, :w//2]))), float(np.mean(np.abs(sx[:, w//2:])))])
    return f

gX, gy, aX, ay = [], [], [], []
dirs = sorted([d for d in os.listdir(BASE) if d.isdigit() and len(d)==8])
print("Building training data from %d dirs..." % len(dirs))

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
        has_w = 'woman' in fl
        has_m = '_man_' in fl or fl.startswith('man_')
        if gf and (has_w or has_m):
            gX.append(gf)
            gy.append(0 if has_m else 1)
        if af:
            is_front = 'front' in fl
            is_left = 'left' in fl
            is_right = 'right' in fl
            if is_front or is_left or is_right:
                aX.append(af)
                ay.append(0 if is_front else 1 if is_left else 2)

print("Training: gender=%d, angle=%d" % (len(gX), len(aX)))

gs = StandardScaler()
gc = SVC(kernel='rbf', probability=True, random_state=42)
gc.fit(gs.fit_transform(np.array(gX)), gy)

ass = StandardScaler()
ac = SVC(kernel='rbf', probability=True, random_state=42)
ac.fit(ass.fit_transform(np.array(aX)), ay)

anames = ['front_view', 'left_side_view', 'right_side_view']
gnames = ['man', 'woman']

total, predicted, noface = 0, 0, 0
print("\nPredicting unseen photos...")
for d in dirs:
    dp = os.path.join(BASE, d)
    for fn in os.listdir(dp):
        if not fn.lower().endswith('.jpg'): continue
        if any(k in fn.lower() for k in ['woman','man','front','left','right']): continue
        total += 1
        g = cv2.imread(os.path.join(dp, fn), cv2.IMREAD_GRAYSCALE)
        if g is None:
            noface += 1
            continue
        gf = extract_gf(g)
        af = extract_af(g)
        if gf is None or af is None:
            noface += 1
            continue
        pg = gnames[gc.predict(gs.transform([gf]))[0]]
        pa = anames[ac.predict(ass.transform([af]))[0]]
        predicted += 1
        if predicted <= 10:
            print("  %s/%s | %s" % (pg, pa.replace('_view',''), fn[:55]))

print("\nSummary: total=%d predicted=%d noface=%d" % (total, predicted, noface))
