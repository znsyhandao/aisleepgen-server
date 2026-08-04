import urllib.request, json, sys

def test():
    API = 'http://82.156.208.245:8090'

    # 1. Health
    r = urllib.request.Request(f'{API}/health')
    resp = json.loads(urllib.request.urlopen(r, timeout=5).read())
    print('Health:', resp.get('status'))

    # 2. Pricing
    r = urllib.request.Request(f'{API}/api/pricing')
    resp = json.loads(urllib.request.urlopen(r, timeout=5).read())
    p = resp.get('pricing', {})
    print('Pricing:', {k: {'monthly': v.get('price_monthly'), 'yearly': v.get('price_yearly')} for k, v in p.items()})

    # 3. Recommend
    data = json.dumps({'openid': 'test123'}).encode()
    r = urllib.request.Request(f'{API}/api/recommend-tier', data=data,
        headers={'Content-Type': 'application/json'})
    resp = json.loads(urllib.request.urlopen(r, timeout=10).read())
    print()
    print('=== RECOMMENDATION ===')
    for k, v in resp.items():
        print(f'  {k}: {v}')

    print()
    print('ALL OK')

test()
