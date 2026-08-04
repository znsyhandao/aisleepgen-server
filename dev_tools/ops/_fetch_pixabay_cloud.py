#!/usr/bin/env python3
"""在腾讯云上爬pixabay获取真实白噪音"""
import sys, os, json, urllib.request, re
sys.stdout.reconfigure(encoding='utf-8')
os.chdir('/opt/aisleepgen')

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# 直接从 Pixabay 搜索 API 获取
# Pixabay 音乐有公开的下载 URL 模式
# 已知可用的白噪音音乐ID（pixabay.com/music）
# 这些ID从网页手动提取

# 从 Pixabay 的 RSS/API 获取
API = 'https://pixabay.com/api/v1/music/?q={}&per_page=5'

sounds = {
    'rain': 'nature+sounds+rain+ambient',
    'ocean': 'ocean+waves+sea+ambient',
    'forest': 'forest+nature+birds+ambient',
}

for name, query in sounds.items():
    url = API.format(query.replace(' ', '+'))
    print(f'{name}: 搜索 {url[:60]}...')
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        
        hits = data.get('hits', data.get('results', []))
        if not hits and isinstance(data, list):
            hits = data[:5]
        
        print(f'  hits: {len(hits)}')
        for h in hits[:3]:
            audio_url = h.get('audiourl', h.get('audio_url', h.get('url', '')))
            tags = h.get('tags', '')
            dur = h.get('duration', 0)
            print(f'    {audio_url[:80]}... [{tags}] dur={dur}s')
            
            if audio_url and dur > 30:
                out = f'{name}.mp3'
                areq = urllib.request.Request(audio_url, headers=HEADERS)
                aresp = urllib.request.urlopen(areq, timeout=60)
                adata = aresp.read()
                if len(adata) > 50000:
                    with open(out, 'wb') as f:
                        f.write(adata)
                    print(f'    OK: {out} ({len(adata)//1024}KB)')
                    break
                else:
                    print(f'    too small: {len(adata)}B')
    except Exception as e:
        print(f'  FAIL: {str(e)[:80]}')

print('\nResults:')
for f in ['rain.mp3', 'ocean.mp3', 'forest.mp3']:
    if os.path.exists(f) and os.path.getsize(f) > 1000:
        print(f'  {f}: {os.path.getsize(f)//1024}KB')
    else:
        print(f'  {f}: MISSING')
