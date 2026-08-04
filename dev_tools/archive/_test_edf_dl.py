# -*- coding: utf-8 -*-
"""Download Normal_01 + Insomnia_10 for topology verification"""
import os, time, requests, json

DATA_DIR = r'D:\AISleepGen_Optimized\data\edf\mendeley_insomnia'
os.makedirs(DATA_DIR, exist_ok=True)

# Clean zero-length partials
for f in os.listdir(DATA_DIR):
    p = os.path.join(DATA_DIR, f)
    if f.endswith('.edf') and os.path.getsize(p) == 0:
        os.remove(p)

# Get file listing
BASE = 'https://data.mendeley.com/public-api/datasets/3hx58k232n'
resp = requests.get(BASE, headers={'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'}, timeout=15)
data = resp.json()

# Find the 2 files by matching filename
targets = ['Normal_Subject_01', 'Psycophysiological_Insomnia_10']
downloads = []
for f in data.get('files', []):
    fname = f['filename']
    if not fname.lower().endswith('.edf'):
        continue
    for t in targets:
        if t in fname:
            cd = f['content_details']
            dl_url = cd['download_url'].replace('/file_downloaded', '/download')
            downloads.append((fname, dl_url, cd['size']))
            print(f'Found: {fname} ({cd["size"]/1e6:.0f}MB)')

print(f'\nDownloading {len(downloads)} files...')

for fname, dl_url, size in downloads:
    dst = os.path.join(DATA_DIR, fname)
    if os.path.exists(dst) and os.path.getsize(dst) == size:
        print(f'[SKIP] {fname} already complete')
        continue

    print(f'[DL] {fname} ({size/1e6:.0f}MB) from {dl_url}')
    t0 = time.time()
    dreq = requests.get(dl_url, stream=True, headers={'User-Agent': 'Mozilla/5.0'}, timeout=600)
    dl_size = 0
    with open(dst, 'wb') as f:
        for chunk in dreq.iter_content(chunk_size=4*1024*1024):
            if chunk:
                f.write(chunk)
                dl_size += len(chunk)
                if time.time() - t0 > 5:
                    speed = dl_size/1e6/(time.time()-t0)
                    print(f'  {dl_size/1e6:.0f}MB ({speed:.0f}MB/s)', flush=True)
    elapsed = time.time() - t0
    final_speed = os.path.getsize(dst)/1e6/elapsed
    print(f'[OK] {fname}: {elapsed:.0f}s, {final_speed:.1f}MB/s')

# Quick triage
print('\nFiles ready:')
for f in os.listdir(DATA_DIR):
    if f.endswith('.edf'):
        print(f'  {f}: {os.path.getsize(os.path.join(DATA_DIR,f))/1e6:.0f}MB')
