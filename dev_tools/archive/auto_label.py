# -*- coding: utf-8 -*-
"""
自动标注 — 示范版：只标注指定日期的照片，输出到 _auto_labeled/
不修改原始文件
支持：文件名后缀 woman/man + 子目录 man + 未标注照片
"""
import os, cv2, numpy as np, shutil, sys
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler

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
    left, right = gray[:, :w//2], gray[:, w//2:]
    f = [float(np.mean(left)), float(np.mean(right)), float(np.mean(left)-np.mean(right)), float(np.std(left)-np.std(right))]
    try:
        sx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
        sy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
        f.extend([float(np.mean(np.abs(sx))), float(np.mean(np.abs(sy)))])
        if w >= 4:
            f.extend([float(np.mean(np.abs(sx[:,:w//2]))), float(np.mean(np.abs(sx[:,w//2:])))])
        else:
            f.extend([0.0, 0.0])
    except:
        f.extend([0.0, 0.0, 0.0, 0.0])
    return f

def get_training_photos():
    """从目录+子目录收集所有标注照片"""
    gX, gy, aX, ay = [], [], [], []
    dirs = sorted([d for d in os.listdir(BASE) if d.isdigit() and len(d)==8])
    for d in dirs:
        dp = os.path.join(BASE, d)
        if not os.path.isdir(dp): continue
        # 扫描顶层和子目录
        for root, dirs_inner, files in os.walk(dp):
            subdir_name = os.path.basename(root)
            gender_from_dir = subdir_name if subdir_name in ['man'] else None
            
            for fn in files:
                if not fn.lower().endswith('.jpg'): continue
                fl = fn.lower()
                fp = os.path.join(root, fn)
                
                # 确定gender
                has_w = 'woman' in fl
                has_m = gender_from_dir == 'man' or ('_man_' in fl or fl.startswith('man_'))
                if not has_w and not has_m:
                    continue  # 跳过未标注的（只用于训练）
                
                # 确定角度
                is_front = 'front' in fl
                is_left = 'left' in fl
                is_right = 'right' in fl
                if not is_front and not is_left and not is_right:
                    continue  # 无角度的不用于角度训练
                
                if len(gX) >= 500:  # 限制训练集大小防止内存问题
                    break
                if len(aX) >= 500:
                    break
                
                try:
                    g = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
                    if g is None or g.size < 100: continue
                except:
                    continue
                
                gf = extract_gf(g)
                af = extract_af(g)
                if gf is None or af is None: continue
                
                gX.append(gf)
                gy.append(0 if has_m else 1)
                aX.append(af)
                ay.append(0 if is_front else 1 if is_left else 2)
    
    return gX, gy, aX, ay

def train_classifiers():
    print("开始训练分类器...", flush=True)
    gX, gy, aX, ay = get_training_photos()
    print("训练数据: gender=%d张 angle=%d张" % (len(gX), len(aX)), flush=True)
    
    if len(gX) < 10 or len(aX) < 10:
        print("[ERROR] 数据不足", flush=True)
        return None, None, None, None
    
    gs = StandardScaler()
    gc = SVC(kernel='rbf', probability=True, random_state=42)
    gc.fit(gs.fit_transform(np.array(gX)), gy)
    
    ass = StandardScaler()
    ac = SVC(kernel='rbf', probability=True, random_state=42)
    ac.fit(ass.fit_transform(np.array(aX)), ay)
    
    print("训练完成", flush=True)
    return gc, gs, ac, ass

def label_one_day(date_str):
    """标注一个日期的照片到输出目录"""
    gc, gs, ac, ass = train_classifiers()
    if gc is None: return
    
    anames = ['front_view', 'left_side_view', 'right_side_view']
    gnames = ['man', 'woman']
    
    src_dir = os.path.join(BASE, date_str)
    if not os.path.isdir(src_dir):
        print("[ERROR] %s 目录不存在" % date_str)
        return
    
    out_dir = os.path.join(OUT, date_str)
    os.makedirs(out_dir, exist_ok=True)
    
    # 搜集src_dir下所有jpg（包括子目录）
    photos = []
    for root, dirs_inner, files in os.walk(src_dir):
        for fn in files:
            if fn.lower().endswith('.jpg'):
                rel = os.path.relpath(os.path.join(root, fn), src_dir)
                photos.append((fn, root, rel))
    
    print("处理 %s (%d张照片):" % (date_str, len(photos)))
    
    all_predicted = []
    for fn, root_dir, rel in sorted(photos):
        fl = fn.lower()
        fp = os.path.join(root_dir, fn)
        
        # 已有的标签
        has_label = any(k in fl for k in ['woman','man','front','left','right'])
        if has_label:
            # 推断已有gender
            has_w = 'woman' in fl
            has_m = '_man_' in fl or fl.startswith('man_')
            gender = 'woman' if has_w else 'man' if has_m else '?'
            if 'front' in fl: angle = 'front'
            elif 'left' in fl: angle = 'left'
            elif 'right' in fl: angle = 'right'
            else: angle = '?'
            shutil.copy2(fp, os.path.join(out_dir, fn))
            all_predicted.append((fn, gender, angle, '已标注'))
            continue
        
        g = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
        if g is None:
            all_predicted.append((fn, '?', '?', '无法读取'))
            continue
        
        gf = extract_gf(g)
        af = extract_af(g)
        if gf is None or af is None:
            all_predicted.append((fn, '?', '?', '特征提取失败'))
            continue
        
        pg = gnames[gc.predict(gs.transform([gf]))[0]]
        pa = anames[ac.predict(ass.transform([af]))[0]]
        
        base, ext = os.path.splitext(fn)
        new_fn = "%s_%s_%s%s" % (base, pg, pa.replace('_view',''), ext)
        shutil.copy2(fp, os.path.join(out_dir, new_fn))
        all_predicted.append((fn, pg, pa.replace('_view',''), '自动标注'))
    
    # 打印结果
    print("\n标注结果:")
    print("-" * 60)
    for fn, g, a, status in all_predicted:
        print("  [%-4s] %s/%s | %s" % (status, g, a, fn[:50]))
    
    print("\n标注完成！文件在: %s" % out_dir)
    print("请检查标注是否正确。")

if __name__ == '__main__':
    date_str = sys.argv[1] if len(sys.argv) > 1 else '20260512'
    label_one_day(date_str)
