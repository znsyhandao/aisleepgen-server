# -*- coding: utf-8 -*-
"""
最佳实践：用ResNet50做照片标注
- 零训练：直接用ImageNet预训练模型的倒数第二层做特征提取
- 你标注的430张照片做参考库 → 新照片找最近邻居投票
- 不修改原始文件，输出到 _auto_labeled/
"""
import os, cv2, numpy as np, pickle, shutil, sys, gc, re
import torch
import torch.nn as nn
import torchvision.transforms as T
import torchvision.models as models

BASE = r'D:\AISleepGen_Optimized\sleep-skin image database'
OUT = r'D:\AISleepGen_Optimized\sleep-skin image database\_auto_labeled'
MODEL_PATH = r'D:\AISleepGen_Optimized\_label_models'

os.makedirs(OUT, exist_ok=True)
os.makedirs(MODEL_PATH, exist_ok=True)

# Load ResNet50
print("Loading ResNet50...", flush=True)
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print("Device:", device, flush=True)

resnet = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
# 去掉最后一层分类层，用1024维特征向量
class FeatureExtractor(nn.Module):
    def __init__(self, base):
        super().__init__()
        self.features = nn.Sequential(*list(base.children())[:-1])
    def forward(self, x):
        return self.features(x).flatten(1)

model = FeatureExtractor(resnet).to(device).eval()
print("Model loaded", flush=True)

