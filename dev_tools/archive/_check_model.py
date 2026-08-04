# -*- coding: utf-8 -*-
import pickle, os, sys

sys.stdout.reconfigure(encoding='utf-8')

backup_dir = r'D:\AISleepGen_Optimized\.surgical_backups'

for fname in ['trajectory_lgb_20260706_102109_32samples.pkl',
              'trajectory_lgb_20260706_094223_31samples.pkl']:
    fp = os.path.join(backup_dir, fname)
    if not os.path.exists(fp):
        print(f'{fname}: NOT FOUND')
        continue
    d = pickle.load(open(fp, 'rb'))
    print(f'{fname}')
    print(f'   n={d["n"]}')
    print(f'   features={d["features"]}')
    model = d['model']
    print(f'   model type: {type(model).__name__}')
    if hasattr(model, 'best_iteration'):
        print(f'   best_iteration={model.best_iteration}')
    print()

# 检查production模型
prod_pkl = r'D:\AISleepGen_Optimized\data\lgbm_tracker_model.pkl'
if os.path.exists(prod_pkl):
    print(f'Production模型存在: {os.path.getsize(prod_pkl)/1024:.0f}KB')
else:
    print('Production模型 data/lgbm_tracker_model.pkl: 不存在')
