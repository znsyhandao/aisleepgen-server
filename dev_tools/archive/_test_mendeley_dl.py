# -*- coding: utf-8 -*-
"""Quick connectivity test"""
import requests, time

url = 'https://data.mendeley.com/public-files/datasets/3hx58k232n/files/fbe80656-82c3-4ea0-b9e9-9896e34b3125/file_downloaded'
t0 = time.time()
try:
    r = requests.get(url, stream=True, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    status = r.status_code
    ct = r.headers.get('content-type', '?')
    cl = r.headers.get('content-length', '?')
    print(f'Status: {status}')
    print(f'Content-Type: {ct}  Content-Length: {cl}')
    if status == 200:
        chunk = next(r.iter_content(1024))
        print(f'First chunk: {len(chunk)} bytes after {time.time()-t0:.1f}s')
except Exception as e:
    print(f'Error: {e}')
