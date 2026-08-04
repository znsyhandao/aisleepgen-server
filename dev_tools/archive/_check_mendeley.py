# Check Mendeley dataset file listing
import urllib.request, json, re

url = 'https://data.mendeley.com/public-api/datasets/3hx58k232n/files'
try:
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    print(f'Files: {len(data)}')
    for d in data[:10]:
        print(json.dumps(d, indent=2)[:300])
        print('---')
except Exception as e:
    print(f'API error: {e}')
    # Fallback: HTML
    url2 = 'https://data.mendeley.com/datasets/3hx58k232n/3'
    req2 = urllib.request.Request(url2)
    with urllib.request.urlopen(req2, timeout=15) as resp:
        html = resp.read().decode('utf-8', errors='replace')
    # Find any download links
    pattern = r'https?://[^\s<>]+\.(?:zip|tar|gz|rar)'
    links = re.findall(pattern, html)
    print(f'Download links found: {len(links)}')
    for l in links[:5]:
        print(f'  {l}')
