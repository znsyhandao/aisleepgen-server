# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'D:\AISleepGen_Optimized')

with open('dp_router.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f'Total lines: {len(lines)}')

# Lines 625-633 (0-indexed 624-632) are duplicate handle_wx_login code inside handle_chat
# Delete them
del lines[624:633]

print(f'After deletion: {len(lines)} lines')

# Verify line 624 is now the reply[:80] line followed by proper closing
print(f'Line 624 (last action trigger line): {repr(lines[623][:80])}')
print(f'Line 625 (should be next): {repr(lines[624][:80])}')

with open('dp_router.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

import py_compile
try:
    py_compile.compile('dp_router.py', doraise=True)
    print('COMPILATION: OK')
except py_compile.PyCompileError as e:
    print(f'COMPILE ERROR: {e}')
