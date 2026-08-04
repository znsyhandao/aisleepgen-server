# -*- coding: utf-8 -*-
"""最小测试：导入_build_history_context看看是否报错"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(r'D:\AISleepGen_Optimized')

import importlib.util
spec = importlib.util.spec_from_file_location('dsp', r'D:\AISleepGen_Optimized\deepseek_proxy.py')
mod = importlib.util.module_from_spec(spec)

# compile source
import py_compile
try:
    py_compile.compile(r'D:\AISleepGen_Optimized\deepseek_proxy.py', doraise=True)
    print('编译通过')
except Exception as e:
    print(f'编译失败: {e}')

# 直接执行函数测试
with open(r'D:\AISleepGen_Optimized\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    code = f.read()
compiled = compile(code, 'deepseek_proxy.py', 'exec')

# 创建mock环境
ns = {'__name__': '__test__', '__file__': 'deepseek_proxy.py'}
try:
    exec(compiled, ns)
    # 如果有_build_history_context
    if '_build_history_context' in ns:
        try:
            result = ns['_build_history_context'](openid='test')
            print(f'函数调用成功: {type(result)}')
        except Exception as e:
            import traceback
            print(f'函数调用失败: {e}')
            traceback.print_exc()
    else:
        print('函数未加载（可能需要更多依赖）')
except Exception as e:
    import traceback
    print(f'模块加载失败: {e}')
    traceback.print_exc()
