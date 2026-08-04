# -*- coding: utf-8 -*-
"""Download 1 EDF using raw urllib (which worked for XLSX)"""
import os, time, urllib.request

DATA_DIR = r'D:\AISleepGen_Optimized\data\edf\mendeley_insomnia'
os.makedirs(DATA_DIR, exist_ok=True)

# Clean zeros
for f in os.listdir(DATA_DIR):
    p = os.path.join(DATA_DIR, f)
    if f.endswith('.edf') and os.path.getsize(p) == 0:
        os.remove(p)
    # Also .tmp
    if f.endswith('.part'):
        os.remove(p)

# Normal_Subject_01 download URL (from API)
url = 'https://data.mendeley.com/public-files/datasets/3hx58k232n/files/1fc96698-86d7-4f8e-be63-346a15ceb20f/file_downloaded'
dst = os.path.join(DATA_DIR, 'Normal_Subject_01.edf')

print(f'Downloading Normal_Subject_01.edf...')
t0 = time.time()
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'})

# Use urllib with blocking read (not stream) - worked for XLSX
with urllib.request.urlopen(req, timeout=600) as resp:
    size = int(resp.headers.get('Content-Length', 0))
    print(f'Content-Length: {size/1e6:.0f}MB')
    with open(dst, 'wb') as f:
        while True:
            chunk = resp.read(4*1024*1024)
            if not chunk:
                break
            f.write(chunk)
            elapsed = time.time() - t0
            dl = os.path.getsize(dst)
            speed = dl/1e6/elapsed if elapsed > 0 else 0
            print(f'  {dl/1e6:.0f}MB at {speed:.1f}MB/s ({elapsed:.0f}s)', flush=True)

elapsed = time.time() - t0
fsize = os.path.getsize(dst)
print(f'[OK] {fsize/1e6:.0f}MB in {elapsed:.0f}s ({fsize/1e6/elapsed:.1f}MB/s)')
