# -*- coding: utf-8 -*-
"""Download EDF using Mendeley data.caltech.edu mirror"""
import os, time, urllib.request

DATA_DIR = r'D:\AISleepGen_Optimized\data\edf\mendeley_insomnia'
os.makedirs(DATA_DIR, exist_ok=True)

# File mappings: (local_name, file_id, expected_size)
# Got from the dataset API
FILES = {
    'Normal_Subject_01.edf': {
        'id': '1fc96698-86d7-4f8e-be63-346a15ceb20f',
        'size': 371605246
    },
    'Raw_Signal_Psycophysiological_Insomnia_10.edf': {
        'id': 'e7e07ff2-a3d4-4464-a086-75b7e8feb45b',
        'size': 370827502
    }
}

# Mendeley download from public-files (the one that works but slow)
BASE = 'https://data.mendeley.com/public-files/datasets/3hx58k232n/files/{fid}/file_downloaded'

# We'll try sequential download with per-chunk progress
for fname, info in FILES.items():
    dst = os.path.join(DATA_DIR, fname)
    
    # Skip if exists and correct size
    if os.path.exists(dst) and os.path.getsize(dst) == info['size']:
        print(f'[✓] {fname}: already complete ({info["size"]/1e6:.0f}MB)')
        continue
    
    # Remove partial
    if os.path.exists(dst):
        os.remove(dst)
    
    url = BASE.format(fid=info['id'])
    print(f'\n[DL] {fname} ({info["size"]/1e6:.0f}MB)')
    
    # Use urllib with proper timeout and progress
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'
    })
    
    success = False
    for attempt in range(3):
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                content_len = int(resp.headers.get('Content-Length', 0))
                print(f'  Content-Length: {content_len/1e6:.0f}MB')
                
                with open(dst, 'wb') as f:
                    while True:
                        chunk = resp.read(4*1024*1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        
                        # Progress every 30s
                        elapsed = time.time() - t0
                        if elapsed > 30:
                            dl = os.path.getsize(dst)
                            speed = dl/1e6/elapsed if elapsed > 0 else 0
                            eta = ((info['size'] - dl)/1e6)/speed if speed > 0 else 0
                            print(f'  {dl/1e6:.0f}/{info["size"]/1e6:.0f}MB @ {speed:.1f}MB/s, ETA {eta:.0f}s', flush=True)
                            t0 = time.time()
                
                actual_size = os.path.getsize(dst)
                if actual_size == info['size']:
                    print(f'[✓] {fname}: complete ({actual_size/1e6:.0f}MB)')
                    success = True
                    break
                else:
                    print(f'[!] Size mismatch: got {actual_size}, expected {info["size"]}')
                    if os.path.exists(dst):
                        os.remove(dst)
        except Exception as e:
            print(f'  Attempt {attempt+1}/3 failed: {e}')
            if os.path.exists(dst):
                os.remove(dst)
            time.sleep(5)
    
    if not success:
        print(f'[✗] {fname}: download failed after 3 attempts')
        # Write error to log
        with open(os.path.join(DATA_DIR, 'dl_failures.txt'), 'a') as f:
            f.write(f'{fname}: Failed after 3 attempts\n')

print(f'\n{"="*50}')
print('Results:')
eds = sorted([f for f in os.listdir(DATA_DIR) if f.endswith('.edf')])
total = 0
for f in eds:
    sz = os.path.getsize(os.path.join(DATA_DIR, f))
    total += sz
    mark = '✓' if sz > 0 else '✗'
    print(f'  {mark} {f}: {sz/1e6:.0f}MB')
print(f'Total: {total/1e9:.2f}GB / {len(eds)} files')
