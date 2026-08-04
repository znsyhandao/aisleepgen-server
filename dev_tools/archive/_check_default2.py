import json, sys
sys.stdout.reconfigure(encoding='utf-8')
with open('D:\\AISleepGen_Optimized\\user_profile.json', 'r', encoding='utf-8') as f:
    all_p = json.load(f)

p = all_p.get('default', {})
print('default profile 来源:')
# 看 history 里第一个条目的信息
h = p.get('history', [])
if h:
    print(f'history 第1条: {json.dumps(h[0], ensure_ascii=False)[:200]}')
else:
    print('history 为空')

# latest 数据
lt = p.get('latest', {})
print(f'latest: {json.dumps(lt, ensure_ascii=False)}')

# 看世界模型更新
print(f'wm_updated_at: {lt.get("wm_updated_at")}')
print(f'score: {lt.get("score")}')
print(f'stress_level: {lt.get("stress_level")}')
