import json, urllib.request, sys
sys.stdout.reconfigure(encoding='utf-8')

def req(method, path, data=None, timeout=30):
    r = urllib.request.Request(f'http://localhost:8090{path}', 
        data=json.dumps(data).encode() if data else None,
        headers={'Content-Type':'application/json'}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except Exception as e:
        return 0, str(e)

# 1. stop-breathing
code, r = req('POST', '/api/stop-breathing', {'openid':'default'})
print(f'stop-breathing: {code} {str(r)[:300]}')

# 2. relax-feedback
code, r = req('POST', '/api/relax-feedback', {'openid':'default','score':8,'pattern':'4-7-8'})
print(f'relax-feedback: {code} {str(r)[:300]}')

# 3. data-export
code, r = req('GET', '/api/data-export?openid=default')
print(f'data-export: {code} {str(r)[:300]}')

# 4. memory-recall
code, r = req('POST', '/api/memory-recall', {'openid':'default'})
print(f'memory-recall: {code} {str(r)[:300]}')
