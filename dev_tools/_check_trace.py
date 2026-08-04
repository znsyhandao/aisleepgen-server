# 检查注入点
import sys, py_compile
sys.stdout.reconfigure(encoding='utf-8')

bak = r'D:\AISleepGen_Optimized\.surgical_backups\deepseek_proxy.py_20260520_105204.bak'

# 编译原版
try:
    py_compile.compile(r'D:\AISleepGen_Optimized\deepseek_proxy.py', doraise=True)
    print('Current file: OK')
except Exception as e:
    print('Current file: FAIL', e)

with open(bak, 'r', encoding='utf-8') as f:
    content = f.read()

# 检查 markers 现在的位置
markers = [
    ('openid', 'openid = self._get_openid(data)'),
    ('before_history', '        # \u6784\u5efa\u5386\u53f2\u753b\u50cf\u4e0a\u4e0b\u6587\uff08\u542b\u4e13\u5bb6\u56de\u987e\u6570\u636e\uff09'),
    ('after_history', '# \u6784\u5efa\u5386\u53f2\u753b\u50cf\u4e0a\u4e0b\u6587\uff08\u542b\u4e13\u5bb6\u56de\u987e\u6570\u636e\uff09'),
    ('messages', "messages = [{'role': 'system', 'content': system_content}]"),
    ('latest_updates', "            if 'latest' in updates:"),
]

for name, marker in markers:
    idx = content.find(marker)
    if idx >= 0:
        line_no = content[:idx].count('\n') + 1
        print(f'Marker [{name}] at line {line_no}')
    else:
        print(f'Marker [{name}] NOT FOUND')

# 检查注入后所有的 [Trace] 行
trace_count = content.count('[Trace')
print(f'\n[Trace] occurrences after injection: {trace_count}')

# 如果 >0，看哪里的问题
if trace_count > 0:
    lines_after = content[:idx].count('\n') if idx >= 0 else 0
    # 找一个 trace 行看看
    for i, line in enumerate(content.split('\n'), 1):
        if '[Trace' in line:
            print(f'  Trace at L{i}: {line.strip()[:120]}')
