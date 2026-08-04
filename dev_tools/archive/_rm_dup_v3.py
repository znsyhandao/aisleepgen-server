# -*- coding: utf-8 -*-
"""删掉_build_history_context中if today_entries块内的重复summaries赋值"""
import py_compile

fp = r'D:\AISleepGen_Optimized\deepseek_proxy.py'

with open(fp, 'rb') as f:
    raw = f.read()

# 删除 L2618 那行: "        summaries = profile.get('conversation_summaries', [])"
# 精确匹配字节
pattern = b'        summaries = profile.get(\'conversation_summaries\', [])\r\n'

# 找第二次出现（第一个是函数级，第二个是分支内，第三个是另一个函数）
idx1 = raw.find(pattern)
idx2 = raw.find(pattern, idx1 + len(pattern))
idx3 = raw.find(pattern, idx2 + len(pattern))

print(f'第一处(函数级): {idx1}')
print(f'第二处(L2618分支内): {idx2}')
print(f'第三处(另一函数): {idx3}')

# 删第二处
if idx2 >= 0 and idx2 != idx1:
    # 确认前文是"# 从 conversation_summaries"
    before = raw[idx2-60:idx2]
    print(f'第二处前文: {before}')
    
    raw = raw[:idx2] + raw[idx2+len(pattern):]
    print('已删除第二处重复赋值')
    
    with open(fp, 'wb') as f:
        f.write(raw)

try:
    py_compile.compile(fp, doraise=True)
    print('编译通过')
except py_compile.PyCompileError as e:
    print(f'编译失败: {e}')
