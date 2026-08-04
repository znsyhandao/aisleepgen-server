"""调试：测试训练过程"""
import os, cv2, numpy as np
print("Import OK", flush=True)

BASE = r'D:\AISleepGen_Optimized\sleep-skin image database'

def extract_gf(gray):
    try:
        f = [float(np.mean(gray)), float(np.std(gray)), float(np.percentile(gray, 25)), float(np.percentile(gray, 75))]
        h, w = gray.shape
        for i in range(4):
            for j in range(4):
                b = gray[i*h//4:(i+1)*h//4, j*w//4:(j+1)*w//4]
                f.extend([float(np.mean(b)), float(np.std(b))] if b.size > 0 else [0.0, 0.0])
        return f
    except Exception as e:
        print("extract_gf error:", e, flush=True)
        return None

print("Testing train...", flush=True)
dirs = sorted([d for d in os.listdir(BASE) if d.isdigit() and len(d)==8])
count = 0
for d in dirs:
    dp = os.path.join(BASE, d)
    for fn in os.listdir(dp):
        if count >= 5: break
        fl = fn.lower()
        if not any(k in fl for k in ['woman','man','front','left','right']): continue
        fp = os.path.join(dp, fn)
        print("Reading:", fn[:40], flush=True)
        g = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
        print("  shape:", g.shape if g is not None else "None", flush=True)
        count += 1
    if count >= 5: break
print("Done", flush=True)
