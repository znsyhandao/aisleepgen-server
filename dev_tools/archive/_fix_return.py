# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'D:\AISleepGen_Optimized')

with open('dp_router.py', 'rb') as f:
    c = bytearray(f.read())

# Find the last occurrence of reply[:80]
# The line ends with \r\n on Windows
i = c.rfind(b'reply = reply[:80]')
eol = c.find(b'\n', i) + 1  # include the \n
insert_at = eol
print(f'Inserting at byte: {insert_at}')
print(f'Before: {c[insert_at-5:insert_at]}')
print(f'After: {c[insert_at:insert_at+30]}')

ret_block = """
    return {
        'reply': reply,
        'action': _action_trigger,
        'meditation_protocol': _action_trigger,
        'token_estimate': token_estimate,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'ai_score': round(score, 1) if isinstance(score, (int, float)) else None,
        'ai_quality': quality if quality else None,
        'debate': deb if deb else None,
        'async_pipeline': True,
        'local_only': pipeline_result.get('local_only', False),
        'elapsed_ms': pipeline_result.get('elapsed_ms', 0),
        'companion': companion_initial if companion_started else None,
        'expert_detail': pipeline_result.get('expert_detail', {}),
    }

"""

ret_bytes = ret_block.encode('utf-8')
result = c[:insert_at] + ret_bytes + c[insert_at:]

with open('dp_router.py', 'wb') as f:
    f.write(result)

import py_compile
try:
    py_compile.compile('dp_router.py', doraise=True)
    print('COMPILATION: OK')
except py_compile.PyCompileError as e:
    print(f'COMPILE ERROR: {e}')
