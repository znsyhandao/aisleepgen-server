# -*- coding: utf-8 -*-
import shutil, os, time, py_compile

d = r'D:\AISleepGen_Optimized\.surgical_backups'
os.makedirs(d, exist_ok=True)
ts = time.strftime('%Y%m%d_%H%M%S')

pairs = [
    (r'D:\AISleepGen_Optimized', 'deepseek_proxy.py'),
    (r'D:\super_frontier_radar', 'heartbeat_orchestrator.py'),
]

for base, fn in pairs:
    src = os.path.join(base, fn)
    bfn = fn.replace('.py', '')
    name = os.path.join(d, f'{bfn}_{ts}_x2x3.py')
    shutil.copy2(src, name)
    print(f'Backup: {os.path.basename(name)}')

# verify compile
for base, fn in pairs:
    py_compile.compile(os.path.join(base, fn), doraise=True)

print('All PASS')
