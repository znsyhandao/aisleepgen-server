# -*- coding: utf-8 -*-
import shutil, os, time, py_compile
f = r'D:\AISleepGen_Optimized\deepseek_proxy.py'
d = r'D:\AISleepGen_Optimized\.surgical_backups'
os.makedirs(d, exist_ok=True)
ts = time.strftime('%Y%m%d_%H%M%S')
name = os.path.join(d, f'deepseek_proxy_{ts}_creative_batch.py')
shutil.copy2(f, name)
print(f'Backup: {os.path.basename(name)}')
try:
    py_compile.compile(f, doraise=True)
    print('Compile: PASS')
except Exception as e:
    print(f'Compile: FAIL {e}')
# also backup trajectory_model_db
f2 = r'D:\AISleepGen_Optimized\trajectory_model_db.py'
name2 = os.path.join(d, f'trajectory_model_db_{ts}_creative.py')
shutil.copy2(f2, name2)
print(f'Backup: {os.path.basename(name2)}')
