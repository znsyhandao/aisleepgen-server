import py_compile
f = r'D:\AISleepGen_Optimized\_test_hook_block3.py'
try:
    py_compile.compile(f, doraise=True)
    print('compile ok')
except Exception as e:
    print(f'compile fail: {e}')
