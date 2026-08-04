import os, sys, time
sys.stdout.reconfigure(encoding='utf-8')
pycache = r'D:\AISleepGen_Optimized\__pycache__'
if os.path.exists(pycache):
    for f in sorted(os.listdir(pycache)):
        if 'deepseek' in f:
            fp = os.path.join(pycache, f)
            mtime = os.path.getmtime(fp)
            ftime = time.strftime('%H:%M:%S', time.localtime(mtime))
            size = os.path.getsize(fp)
            print(f'{f}: {ftime} ({size} bytes)')
else:
    print('no pycache')
