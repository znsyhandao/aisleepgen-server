import sys, py_compile
sys.stdout.reconfigure(encoding='utf-8')
with open('deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复：将 summaries 赋值移到 if today_entries 块外面
old = '''        prefix = '【今天 用户修正】' if entry_type == 'correction' else f'【今天 {today}】'
        # 从 conversation_summaries 中找回复摘要
        summaries = profile.get('conversation_summaries', [])
        my_reply = '''''

new = '''        prefix = '【今天 用户修正】' if entry_type == 'correction' else f'【今天 {today}】'
        my_reply = '''

if old in content:
    content = content.replace(old, new, 1)
else:
    print('OLD1 NOT FOUND')
    # 再试只含 summaries 的那行
    old2 = '        summaries = profile.get(\'conversation_summaries\', [])'
    if old2 in content:
        # 直接在 old2 前加一行 summaries，在 if 外
        new2 = '    summaries = profile.get(\'conversation_summaries\', [])\n' + old2
        content = content.replace(new2, '    summaries = profile.get(\'conversation_summaries\', [])\n        summaries = profile.get(\'conversation_summaries\', [])')
    else:
        # 看看周围
        idx = content.find('conversation_summaries')
        print('Around:', repr(content[idx-20:idx+40]))

# 在 L1367 (if today_entries:) 之前加一个模块级 summaries 赋值
old3 = '    if today_entries:'
new3 = '    summaries = profile.get(\'conversation_summaries\', [])\n    if today_entries:'
content = content.replace(old3, new3, 1)

with open('deepseek_proxy.py', 'w', encoding='utf-8') as f:
    f.write(content)

py_compile.compile('deepseek_proxy.py', doraise=True)
print('OK')
