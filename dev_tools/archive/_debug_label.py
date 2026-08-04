"""测试单文件标注"""
import os, cv2, numpy as np, pickle, sys, shutil, gc, torch, torch.nn as nn
import torchvision.transforms as T
import torchvision.models as models

BASE = r'D:\AISleepGen_Optimized\sleep-skin image database'
OUT = r'D:\AISleepGen_Optimized\sleep-skin image database\_auto_labeled'

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
resnet = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
class FeatExt(nn.Module):
    def __init__(self, base):
        super().__init__()
        self.features = nn.Sequential(*list(base.children())[:-1])
    def forward(self, x): return self.features(x).flatten(1)
model = FeatExt(resnet).to(device).eval()
transform = T.Compose([T.ToPILImage(), T.Resize((224, 224)), T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])])

def extract_feat(img_bgr):
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    t = transform(img_rgb).unsqueeze(0).to(device)
    with torch.no_grad(): return model(t).cpu().numpy().flatten()

with open(r'D:\AISleepGen_Optimized\_label_models\reference.pkl', 'rb') as f: refs = pickle.load(f)
ref_feats = np.array([r[0] for r in refs])
ref_genders = [r[1] for r in refs]
ref_angles = [r[2] for r in refs]
from sklearn.preprocessing import StandardScaler
scaler = StandardScaler()
ref_feats_norm = scaler.fit_transform(ref_feats)

# 测试 _man_woman_right 文件
fn = 'IMG_20260513_071101_man_woman_right.jpg'
fp = os.path.join(BASE, '20260513', fn)
print('File:', fn, flush=True)
fl = fn.lower()
fl_no_woman = fl.replace('woman', '')
has_man = '_man_' in fl_no_woman or fl_no_woman.startswith('man_')
has_woman = 'woman' in fl
print('has_man=%s has_woman=%s' % (has_man, has_woman), flush=True)

# 这是推理路径
g = cv2.imread(fp)
feat = extract_feat(g)
fnorm = scaler.transform([feat])
dists = np.linalg.norm(ref_feats_norm - fnorm, axis=1)
idxs = np.argsort(dists)[:11]
neighbor_g = [ref_genders[i] for i in idxs]
neighbor_a = [ref_angles[i] for i in idxs]
print('Neighbors gender:', neighbor_g, flush=True)
print('Neighbors angle:', neighbor_a, flush=True)
max_g = max(set(neighbor_g), key=neighbor_g.count)
max_a = max(set(neighbor_a), key=neighbor_a.count)
print('Vote: gender=%s(%d%%) angle=%s(%d%%)' % (max_g, neighbor_g.count(max_g)/11*100, max_a, neighbor_a.count(max_a)/11*100), flush=True)
print('DONE', flush=True)
