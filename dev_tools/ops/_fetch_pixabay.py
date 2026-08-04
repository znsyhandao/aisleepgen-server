#!/usr/bin/env python3
"""
Pixabay Music - 从网页抓取白噪音下载链接
"""
import sys, os, json, urllib.request, re, time
sys.stdout.reconfigure(encoding='utf-8')

OUTDIR = 'miniprogram/assets/sounds'
os.makedirs(OUTDIR, exist_ok=True)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# Pixabay Music 搜索结果，从 HTML 解析下载链接
SEARCH_URLS = {
    'rain': 'https://pixabay.com/music/search/rain/?order=ec',
    'ocean': 'https://pixabay.com/music/search/ocean/',
    'forest': 'https://pixabay.com/music/search/forest/',
}

# Pixabay 音频 JSON API (内部)
API_URL = 'https://pixabay.com/api/v1/music/'

def fetch_page(url):
    req = urllib.request.Request(url, headers=HEADERS)
    resp = urllib.request.urlopen(req, timeout=15)
    return resp.read().decode('utf-8')

def extract_audio_urls(html, max_items=3):
    """从HTML中提取音频URL"""
    # Pixabay 音乐页的音频元素格式: data-audio="url" 或 mp3 下载链接
    urls = []
    
    # 匹配 data-audio 属性
    for m in re.finditer(r'data-audio="([^"]+\.mp3[^"]*)"', html):
        url = m.group(1)
        if url not in urls:
            urls.append(url)
    
    # 匹配 audio 标签 source
    for m in re.finditer(r'<source[^>]+src="([^"]+\.mp3[^"]*)"', html):
        url = m.group(1)
        if url not in urls:
            urls.append(url)
    
    # 匹配 JSON 中的 download 链接
    for m in re.finditer(r'"download"[^:]*:\s*"([^"]+\.mp3[^"]*)"', html):
        url = m.group(1).replace('\\/', '/')
        if url not in urls:
            urls.append(url)
    
    return urls[:max_items]

def download(url, filepath):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=30)
        data = resp.read()
        if len(data) > 50000:
            with open(filepath, 'wb') as f:
                f.write(data)
            return True, len(data)
        return False, f'small: {len(data)}B'
    except Exception as e:
        return False, str(e)[:60]

for name, search_url in SEARCH_URLS.items():
    filepath = os.path.join(OUTDIR, name + '.mp3')
    for ext in ['.mp3', '.wav']:
        old = os.path.join(OUTDIR, name + ext)
        if os.path.exists(old):
            os.remove(old)
    
    print(f'\n{name}: 搜索 {search_url}')
    try:
        html = fetch_page(search_url)
        urls = extract_audio_urls(html)
        print(f'  找到 {len(urls)} 个音频')
        
        success = False
        for i, url in enumerate(urls):
            print(f'  下载 {i+1}: {url[:80]}...')
            ok, result = download(url, filepath)
            if ok:
                print(f'    OK: {result//1024}KB')
                success = True
                break
            else:
                print(f'    FAIL: {result}')
        
        if not success:
            print(f'  全部失败，查看 HTML 片段:')
            print(f'  {html[:500]}')
    
    except Exception as e:
        print(f'  搜索失败: {e}')

print(f'\n完成')
for f in sorted(os.listdir(OUTDIR)):
    sz = os.path.getsize(os.path.join(OUTDIR, f))
    print(f'  {f}: {sz//1024}KB')