# Image transforms
transform = T.Compose([
    T.ToPILImage(),
    T.Resize((224, 224)),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

def extract_feature(img_bgr):
    """从BGR图像提取1024维特征"""
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    tensor = transform(img_rgb).unsqueeze(0).to(device)
    with torch.no_grad():
        feat = model(tensor).cpu().numpy().flatten()
    return feat

# ===== 构建参考库 =====
def build_reference():
    ref_path = os.path.join(MODEL_PATH, 'reference.pkl')
    if os.path.exists(ref_path):
        print("Loading cached reference...", flush=True)
        with open(ref_path, 'rb') as f: return pickle.load(f)

    print("Building reference library from labeled photos...", flush=True)
    refs = []  # [(feature, gender, angle, date, fn), ...]
    
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
                is_f = 'front' in fl; is_l = 'left' in fl; is_r = 'right' in fl
                if not is_f and not is_l and not is_r: continue
                
                g = cv2.imread(fp)
                if g is None: continue
                try:
                    feat = extract_feature(g)
                except:
                    continue
                
                gender = 'woman' if has_w else 'man'
                angle = 'front' if is_f else 'left' if is_l else 'right'
                refs.append((feat, gender, angle, d, fn))
                
                if len(refs) % 50 == 0:
                    print("  %d photos processed..." % len(refs), flush=True)
                    gc.collect()
    
    with open(ref_path, 'wb') as f: pickle.dump(refs, f)
    print("Reference: %d photos" % len(refs), flush=True)
    return refs

print("Building reference...", flush=True)
refs = build_reference()

# 构建特征矩阵
ref_feats = np.array([r[0] for r in refs])
ref_genders = [r[1] for r in refs]
ref_angles = [r[2] for r in refs]

from sklearn.preprocessing import StandardScaler
scaler = StandardScaler()
ref_feats_norm = scaler.fit_transform(ref_feats)

# ===== 标注指定日期 =====
def label_day(date_str, k=11):
    src_dir = os.path.join(BASE, date_str)
    if not os.path.isdir(src_dir): return
    
    out_dir = os.path.join(OUT, date_str)
    os.makedirs(out_dir, exist_ok=True)
    
    # 收集所有照片
    photos = []
    for root, dirs_inner, files in os.walk(src_dir):
        for fn in files:
            if fn.lower().endswith('.jpg'):
                photos.append((fn, root))
    
    print("\n标注 %s (%d张):" % (date_str, len(photos)), flush=True)
    print("=" * 60)
    
    for fn, root_dir in sorted(photos):
        fl = fn.lower()
        fp = os.path.join(root_dir, fn)
        
        # 跳过已有标签的
        has_w, has_m = 'woman' in fl, (os.path.basename(root_dir) == 'man' or '_man_' in fl or fl.startswith('man_'))
        ex_g = ('woman' if has_w else 'man') if (has_w or has_m) else None
        ex_a = ('front' if 'front' in fl else 'left' if 'left' in fl else 'right' if 'right' in fl else None)
        has_angle_label = ex_a is not None
        has_label = ex_g is not None and has_angle_label
        if has_label:
            shutil.copy2(fp, os.path.join(out_dir, fn))
            print("  [已有] %s/%s | %s" % (ex_g, ex_a, fn[:45]))
            continue
        
        # 从文件名推断性别（首选方式，文件名_man_和_woman_是手动标注）
        inferred_gender = None
        fl_no_woman = fl.replace('woman', '')  # 去除woman关键词，避免_man_woman冲突
        has_man_marker = bool(re.search(r'_man[_.]', fl_no_woman))
        if has_man_marker or os.path.basename(root_dir) == 'man':
            inferred_gender = 'man'
        elif 'woman' in fl:
            inferred_gender = 'woman'
        
        # 从文件名推断角度（文件名已有 front/left/right 的直接使用）
        inferred_angle = None
        if 'front' in fl: inferred_angle = 'front'
        elif 'left' in fl: inferred_angle = 'left'
        elif 'right' in fl: inferred_angle = 'right'
        
        # 已有完整标签的直接复制
        if inferred_gender is not None and inferred_angle is not None:
            base, ext = os.path.splitext(fn)
            tag = '%s_%s' % (inferred_gender, inferred_angle)
            if '_%s_' % tag not in fn and not fn.endswith('_%s%s' % (tag, ext)):
                new_fn = '%s_%s_%s%s' % (base, inferred_gender, inferred_angle, ext)
            else:
                new_fn = fn
            shutil.copy2(fp, os.path.join(out_dir, new_fn))
            print('  [已有] %s/%s | %s' % (inferred_gender, inferred_angle, new_fn[:45]))
            continue
        
        # 只有性别已知 + 角度未知：只标性别，不标角度
        if inferred_gender is not None:
            base, ext = os.path.splitext(fn)
            new_fn = '%s_%s%s' % (base, inferred_gender, ext)
            shutil.copy2(fp, os.path.join(out_dir, new_fn))
            print('  [性别] %s/？ → %s' % (inferred_gender, new_fn[:50]))
            continue
        
        # 既无性别也无角度：用ResNet50预测性别，角度留空
        g = cv2.imread(fp)
        if g is None:
            print("  [!!] 读不了 | %s" % fn[:45])
            continue
        
        try:
            feat = extract_feature(g)
        except Exception as e:
            print("  [!!] 特征失败: %s" % str(e)[:30])
            continue
        
        # 找最近邻
        feat_norm = scaler.transform([feat])
        dists = np.linalg.norm(ref_feats_norm - feat_norm, axis=1)
        idxs = np.argsort(dists)[:k]
        
        # 性别预测（ResNet50最近邻）
        neighbor_genders = [ref_genders[i] for i in idxs]
        gender = max(set(neighbor_genders), key=neighbor_genders.count)
        g_conf = neighbor_genders.count(gender) / k * 100
        
        base, ext = os.path.splitext(fn)
        new_fn = "%s_%s%s" % (base, gender, ext)
        print("  [%3d%%/%s] %s → %s" % (g_conf, 'ResNet', gender, new_fn[:50]))
        shutil.copy2(fp, os.path.join(out_dir, new_fn))
        shutil.copy2(fp, os.path.join(out_dir, new_fn))

    print("=" * 60)
    print("完成! %s" % out_dir)

if __name__ == '__main__':
    date_str = sys.argv[1] if len(sys.argv) > 1 else '20260512'
    label_day(date_str)
