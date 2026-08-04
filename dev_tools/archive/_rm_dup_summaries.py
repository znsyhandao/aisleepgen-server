# -*- coding: utf-8 -*-
"""删除_build_history_context中多余的summaries赋值"""
import sys, py_compile
sys.stdout.reconfigure(encoding='utf-8')

fp = r'D:\AISleepGen_Optimized\deepseek_proxy.py'

with open(fp, 'rb') as f:
    content = f.read()

# 删除 "summaries = profile.get('conversation_summaries', [])" 在 if today_entries 块内的那行
# 精确匹配：16个空格 + 那行代码
pattern = b'        summaries = profile.get(\'conversation_summaries\', [])\r\n'
count = content.count(pattern)
print(f'找到 {count} 处')

# 删掉 if today_entries 块内的那行（不是函数级别的）
# 找到第二个出现位置
idx1 = content.find(pattern)
idx2 = content.find(pattern, idx1 + len(pattern)) if idx1 >= 0 else -1

print(f'第一处: {idx1}')
print(f'第二处: {idx2}')

# 第二处是在 if today_entries 块内的重复赋值，删除它
if idx2 >= 0:
    # 确认这是 not 函数级别的
    before = content[idx2-40:idx2]
    print(f'删除前上下文: {before}')
    
    # 删除整行（包括\r\n）
    content = content[:idx2] + content[idx2+len(pattern):]
    print('已删除第二处')
    
    with open(fp, 'wb') as f:
        f.write(content)
else:
    print('未找到第二处')

try:
    py_compile.compile(fp, doraise=True)
    print('编译通过')
except py_compile.PyCompileError as e:
    print(f'编译失败: {e}')
