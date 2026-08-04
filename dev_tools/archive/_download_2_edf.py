# -*- coding: utf-8 -*-
"""Download 2 EDF files using requests with streaming"""
import requests, json, os, time

TARGET_NORMAL = 1
TARGET_INSOMNIA = 10
DATA_DIR = r'D:\AISleepGen_Optimized\data\edf\mendeley_insomnia'
os.makedirs(DATA_DIR, exist_ok=True)

# Clean partial file
for f in os.listdir(DATA_DIR):
    if f.endswith('.edf') and os.path.getsize(os.path.join(DATA_DIR, f)) == 0:
        os.remove(os.path.join(DATA_DIR, f))

url = 'https://data.mendeley.com/public-api/datasets/3hx58k232n'
headers = {'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
resp = requests.get(url, headers=headers, timeout=15)
data = resp.json()

dl_list = []
for f in data.get('files', []):
    fname = f['filename']
    if not fname.lower().endswith('.edf'):
        continue
    cd = f['content_details']
    n1 = f'Normal_Subject_{TARGET_NORMAL:02d}'
    n2 = f'Psycophysiological_Insomnia_{TARGET_INSOMNIA:02d}'
    if n1 in fname or n2 in fname:
        dl_list.append((fname, cd['download_url'], cd['size']))

for fname, dl_url, size in dl_list:
    dst = os.path.join(DATA_DIR, fname)
    if os.path.exists(dst) and os.path.getsize(dst) == size:
        print(f'[SKIP] {fname} ({size/1e6:.0f}MB)')
        continue
    print(f'[DL] {fname} ({size/1e6:.0f}MB)...')
    t0 = time.time()
    dreq = requests.get(dl_url, stream=True, headers={'User-Agent': 'Mozilla/5.0'}, timeout=600)
    with open(dst, 'wb') as f:
        for chunk in dreq.iter_content(chunk_size=8*1024*1024):
            if chunk:
                f.write(chunk)
                sz = os.path.getsize(dst)
                speed = sz / 1e6 / (time.time() - t0 + 0.001)
                print(f'  {sz/1e6:.0f}MB ({speed:.0f}MB/s)', flush=True)
    elapsed = time.time() - t0
    final_speed = size/1e6/elapsed
    print(f'[OK] {fname}: {elapsed:.0f}s, {final_speed:.1f}MB/s')

print(f'\nDone. Files:')
for f in os.listdir(DATA_DIR):
    if f.endswith('.edf'):
        print(f'  {f}: {os.path.getsize(os.path.join(DATA_DIR,f))/1e6:.0f}MB')
