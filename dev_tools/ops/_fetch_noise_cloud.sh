#!/bin/bash
# 从腾讯云下载真正的白噪音（海外CDN可达）
# 使用 freesound 的 API 搜索 CC0 音频

# 先用 wget 试试 freesound API 搜索
echo "=== 搜索雨声 ==="
curl -s "https://freesound.org/apiv2/search/text/?query=rain+ambient+loop&filter=license:cc-zero&fields=id,name,previews&page_size=3" \
  > /opt/aisleepgen/freesound_search.json 2>&1
echo "Search result:"
python3 -c "import json; d=json.load(open('/opt/aisleepgen/freesound_search.json')); [print(r['id'], r['name'], list(r.get('previews',{}).values())[0] if r.get('previews') else 'no preview') for r in d.get('results',[])]" 2>&1 || echo "API fail"

# 如果有结果，下载第一个
if [ -f /opt/aisleepgen/freesound_search.json ]; then
  python3 -c "
import json, urllib.request
d = json.load(open('/opt/aisleepgen/freesound_search.json'))
results = d.get('results', [])
if results:
    for r in results:
        previews = r.get('previews', {})
        for k in ['preview-hq-mp3', 'preview-lq-mp3', 'preview-hq-ogg', 'preview-lq-ogg']:
            url = previews.get(k)
            if url:
                fname = r['name'].replace(' ','_')[:30] + '.mp3'
                print(f'Downloading {r[\"id\"]}: {url}')
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    resp = urllib.request.urlopen(req, timeout=30)
                    data = resp.read()
                    with open(f'/opt/aisleepgen/sound_{r[\"id\"]}.mp3', 'wb') as f:
                        f.write(data)
                    print(f'  OK: {len(data)//1024}KB')
                except Exception as e:
                    print(f'  FAIL: {e}')
                break
else:
    print('No results')
" 2>&1
fi

ls -la /opt/aisleepgen/sound_*.mp3 2>&1
