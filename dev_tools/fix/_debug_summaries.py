import sys, py_compile
sys.stdout.reconfigure(encoding='utf-8')
with open('deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 L1372 的 'summaries = profile.get' 前加一行 debug print
old = '        summaries = profile.get(\'conversation_summaries\', [])'
new = '''        print(f'[DEBUG] _build_history_context: openid={{openid}} history_len={{len(profile.get("history", []))}} summaries_raw_type={{type(profile.get("conversation_summaries", "MISSING")).__name__}}')
        summaries = profile.get('conversation_summaries', [])'''

if old in content:
    content = content.replace(old, new)
    with open('deepseek_proxy.py', 'w', encoding='utf-8') as f:
        f.write(content)
    py_compile.compile('deepseek_proxy.py', doraise=True)
    print('OK')
else:
    print('OLD TEXT NOT FOUND')
    # 找附近
    idx = content.find('conversation_summaries')
    print('Around:', repr(content[idx-50:idx+50]))
