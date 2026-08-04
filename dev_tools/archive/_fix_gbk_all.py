# -*- coding: utf-8 -*-
"""批量修复所有子模块的GBK编码兼容性"""
import sys, os

sys.stdout.reconfigure(encoding='utf-8')

files_to_fix = [
    r'D:\AISleepGen_Optimized\feedback_short_circuit.py',
    r'D:\AISleepGen_Optimized\experiment_grim_reaper.py',
    r'D:\AISleepGen_Optimized\auto_hypothesis.py',
    r'D:\AISleepGen_Optimized\adversarial_training.py',
    r'D:\AISleepGen_Optimized\implicit_feedback_decoder.py',
    r'D:\AISleepGen_Optimized\baowang_emulator.py',
    r'D:\AISleepGen_Optimized\dual_brain_loop.py',
    r'D:\AISleepGen_Optimized\input_compressor.py',
]

# 在所有模块顶部加UTF-8安全打印
REQUIRED_HEADER = '''import sys
if hasattr(sys, "stdout") and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
'''

for fp in files_to_fix:
    if not os.path.exists(fp):
        print(f'SKIP: {os.path.basename(fp)} not found')
        continue
    
    with open(fp, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否已有reconfigure
    if 'stdout.reconfigure' in content:
        print(f'  SKIP (already fixed): {os.path.basename(fp)}')
        continue
    
    # 在首个import之后插入
    import re
    # 找第一个import语句
    lines = content.split('\n')
    insert_pos = 0
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            # 找最后一个import
            pass
        if line.startswith('# ') or line.startswith('#!'):
            continue
        if line.strip() == '':
            continue
        if not (line.startswith('import ') or line.startswith('from ')):
            insert_pos = i
            break
    
    # 在最后一个import行后插入
    if insert_pos == 0:
        # 没有import（不太可能）
        lines.insert(0, REQUIRED_HEADER)
    else:
        for j in range(insert_pos - 1, -1, -1):
            if lines[j].startswith('import ') or lines[j].startswith('from '):
                lines.insert(j + 1, '')
                lines.insert(j + 2, REQUIRED_HEADER.strip())
                break
        else:
            lines.insert(0, REQUIRED_HEADER)
    
    new_content = '\n'.join(lines)
    
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    # 验证
    import py_compile
    try:
        py_compile.compile(fp, doraise=True)
        print(f'  OK: {os.path.basename(fp)}')
    except py_compile.PyCompileError as e:
        print(f'  FAIL: {os.path.basename(fp)}: {e}')
        # revert
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'  REVERTED: {os.path.basename(fp)}')

print('\nDone')
