# -*- coding: utf-8 -*-
"""删除L2619的重复summaries = profile.get(...)"""
with open(r'D:\AISleepGen_Optimized\deepseek_proxy.py', 'rb') as f:
    raw = f.read()

# 定位到"从 conversation_summaries 中找回复摘要"之后的第一行summaries赋值
marker = b'conversation_summaries \xe4\xb8\xad\xe6\x89\xbe\xe5\x9b\x9e\xe5\xa4\x8d\xe6\x91\x98\xe8\xa6\x81'
idx = raw.find(marker)
print(f'marker at {idx}')

if idx >= 0:
    # 从这个位置开始找第一个 assignments: summaries = profile.get
    rest = raw[idx:]
    target = b'summaries = profile.get(\'conversation_summaries\', [])'
    target_idx = rest.find(target)
    if target_idx >= 0:
        # 找到整行（从行首\n到行末\r\n）
        start_of_line = rest.rfind(b'\n', 0, target_idx)
        end_of_line = rest.find(b'\n', target_idx)
        if end_of_line < 0: end_of_line = len(rest)
        
        to_remove = rest[start_of_line:end_of_line+1]
        print(f'删除: {to_remove[:60]}')
        print(f'长度: {len(to_remove)}')
        
        new_raw = raw[:idx] + rest.replace(to_remove, b'', 1)
        with open(r'D:\AISleepGen_Optimized\deepseek_proxy.py', 'wb') as f:
            f.write(new_raw)
        print('完成')
    else:
        print('没找到目标行')
else:
    print('没找到标记')

import py_compile
try:
    py_compile.compile(r'D:\AISleepGen_Optimized\deepseek_proxy.py', doraise=True)
    print('编译通过')
except Exception as e:
    print(f'编译失败: {e}')
