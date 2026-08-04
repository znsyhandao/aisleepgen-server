# -*- coding: utf-8 -*-
"""Background EDF download - single file, patient, with recovery"""
import os, time, urllib.request

DATA_DIR = r'D:\AISleepGen_Optimized\data\edf\mendeley_insomnia'
os.makedirs(DATA_DIR, exist_ok=True)

# Clean any zero-byte remnants
for f in os.listdir(DATA_DIR):
    p = os.path.join(DATA_DIR, f)
    if f.endswith('.edf') and os.path.getsize(p) == 0:
        os.remove(p)

# Target files
TARGETS = [
    ('Normal_Subject_01.edf', '1fc96698-86d7-4f8e-be63-346a15ceb20f', 371605246),
    ('Raw_Signal_Psycophysiological_Insomnia_10.edf', 'e7e07ff2-a3d4-4464-a086-75b7e8feb45b', 370827502),
]

BASE = 'https://data.mendeley.com/public-files/datasets/3hx58k232n/files/{fid}/file_downloaded'
ALT_BASE = 'https://data.mendeley.com/v1/datasets/3hx58k232n/files/{fid}/download'

for fname, fid, expected_size in TARGETS:
    dst = os.path.join(DATA_DIR, fname)
    if os.path.exists(dst):
        sz = os.path.getsize(dst)
        if sz == expected_size:
            print(f'[✓] {fname}: already complete ({sz/1e6:.0f}MB)')
            continue
        elif sz > 0:
            print(f'[!] {fname}: partial {sz/1e6:.0f}MB, resuming...')
            # Try to resume using Range header (if server supports)
        else:
            os.remove(dst)
    
    print(f'[DL] {fname} ({expected_size/1e6:.0f}MB)')
    success = False
    
    for attempt in range(5):
        urls = [BASE.format(fid=fid), ALT_BASE.format(fid=fid)]
        for url in urls:
            t0 = time.time()
            try:
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'
                })
                with urllib.request.urlopen(req, timeout=1800) as resp:
                    with open(dst, 'wb') as f:
                        while True:
                            chunk = resp.read(8*1024*1024)
                            if not chunk:
                                break
                            f.write(chunk)
                
                sz = os.path.getsize(dst)
                if sz == expected_size:
                    elapsed = time.time() - t0
                    speed = sz/1e6/elapsed if elapsed > 0 else 0
                    print(f'[✓] {fname}: {sz/1e6:.0f}MB in {elapsed:.0f}s ({speed:.1f}MB/s)')
                    success = True
                    break
                else:
                    print(f'[!] Size mismatch: {sz}/{expected_size}')
                    os.remove(dst)
            except Exception as e:
                if os.path.exists(dst) and os.path.getsize(dst) == 0:
                    os.remove(dst)
                elapsed = time.time() - t0
                print(f'  Attempt {attempt+1}/5 ({elapsed:.0f}s): {e}')
                time.sleep(10)
        
        if success:
            break
    
    if not success:
        print(f'[✗] {fname}: FAILED after 5 attempts')

print(f'\nStatus:')
for f in sorted(os.listdir(DATA_DIR)):
    if f.endswith('.edf'):
        sz = os.path.getsize(os.path.join(DATA_DIR, f))
        print(f'  {"✓" if sz > 0 else "✗"} {f}: {sz/1e6:.0f}MB')
