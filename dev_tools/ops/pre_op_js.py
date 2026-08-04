#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pre_op_js.py — 前端JS/JSON修改前预检（对标pre_op.py）

用法: python dev_tools/ops/pre_op_js.py <文件路径>
回滚: copy .surgical_backups/<filename>_<timestamp>.bak <filename>
"""

import sys, os, shutil, datetime, json

def check_js(content, path):
    """JS 基础检查：括号匹配 + 双逗号 + 常见语法错"""
    issues = []
    
    # 双逗号
    if ',,' in content:
        # 排除字符串里的
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if ',,' in stripped and not stripped.startswith('//') and not stripped.startswith('/*'):
                issues.append((i, 'DOUBLE COMMA', stripped[:80]))
    
    # 大括号匹配
    stack = []
    for i, ch in enumerate(content):
        if ch == '{':
            stack.append('{')
        elif ch == '}':
            if not stack:
                issues.append((content[:i].count('\n') + 1, 'EXTRA CLOSING BRACE', ''))
                break
            stack.pop()
        elif ch == '[':
            stack.append('[')
        elif ch == ']':
            if not stack or stack[-1] != '[':
                issues.append((content[:i].count('\n') + 1, 'MISMATCHED BRACKET', ''))
                break
            stack.pop()
    
    if stack:
        issues.append((-1, f'UNCLOSED BRACKETS: {len(stack)} remaining', ''))
    
    # exports 块语法快速检查
    if 'module.exports' in content:
        idx = content.find('module.exports')
        after = content[idx:]
        if after.count(',') > after.count('\n') * 2:
            issues.append((-1, 'WARN: exports可能有尾逗号', ''))
        # 检查 exports 块内是否有缺失逗号的行（非最后一行的 key: value 后面没有逗号）
        export_lines = after.split('\n')
        for i, line in enumerate(export_lines):
            stripped = line.strip()
            # key: value  且不是最后一行，且没有尾逗号
            if ':' in stripped and not stripped.endswith(',') and not stripped.startswith('}'):
                # 跳过以 { 开头或包含 { 的多行对象
                if not stripped.endswith('{') and '{' not in stripped:
                    # 确认这行没有在函数体内部
                    indent = len(line) - len(line.lstrip())
                    if indent > 0 and 'function' not in stripped and '=>' not in stripped and 'if' not in stripped.split(':')[0]:
                        issues.append((idx + i, 'MISSING COMMA', stripped[:80]))
    
    return issues

def pre_op_js(filepath):
    if not os.path.exists(filepath):
        print(f'[pre_op_js] File not found: {filepath}')
        sys.exit(1)
    
    print(f'[pre_op_js] Target: {os.path.basename(filepath)}')
    
    # 备份
    bak_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.surgical_backups')
    os.makedirs(bak_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = os.path.join(bak_dir, f'{os.path.basename(filepath)}_{ts}.bak')
    shutil.copy2(filepath, bak)
    print(f'[pre_op_js] Backup: {str(bak)[-40:]}')
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    issues = check_js(content, filepath)
    
    if issues:
        print('[pre_op_js] ISSUES FOUND:')
        for line, typ, detail in issues:
            print(f'  {typ} at line {line}: {detail}')
        print('[pre_op_js] Fix before editing!')
        print(f'[pre_op_js] Rollback: copy {str(bak)[-40:]} {filepath}')
        return False
    else:
        print('[pre_op_js] OK - no issues found')
        return True

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python pre_op_js.py <file.js>')
        sys.exit(1)
    success = pre_op_js(sys.argv[1])
    sys.exit(0 if success else 1)
