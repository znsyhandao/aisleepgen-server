#!/usr/bin/env python3
"""
从网络上获取真实高质量白噪音音频（CC0/免版权）
下载的是真正录音级的雨声、海浪、森林
"""
import sys, os, urllib.request, json, time
sys.stdout.reconfigure(encoding='utf-8')

OUTDIR = 'miniprogram/assets/sounds'
os.makedirs(OUTDIR, exist_ok=True)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def download(url, filepath, max_retry=3):
    """下载文件，有重试"""
    for attempt in range(max_retry):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            resp = urllib.request.urlopen(req, timeout=30)
            data = resp.read()
            if len(data) > 50000:  # 至少 50KB
                with open(filepath, 'wb') as f:
                    f.write(data)
                return True, len(data)
            else:
                return False, f'文件太小: {len(data)}B'
        except Exception as e:
            if attempt < max_retry - 1:
                time.sleep(2)
                continue
            return False, str(e)[:80]

# 已知可靠的 CC0 白噪音源
# 来源: freesound.org CC0 采样, 已知sound IDs
SOUNDS = [
    # 1. 雨声 - "Rain on Window" by klankbeeld (CC0)
    ('rain', [
        'https://cdn.freesound.org/previews/604/604026_12558617-hq.mp3',
        'https://cdn.freesound.org/previews/609/609142_13079460-hq.mp3',
        'https://cdn.freesound.org/previews/470/470583_10061122-hq.mp3',
    ]),
    # 2. 海浪声
    ('ocean', [
        'https://cdn.freesound.org/previews/431/431923_7804924-hq.mp3',
        'https://cdn.freesound.org/previews/407/407420_5121236-hq.mp3',
        'https://cdn.freesound.org/previews/479/479838_9547300-hq.mp3',
    ]),
    # 3. 森林/自然
    ('forest', [
        'https://cdn.freesound.org/previews/480/480547_5121236-hq.mp3',
        'https://cdn.freesound.org/previews/425/425782_8076671-hq.mp3',
        'https://cdn.freesound.org/previews/472/472257_10230689-hq.mp3',
    ]),
]

for name, urls in SOUNDS:
    filepath = os.path.join(OUTDIR, name + '.mp3')
    # 删除旧的
    for ext in ['.mp3', '.wav']:
        old = os.path.join(OUTDIR, name + ext)
        if os.path.exists(old):
            os.remove(old)
    
    print(f'下载: {name}')
    success = False
    for i, url in enumerate(urls):
        ok, result = download(url, filepath)
        if ok:
            print(f'  OK: {result//1024}KB (来源{i+1})')
            success = True
            break
        else:
            print(f'  来源{i+1} 失败: {result}')
    
    if not success:
        print(f'  ALL FAILED')
        # 如果全失败，用 python 生成更好的白噪音（比 ffmpeg 好一点，但最后还是换真录音）
        import numpy as np
        from scipy.io import wavfile
        sr = 44100
        dur = 30
        t = np.linspace(0, dur, sr*dur, False)
        # 粉红噪音
        white = np.random.normal(0, 1, len(t))
        # 累积 -> 布朗, 再滤波
        brown = np.cumsum(white)
        # 雨声用多频段噪声
        noise = np.zeros_like(t)
        for freq in [200, 500, 1000, 2000, 4000]:
            filtered = np.sin(2*np.pi*freq*t) * white * 0.2
            noise += filtered
        noise = noise / np.max(np.abs(noise)) * 0.5
        wavfile.write(filepath.replace('.mp3', '.wav'), sr, np.int16(noise * 16384))
        print(f'  FAILBACK: 合成 {name}.wav')

print(f'\n完成! 文件:')
for f in sorted(os.listdir(OUTDIR)):
    sz = os.path.getsize(os.path.join(OUTDIR, f))
    print(f'  {f}: {sz//1024}KB')
