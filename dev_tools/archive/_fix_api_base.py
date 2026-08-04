import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\AISleepGen_Optimized\\miniprogram\\utils\\api.js', 'r', encoding='utf-8') as f:
    content = f.read()

old = "const API_BASE = 'http://82.156.208.245'"
new = "const API_BASE = 'http://localhost:8090'"

if old in content:
    content = content.replace(old, new, 1)
    with open('D:\\AISleepGen_Optimized\\miniprogram\\utils\\api.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print('API_BASE changed to localhost:8090')
else:
    print('Not found')
    # 看看现在什么值
    idx = content.find('API_BASE')
    print(content[idx:idx+50])
