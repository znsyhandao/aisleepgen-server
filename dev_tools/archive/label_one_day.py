# -*- coding: utf-8 -*-
"""第二步：用训练好的模型标注指定日期，输出到 _auto_labeled/"""
import os, cv2, numpy as np, pickle, shutil, sys

BASE = r'D:\AISleepGen_Optimized\sleep-skin image database'
OUT = r'D:\AISleepGen_Optimized\sleep-skin image database\_auto_labeled'

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

# 加载模型
with open(r'D:\AISleepGen_Optimized\gender_model.pkl', 'rb') as f: gs, gc = pickle.load(f)
with open(r'D:\AISleepGen_Optimized\angle_model.pkl', 'rb') as f: ass, ac = pickle.load(f)

date_str = sys.argv[1] if len(sys.argv) > 1 else '20260512'
src_dir = os.path.join(BASE, date_str)
if not os.path.isdir(src_dir):
    print("ERROR: 目录 %s 不存在" % src_dir)
    sys.exit(1)

out_dir = os.path.join(OUT, date_str)
os.makedirs(out_dir, exist_ok=True)

anames = ['front_view', 'left_side_view', 'right_side_view']
gnames = ['man', 'woman']

# 收集所有jpg
photos = []
for root, dirs_inner, files in os.walk(src_dir):
    for fn in files:
        if fn.lower().endswith('.jpg'):
            photos.append((fn, root))

print("处理 %s (%d张照片):" % (date_str, len(photos)))
print("=" * 60)

for fn, root_dir in sorted(photos):
    fl = fn.lower()
    fp = os.path.join(root_dir, fn)
    
    # 已有标签直接复制
    has_w = 'woman' in fl
    has_m = os.path.basename(root_dir) == 'man' or ('_man_' in fl or fl.startswith('man_'))
    ex_g = ('woman' if has_w else 'man') if (has_w or has_m) else '-'
    ex_a = ('front' if 'front' in fl else 'left' if 'left' in fl else 'right' if 'right' in fl else '-')
    has_label = (has_w or has_m) and (ex_a != '-')
    
    if has_label:
        shutil.copy2(fp, os.path.join(out_dir, fn))
        print("  [已有] %s/%s | %s" % (ex_g, ex_a, fn[:45]))
        continue
    
    g = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
    if g is None:
        print("  [!!] 无法读取 | %s" % fn[:45])
        continue
    
    gf = extract_gf(g)
    af = extract_af(g)
    if gf is None or af is None:
        print("  [!!] 特征失败 | %s" % fn[:45])
        continue
    
    pg = gnames[gc.predict(gs.transform([gf]))[0]]
    pa = anames[ac.predict(ass.transform([af]))[0]]
    prob = np.max(gc.predict_proba(gs.transform([gf]))[0]) * 100
    
    base, ext = os.path.splitext(fn)
    new_fn = "%s_%s_%s%s" % (base, pg, pa.replace('_view',''), ext)
    shutil.copy2(fp, os.path.join(out_dir, new_fn))
    print("  [%.0f%%] %s/%s → %s" % (prob, pg, pa.replace('_view',''), new_fn[:50]))

print("=" * 60)
print("完成！文件在: %s" % out_dir)
