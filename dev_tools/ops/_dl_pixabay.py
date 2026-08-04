import sys, urllib.request, json, os

sys.stdout.reconfigure(encoding='utf-8')

outdir = 'miniprogram/assets/sounds'
os.makedirs(outdir, exist_ok=True)

# Pixabay Sound API - 免费免版权音效
pixabay_key = 'KXCHAKYJ2362645e5a2fd8f'
queries = [
    ('rain', 'rain+ambient+soft'),
    ('ocean', 'ocean+waves+sea'),
    ('forest', 'forest+nature+ambient'),
]

for fname, q in queries:
    url = f'https://pixabay.com/api/sounds/?key={pixabay_key}&q={q}&per_page=3'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        hits = data.get('hits', [])
        if hits:
            # 取第一个
            s = hits[0]
            dl_url = s.get('url', '')
            tags = s.get('tags', '?')
            print(f'{fname}: found {tags} - {dl_url[:80]}...')
            if dl_url:
                dreq = urllib.request.Request(dl_url, headers={'User-Agent': 'Mozilla/5.0'})
                dresp = urllib.request.urlopen(dreq, timeout=30)
                adata = dresp.read()
                if len(adata) > 10000:
                    old_wav = os.path.join(outdir, fname + '.wav')
                    if os.path.exists(old_wav):
                        os.remove(old_wav)
                    fp = os.path.join(outdir, fname + '.mp3')
                    with open(fp, 'wb') as f:
                        f.write(adata)
                    print(f'  OK: {fname}.mp3 ({len(adata)//1024}KB)')
        else:
            print(f'{fname}: no results')
    except Exception as e:
        print(f'{fname}: {str(e)[:80]}')
