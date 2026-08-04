import sys, py_compile
sys.stdout.reconfigure(encoding='utf-8')
with open('deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找 do_POST 的 except 块，加完整 traceback
old = '''            print(f'[do_POST] 未捕获异常: {_post_e}')
            self.send_response(500)'''

new = '''            print(f'[do_POST] FULL TRACE: {_tb.format_exc()[:1000]}')
            print(f'[do_POST] 未捕获异常: {_post_e}')
            self.send_response(500)'''

# 也可能是 print 行不存在（只在 debug 注入后才有）
# 看下 L2025 附近
lines = content.split('\n')
idx = None
for i, line in enumerate(lines):
    if '_post_inner' in line:
        # 找到 _do_post_inner() 之后的 except 块
        for j in range(i, min(i+10, len(lines))):
            if 'print' in lines[j] and '未捕获异常' in lines[j]:
                idx = j
                break
        if idx:
            break

if idx:
    # 在这个 print 行前加一行
    indent = len(lines[idx]) - len(lines[idx].lstrip())
    lines.insert(idx, ' ' * indent + f"full_tb = _tb.format_exc(); print(f'[do_POST] FULL TRACE: {{full_tb[:1000]}}')")
    content = '\n'.join(lines)

with open('deepseek_proxy.py', 'w', encoding='utf-8') as f:
    f.write(content)
py_compile.compile('deepseek_proxy.py', doraise=True)
print('OK')
