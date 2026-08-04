"""
test_compile.py — 快速编译检查

用 py_compile 检查指定 .py 文件的语法正确性。
用法: python dev_tools/check/test_compile.py
"""
"""
test_compile.py — 快速编译检查

用 py_compile 检查 deepseek_proxy.py 的语法正确性。
用法: python dev_tools/check/test_compile.py
"""
import py_compile, os
f = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'deepseek_proxy.py')
try:
    py_compile.compile(f, doraise=True)
    print('compile ok')
except Exception as e:
    print(f'compile fail: {e}')
