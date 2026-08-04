import sys, urllib.request, os, json
sys.stdout.reconfigure(encoding='utf-8')

outdir = 'miniprogram/assets/sounds'
os.makedirs(outdir, exist_ok=True)

# Freesound 的真实音效 - 用已知 sound IDs(CC0)
# 这些 ID 来自 freesound 社区常用的 CC0 音效
sounds = [
    # 真实的雨声
    ('rain', 'https://freesound.org/data/previews/415/415320_5121236-lq.mp3'),
    # 备选雨声  
    ('rain_alt', 'https://freesound.org/data/previews/609/609142_13079460-lq.mp3'),
    # 海浪声
    ('ocean', 'https://freesound.org/data/previews/407/407420_5121236-lq.mp3'),
    # 森林/溪流
    ('forest', 'https://freesound.org/data/previews/425/425782_8076671-lq.mp3'),
    # 夜间虫鸣
    ('night', 'https://freesound.org/data/previews/480/480547_5121236-lq.mp3'),
]

for name, url in sounds:
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'audio/*',
        })
        resp = urllib.request.urlopen(req, timeout=15)
        data = resp.read()
        if len(data) > 10000:
            filepath = os.path.join(outdir, name + '.mp3')
            old_wav = os.path.join(outdir, name + '.wav')
            if os.path.exists(old_wav):
                os.remove(old_wav)
            with open(filepath, 'wb') as f:
                f.write(data)
            print(f'OK: {name}.mp3 ({len(data)//1024}KB)')
        else:
            print(f'TOO_SMALL: {name} ({len(data)}B)')
    except Exception as e:
        print(f'FAIL: {name} -> {str(e)[:80]}')

print('Done')
