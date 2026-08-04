import pandas as pd, sys, os
sys.stdout.reconfigure(encoding='utf-8')

new = pd.read_csv('D:/AISleepGen_Optimized/sleep-skin features/facial_features_v9.csv')
old = pd.read_csv('D:/AISleepGen_Optimized/sleep-skin features/facial_features_v9_backup_20260510.csv')

old_files = set(old['file'].tolist())
new['in_old'] = new['file'].isin(old_files)

new_det = new['face_detected'].astype(str).str.lower().str.strip() == 'true'

# 旧照片在新版中的检测率
old_photos = new[new['in_old']]
old_det = new_det[new['in_old']]
print(f'旧照片在新版中: {old_det.sum()}/{len(old_photos)}({old_det.sum()/len(old_photos)*100:.0f}%)')

# 新版新增照片
new_photos = new[~new['in_old']]
new_det2 = new_det[~new['in_old']]
print(f'新增照片: {new_det2.sum()}/{len(new_photos)}({new_det2.sum()/len(new_photos)*100:.0f}%)')

# 按日期
print('\n按日期检测率:')
for d in sorted(new['date'].unique()):
    dd = new[new['date'].astype(str).str.strip() == str(d)]
    det = new_det[new['date'].astype(str).str.strip() == str(d)]
    print(f'  {d}: {det.sum()}/{len(dd)} = {det.sum()/len(dd)*100:.0f}%')
