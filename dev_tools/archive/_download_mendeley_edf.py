# -*- coding: utf-8 -*-
"""
_mendeley_edf_download.py — 批量下载 Mendeley 失眠数据集 EDF 文件

突变动力学审核：
  1. 只下载 24 个标注过 Diagnostic.Insomnia 的 subject EDF（排除 PSD/其他文件）
  2. 每个 350MB，总计 ~8GB，耗时较长（WIFI 约 15-30 分钟）
  3. 断点续传：已存在的文件跳过
  4. 下载到 D:\AISleepGen_Optimized\data\edf\mendeley_insomnia
  5. 完成后自动运行 triage 诊断
"""
import urllib.request, json, os, time

DATA_DIR = r'D:\AISleepGen_Optimized\data\edf\mendeley_insomnia'
os.makedirs(DATA_DIR, exist_ok=True)

# Fetch dataset file listing
url = 'https://data.mendeley.com/public-api/datasets/3hx58k232n'
req = urllib.request.Request(url, headers={
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'
})
with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read())

# Filter EDF files (exclude .xlsx, .zip, .pdf)
edf_files = []
for f in data.get('files', []):
    cd = f.get('content_details', {})
    fname = f['filename']
    if not fname.lower().endswith('.edf'):
        continue
    dl_url = cd.get('download_url', '')
    size = cd.get('size', 0)
    edf_files.append((fname, dl_url, size))

print(f'EDF files to download: {len(edf_files)}')
total_gb = sum(s for _, _, s in edf_files) / 1e9
print(f'Total size: {total_gb:.1f} GB')
print()

downloaded = 0
skipped = 0
errors = 0

for fname, dl_url, size in edf_files:
    dst = os.path.join(DATA_DIR, fname)
    if os.path.exists(dst) and os.path.getsize(dst) == size:
        print(f'[SKIP] {fname} ({size/1e6:.0f}MB)')
        skipped += 1
        continue
    
    print(f'[DL] {fname} ({size/1e6:.0f}MB)...', end=' ', flush=True)
    t0 = time.time()
    try:
        dreq = urllib.request.Request(dl_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'
        })
        with urllib.request.urlopen(dreq, timeout=600) as resp:
            with open(dst, 'wb') as f:
                while True:
                    chunk = resp.read(8192 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
        elapsed = time.time() - t0
        speed = size / 1e6 / elapsed
        print(f'OK ({elapsed:.0f}s, {speed:.0f}MB/s)')
        downloaded += 1
    except Exception as e:
        print(f'FAIL: {e}')
        errors += 1
        # Clean partial file
        if os.path.exists(dst):
            os.remove(dst)
    
    # Pause between downloads to avoid rate limiting
    time.sleep(0.5)

print(f'\nDone: {downloaded} downloaded, {skipped} skipped, {errors} errors')
print(f'EDF files in dir: {len([f for f in os.listdir(DATA_DIR) if f.endswith(".edf")])}')

# Run triage if we have files
if downloaded + skipped > 0:
    print('\n=== Running dataset triage ===')
    sys.path.insert(0, r'D:\AISleepGen_Optimized')
    from triage_dataset import diagnose
    diagnose(DATA_DIR)
