#!/usr/bin/env python3
"""End-to-end test: verify SAE features injected in real HTTP response"""
import urllib.request, json

# health check
r = urllib.request.urlopen('http://localhost:8090/health', timeout=10)
h = json.loads(r.read())
status = h.get('status', '?')
print(f'Health: {status}')

# world-step
data = json.dumps({
    'openid': 'test_sae_user',
    'session_id': 'test_sae_session',
    'hr': 72,
    'stress': 5,
    'elapsed_s': 10,
}).encode()
r = urllib.request.urlopen('http://localhost:8090/api/sleep/world-step', data=data, timeout=15)
resp = json.loads(r.read())
has_sae = '_sae_features' in resp
print(f'world-step SAE: {has_sae}')
if has_sae:
    print(json.dumps(resp['_sae_features'], indent=2))
else:
    print(f'Keys: {list(resp.keys())[:5]}')
