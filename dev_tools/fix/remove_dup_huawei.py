#!/usr/bin/env python3
"""Remove duplicated huawei handlers from deepseek_proxy.py"""
import re

with open(r'D:\AISleepGen_Optimized\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find lines to remove: from "    def _handle_huawei_authorize" (standalone outside class)
# to blank line before "def _handle_prediction_stats"
remove_start = None
remove_end = None

for i, line in enumerate(lines):
    # Look for the duplicated handlers: 4-space indent, after "except Exception:\n        pass\n\n"
    stripped = line.strip()
    if i > 6960 and i < 6980:
        if stripped.startswith('def _handle_huawei') and 'self' in line:
            # Check if this is inside the class or after it
            # Look backwards for the last 0-indent def
            for j in range(i-1, max(0, i-10), -1):
                if lines[j].strip().startswith('def ') and not lines[j].startswith(' '):
                    remove_start = i
                    break
            if remove_start:
                break

# Alternative: find by pattern - after "except Exception:\n        pass\n\n"
for i in range(6960, min(len(lines), 6980)):
    if lines[i].rstrip() == 'except Exception:':
        if i+1 < len(lines) and lines[i+1].strip() == 'pass':
            if i+2 < len(lines) and not lines[i+2].strip():
                # Check next non-empty line
                for k in range(i+3, min(i+6, len(lines))):
                    if lines[k].strip().startswith('def _handle_huawei'):
                        remove_start = i+3
                        break
    
    if remove_start:
        break

if remove_start:
    # Find the "def _handle_prediction_stats" that follows
    for j in range(remove_start, min(remove_start + 80, len(lines))):
        stripped = lines[j].strip()
        if stripped.startswith('def _handle_prediction_stats'):
            remove_end = j - 1
            break
    
    if not remove_end:
        # Find next 0-indent function
        for j in range(remove_start, min(remove_start + 80, len(lines))):
            if lines[j].strip().startswith('def ') and not lines[j].startswith(' '):
                remove_end = j - 1
                break
    
    if not remove_end:
        remove_end = remove_start + 76
    
    stripped = ''.join(lines[:remove_start] + lines[remove_end:])
    
    # Also remove trailing blank lines
    while stripped.endswith('\n\n\n\n'):
        stripped = stripped[:-1]
    
    with open(r'D:\AISleepGen_Optimized\deepseek_proxy.py', 'w', encoding='utf-8') as f:
        f.write(stripped)
    
    print(f'Removed lines {remove_start+1}-{remove_end+1}')
    print(f'File now {len(stripped.splitlines())} lines')
else:
    print('Could not find removal point - checking manually...')
    # Debug: show lines 6960-6980
    for i in range(6960, min(6980, len(lines))):
        print(f'{i+1}: {lines[i].rstrip()[:100]}')
