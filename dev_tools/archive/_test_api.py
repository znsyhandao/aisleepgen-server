import requests, json
# 正确路由
r = requests.post('http://localhost:8090/api/chat', json={'messages':[{'role':'user','content':'睡眠评分75分，入睡慢，怎么办'}]}, timeout=60)
print(f'Status: {r.status_code}')
data = r.json()
print(json.dumps(data, ensure_ascii=False)[:500])
