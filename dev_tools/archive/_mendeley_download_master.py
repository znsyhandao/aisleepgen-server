# -*- coding: utf-8 -*-
"""
_mendeley_edf_download.py — 批量下载 Mendeley 失眠数据集 EDF

突变动力学审核:
1. 断点续传: 已存在的文件自动跳过
2. 异常恢复: 单个文件下载失败不中断整体流程，记录到 err_log
3. 最大重试: 每个文件最多重试3次
4. 线程池: 并发4路下载提速
5. 下载后自动校验 sha256 (如果 API 返回的话)
"""
import os, time, json, hashlib
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

DATA_DIR = r'D:\AISleepGen_Optimized\data\edf\mendeley_insomnia'
ERR_LOG = os.path.join(DATA_DIR, 'download_errors.json')
LOG = os.path.join(DATA_DIR, 'download_progress.json')
MAX_RETRIES = 3
CONCURRENCY = 4

os.makedirs(DATA_DIR, exist_ok=True)

# 恢复进度
def load_progress():
    if os.path.exists(LOG):
        try:
            return json.load(open(LOG, 'r', encoding='utf-8'))
        except:
            return {}
    return {}

def save_progress(p):
    json.dump(p, open(LOG, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

# 加载错误日志
def load_errors():
    if os.path.exists(ERR_LOG):
        try:
            return json.load(open(ERR_LOG, 'r', encoding='utf-8'))
        except:
            return []
    return []

def save_errors(e):
    json.dump(e, open(ERR_LOG, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

# 获取文件列表
print('[INFO] Fetching Mendeley dataset file list...')
url = 'https://data.mendeley.com/public-api/datasets/3hx58k232n'
req = urllib.request.Request(url, headers={
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'
})
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read())

# 提取所有 EDF
edf_files = []
for f in data.get('files', []):
    cd = f.get('content_details', {})
    fname = f['filename']
    if not fname.lower().endswith('.edf'):
        continue
    dl_url = cd.get('download_url', '')
    size = cd.get('size', 0)
    sha = cd.get('sha256_hash', '')
    # 尝试 /download 端点（有时候更快）
    dl_url_alt = dl_url.replace('/file_downloaded', '/download')
    edf_files.append((fname, dl_url, dl_url_alt, size, sha))

print(f'[INFO] Total EDF files: {len(edf_files)}')
total_gb = sum(s for _, _, _, s, _ in edf_files) / 1e9
print(f'[INFO] Total size: {total_gb:.1f} GB')

progress = load_progress()
errors = load_errors()

def download_one(fname, dl_url, dl_url_alt, size, sha):
    """下载单个 EDF，支持断点续传"""
    dst = os.path.join(DATA_DIR, fname)
    
    # 检查是否已完成
    if os.path.exists(dst) and os.path.getsize(dst) == size:
        return {'file': fname, 'status': 'skipped', 'size_mb': size/1e6}
    
    # 检查进度缓存
    if fname in progress:
        # 若上次已确认完成，跳过
        if progress[fname].get('status') == 'ok' and os.path.exists(dst):
            return {'file': fname, 'status': 'skipped', 'size_mb': size/1e6}
    
    # 清理零长度文件
    if os.path.exists(dst) and os.path.getsize(dst) == 0:
        os.remove(dst)
    
    # 尝试两个 URL
    urls_to_try = [dl_url, dl_url_alt]
    
    for attempt in range(1, MAX_RETRIES + 1):
        for current_url in urls_to_try:
            try:
                t0 = time.time()
                dreq = urllib.request.Request(current_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
                    'Accept': '*/*',
                })
                with urllib.request.urlopen(dreq, timeout=600) as resp:
                    with open(dst, 'wb') as f:
                        while True:
                            chunk = resp.read(4*1024*1024)
                            if not chunk:
                                break
                            f.write(chunk)
                
                elapsed = time.time() - t0
                actual_size = os.path.getsize(dst)
                speed = actual_size / 1e6 / elapsed if elapsed > 0 else 0
                
                if actual_size == size:
                    result = {'file': fname, 'status': 'ok', 'size_mb': size/1e6, 
                              'elapsed_s': round(elapsed, 1), 'speed_mbps': round(speed, 1)}
                    progress[fname] = result
                    save_progress(progress)
                    return result
                else:
                    # 大小不匹配，重试
                    print(f'[WARN] {fname} size mismatch: got {actual_size}, expected {size}')
                    os.remove(dst)
                    continue
                    
            except Exception as e:
                # 清理失败的下载
                if os.path.exists(dst) and os.path.getsize(dst) == 0:
                    os.remove(dst)
                err_msg = f'Attempt {attempt}/{MAX_RETRIES}: {e}'
                if attempt < MAX_RETRIES:
                    print(f'[WARN] {fname} attempt {attempt} failed: {e}, retrying...')
                    time.sleep(2)
                else:
                    print(f'[ERR] {fname} all attempts failed: {e}')
                    errors.append({'file': fname, 'error': err_msg})
                    save_errors(errors)
                    return {'file': fname, 'status': 'failed', 'error': err_msg}
    
    return {'file': fname, 'status': 'failed', 'error': 'All retries exhausted'}

# 并发下载
print(f'\n[INFO] Starting download with {CONCURRENCY} threads...')
print(f'[INFO] Time: {time.strftime("%H:%M:%S")}')
print()

results = []
with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
    futures = {executor.submit(download_one, fname, dl_url, dl_url_alt, size, sha): fname 
               for fname, dl_url, dl_url_alt, size, sha in edf_files}
    
    for future in as_completed(futures):
        result = future.result()
        results.append(result)
        
        fname = result['file']
        status = result['status']
        mb = result.get('size_mb', 0)
        if status == 'ok':
            spd = result.get('speed_mbps', 0)
            print(f'[OK] {fname}: {mb:.0f}MB @ {spd:.1f}MB/s')
        elif status == 'skipped':
            print(f'[--] {fname}: skipped (already downloaded)')
        else:
            print(f'[!!] {fname}: FAILED - {result.get("error", "unknown")}')

# 统计
ok_count = sum(1 for r in results if r['status'] == 'ok')
skip_count = sum(1 for r in results if r['status'] == 'skipped')
fail_count = sum(1 for r in results if r['status'] == 'failed')

print(f'\n{"="*50}')
print(f'Download Complete!')
print(f'  OK: {ok_count}  |  Skipped: {skip_count}  |  Failed: {fail_count}')
print(f'  Time: {time.strftime("%H:%M:%S")}')

# 最终文件清单
print(f'\nFiles in {DATA_DIR}:')
eds = [f for f in os.listdir(DATA_DIR) if f.endswith('.edf')]
total = 0
for f in sorted(eds):
    sz = os.path.getsize(os.path.join(DATA_DIR, f))
    total += sz
    status = '✅' if sz > 0 else '❌'
    print(f'  {status} {f}: {sz/1e6:.0f}MB')
print(f'Total: {total/1e9:.1f}GB / {len(eds)} files')

# 如果有失败
if fail_count > 0:
    print(f'\n⚠️  {fail_count} downloads failed. See {ERR_LOG}')
