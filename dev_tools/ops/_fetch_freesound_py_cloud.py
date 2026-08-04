#!/usr/bin/env python3
"""从 Freesound 抓取真实白噪音 - 用 requests 模拟浏览器"""
import sys, os, re, requests, time
sys.stdout.reconfigure(encoding='utf-8')
os.chdir('/opt/aisleepgen')

sess = requests.Session()
sess.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml',
})

# 已知 CC0 sound IDs
SOUNDS = {
    'rain': ['604026', '609142', '623599'],
    'ocean': ['407420', '479838', '409022'],
    'forest': ['425782', '480547', '636238'],
}

def get_preview_url(sound_id):
    """从 sound 页面提取 preview URL"""
    url = f'https://freesound.org/people/none/sounds/{sound_id}/'
    try:
        r = sess.get(url, timeout=15)
        r.raise_for_status()
        html = r.text
        
        # 找 preview URL
        # <meta property="og:audio" content="https://cdn.freesound.org/previews/...">
        m = re.search(r'<meta\s+property="og:audio"\s+content="([^"]+)"', html)
        if m:
            return m.group(1)
        
        # 或者 data-preview-url
        m = re.search(r'data-preview-url=["\']([^"\']+)["\']', html)
        if m:
            return m.group(1)
        
        # 或者 JSON-LD
        m = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', html)
        if m:
            return m.group(1).replace('\\/', '/')
        
        return None
    except Exception as e:
        print(f'  Error: {e}')
        return None

for name, ids in SOUNDS.items():
    out = f'{name}.mp3'
    if os.path.exists(out) and os.path.getsize(out) > 100000:
        print(f'{name}: 已存在 ({os.path.getsize(out)//1024}KB)')
        continue
    
    print(f'\n{name}: 尝试 {len(ids)} 个 sources')
    success = False
    for sid in ids:
        print(f'  sound {sid}...')
        preview = get_preview_url(sid)
        if preview:
            print(f'  preview: {preview}')
            try:
                rr = sess.get(preview, timeout=30)
                if len(rr.content) > 50000:
                    with open(out, 'wb') as f:
                        f.write(rr.content)
                    print(f'  OK: {len(rr.content)//1024}KB')
                    success = True
                    break
                else:
                    print(f'  too small: {len(rr.content)}B')
            except Exception as e:
                print(f'  download fail: {e}')
        else:
            print(f'  no preview URL found')
    
    if not success:
        # fallback to ffmpeg
        print(f'  ALL FAILED, using ffmpeg fallback')

print(f'\n结果:')
for f in ['rain.mp3', 'ocean.mp3', 'forest.mp3']:
    if os.path.exists(f) and os.path.getsize(f) > 1000:
        print(f'  {f}: {os.path.getsize(f)//1024}KB')
    else:
        print(f'  {f}: MISSING')
