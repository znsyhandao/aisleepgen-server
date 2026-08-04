import sys, urllib.request, os
sys.stdout.reconfigure(encoding='utf-8')

outdir = 'miniprogram/assets/sounds'
os.makedirs(outdir, exist_ok=True)

# Freesound CC0 真实的雨声/海浪片段 preview 链接
sounds = [
    ('rain', 'https://cdn.freesound.org/previews/470/470583_10061122-lq.mp3'),
    ('ocean', 'https://cdn.freesound.org/previews/456/456032_4338374-lq.mp3'),
    ('forest', 'https://cdn.freesound.org/previews/500/500067_6022036-lq.mp3'),
    ('brown', 'https://cdn.freesound.org/previews/476/476132_10637355-lq.mp3'),
]

for name, url in sounds:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=15)
        data = resp.read()
        if len(data) > 10000:
            # 微信小程序支持 mp3
            filepath = os.path.join(outdir, name + '.mp3')
            # 删除旧的 wav
            old_wav = os.path.join(outdir, name + '.wav')
            if os.path.exists(old_wav):
                os.remove(old_wav)
            with open(filepath, 'wb') as f:
                f.write(data)
            print(f'OK: {name}.mp3 ({len(data)//1024}KB)')
        else:
            print(f'TOO_SMALL: {url} ({len(data)}B)')
    except Exception as e:
        print(f'FAIL: {name} -> {str(e)[:60]}')

print('Done')
