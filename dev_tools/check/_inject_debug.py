import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
os.chdir('D:\\AISleepGen_Optimized')

# 直接深拷贝并注入调试代码到 _build_history_context
with open('deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在整个函数入口加一段注入，打印调用路径
inject = '''
def _build_history_context(openid='default'):
    import traceback
    print('[_build_history_context] CALLED with openid=%s' % openid)
    # 打印调用栈
    for line in traceback.format_stack()[-5:-1]:
        print('  CALLER:', line.strip()[:120])
'''
# 替换原函数
import re
# 用正则找到完整的 _build_history_context 函数
pattern = r'def _build_history_context\(openid=\'default\'\):(.*?)(?=\n\ndef \w+|$)'
import textwrap
# 找到原函数的开始和结束
lines = content.split('\n')
start = None
for i, line in enumerate(lines):
    if 'def _build_history_context' in line:
        start = i
        break

if start is not None:
    # 在原函数前注入一行
    lines.insert(start + 1, '    import traceback; traceback.print_stack(limit=5)')
    content = '\n'.join(lines)
    
    with open('deepseek_proxy.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('INJECTED at L%d' % (start + 2))
else:
    print('NOT FOUND')
