"""Smoke test for all payment + recommendation APIs"""
import urllib.request, json, sys

API = 'http://82.156.208.245:8090'

def check(name, method='GET', path='/health', data=None):
    try:
        if method == 'GET':
            r = urllib.request.Request(f'{API}{path}')
        else:
            body = json.dumps(data).encode() if data else b'{}'
            r = urllib.request.Request(f'{API}{path}', data=body,
                headers={'Content-Type': 'application/json'}, method=method)
        resp = json.loads(urllib.request.urlopen(r, timeout=10).read())
        sys.stdout.write(f'  OK  {name}\n')
        return resp
    except Exception as e:
        sys.stdout.write(f'  FAIL {name}: {e}\n')
        return None

print('=== Smoke Test: Payment + Recommendation APIs ===')
print()

# 1. Health
check('GET /health', 'GET', '/health')

# 2. Pricing
p = check('GET /api/pricing', 'GET', '/api/pricing')
if p:
    tiers = list(p.get('pricing', {}).keys())
    stages = p.get('lifecycle_stages', [])
    sys.stdout.write(f'       Tiers: {tiers}, Stages: {len(stages)}\n')

# 3. Recommend (cold user)
r = check('POST /api/recommend-tier (cold)', 'POST', '/api/recommend-tier', {'openid': 'test123'})
if r:
    sys.stdout.write(f'       should_recommend={r.get("should_recommend")}, '
                     f'tier={r.get("tier")}, lifecycle={r.get("lifecycle")}, '
                     f'discount={r.get("discount_label")}\n')

# 4. Recommend (create a heavy user profile first)
# Put some fake data to trigger heavy_free scenario
data = {'openid': 'test_heavy', 'onboarding_survey': {'main_issue': 'insomnia'}}
urllib.request.Request(f'{API}/api/update-profile',
    data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'}).open()

r = check('POST /api/recommend-tier (heavy)', 'POST', '/api/recommend-tier', {'openid': 'test_heavy'})
if r:
    sys.stdout.write(f'       should_recommend={r.get("should_recommend")}, '
                     f'tier={r.get("tier")}, lifecycle={r.get("lifecycle")}\n')

# 5. Create order (should return no_payment)
order = check('POST /api/create-order', 'POST', '/api/create-order',
              {'openid': 'test123', 'tier': 'pro', 'period': 'month'})
if order:
    sys.stdout.write(f'       success={order.get("success")}, '
                     f'no_payment={order.get("no_payment")}\n')

print()
print('=== DONE ===')
