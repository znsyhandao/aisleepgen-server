import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')

key = os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('OPENAI_API_KEY')
if key:
    print('API key from env: {}...'.format(key[:12]))
else:
    with open('deepseek_proxy.py', 'r', encoding='utf-8') as f:
        content = f.read()
    keys = re.findall(r'["\'](sk-[a-zA-Z0-9]+)["\']', content)
    for k in keys:
        print('Found in code: {}...'.format(k[:12]))
        break
    else:
        print('No API key found')
        # 看格式
        print('\n--- Looking for key patterns...')
        for line in content.split('\n'):
            if 'api_key' in line.lower() or 'API_KEY' in line or 'sk-' in line:
                print('  ' + line.strip()[:120])
