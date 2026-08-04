# -*- coding: utf-8 -*-
"""注入姬心脏主动对话到Butler返回体 v4"""
import py_compile

fp = r'D:\AISleepGen_Optimized\deepseek_proxy.py'

with open(fp, 'rb') as f:
    raw = f.read()

# 在 result['brief'] 那行和 print(f'[Butler]... 之间插入
marker_before = b"result['brief'] = BizIntelEngine.get_daily_brief()"
marker_after = b"print(f'[Butler] result show_brief="

idx_before = raw.find(marker_before)
idx_after = raw.find(marker_after, idx_before)

print(f'marker_before at {idx_before}')
print(f'marker_after at {idx_after}')

if idx_before >= 0 and idx_after >= 0:
    # 在 after 那行之前插入
    bol_after = raw.rfind(b'\n', 0, idx_after)
    
    insert = (
        b'\n\n'
        b'        # Inject Himiko active conversation\n'
        b'        if himiko_result and himiko_result.get(\'active_conversation\'):\n'
        b'            result[\'active_conversation\'] = himiko_result[\'active_conversation\']\n'
        b'            print(f\'[Himiko] active_conversation injected\')\n'
    )
    
    new_raw = raw[:bol_after] + insert + raw[bol_after:]
    
    with open(fp, 'wb') as f:
        f.write(new_raw)
    
    print(f'注入完成: +{len(insert)} 字节')
else:
    print('找不到插入点')

try:
    py_compile.compile(fp, doraise=True)
    print('编译通过')
except py_compile.PyCompileError as e:
    print(f'编译失败: {e}')
