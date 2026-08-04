# -*- coding: utf-8 -*-
"""
check_audit_injection.py — 检查 deepseek_proxy.py 审计注入结构

审计日志（wfile.write 代理）的正确注入位置必须在:
    do_POST → 解析 data → 注入 wfile.write 代理 → 路由分发

检查项:
    1. wfile.write 代理注入必须在 do_POST 方法内部（不是在 __init__）
    2. 代理注入在 rfile 读取（self.rfile.read）之后
    3. 没有在 do_POST 外部包装读取 rfile 的行为（会吃空数据）

用法:
    python check_audit_injection.py deepseek_proxy.py
"""
import sys, os, re

def check_audit_injection(filepath):
    with open(filepath, encoding='utf-8') as f:
        lines = f.readlines()

    issues = []

    # 1. 找到 do_POST 方法
    do_post_starts = []
    for i, line in enumerate(lines):
        if re.match(r'\s*def do_POST\b', line):
            do_post_starts.append(i)

    for idx, start in enumerate(do_post_starts):
        # 找到对应的方法结束（下一个 def 或 class）
        end = len(lines)
        for j in range(start + 1, min(start + 200, len(lines))):
            if re.match(r'\s*(def |class )', lines[j]) and j > start + 10:
                end = j
                break

        method_lines = lines[start:end]
        method_code = ''.join(method_lines)

        # 检查 __init__ 中是否有 wfile.write 代理
        init_found = False
        for prev_start in range(max(0, start - 200), start):
            if re.match(r'\s*def __init__\b', lines[prev_start]):
                init_end = min(prev_start + 100, len(lines))
                init_code = ''.join(lines[prev_start:init_end])
                if 'wfile' in init_code and 'write' in init_code:
                    if 'audit' in init_code.lower() or 'orig' in init_code.lower():
                        issues.append({
                            'severity': 'HIGH',
                            'msg': f'__init__ 中检测到 wfile.write 代理（L{prev_start+1}）',
                            'detail': 'BaseHTTPRequestHandler 的 __init__ 会重写 self.wfile，代理会被覆盖',
                            'line': prev_start
                        })
                        init_found = True
                        break
        if init_found:
            continue

        # 检查 do_POST 内是否在 rfile 读取前有 wfile.write 代理
        # 先找 rfile 读取
        rfile_line = None
        audit_proxy_before_rfile = False
        audit_proxy_after_data = False
        wfile_before_rfile = False

        for j, mline in enumerate(method_lines):
            stripped = mline.strip()
            if 'rfile.read' in stripped:
                rfile_line = start + j
            # 只有 wfile.write = function 赋值才算代理
            # self.wfile.write(data) 的直接调用不算
            if 'wfile.write =' in stripped:
                if rfile_line is None:
                    wfile_before_rfile = True
                elif start + j > rfile_line:
                    audit_proxy_after_data = True

        if wfile_before_rfile:
            issues.append({
                'severity': 'HIGH',
                'msg': f'do_POST 中 wfile.write 代理在 rfile 读取之前（L{start+1}区域）',
                'detail': '代理需要在 data 解析之后才注入，否则会吃到空数据',
                'line': start
            })

        if not audit_proxy_after_data:
            issues.append({
                'severity': 'MEDIUM',
                'msg': f'do_POST (L{start+1}) 未检测到 wfile.write 审计代理',
                'detail': '如果 audit_logger 已集成到路由中则无视此告警',
                'line': start
            })

    # 2. 检查是否有在 do_POST 外部 monkey-patch 读取 rfile
    method_new_defs = []
    for i, line in enumerate(lines):
        if 'def _new_do_POST' in line or 'def _patched_handler' in line:
            method_new_defs.append(i)
            # 检查其内部是否有 rfile
            for j in range(i, min(i + 50, len(lines))):
                if 'rfile' in lines[j]:
                    issues.append({
                        'severity': 'HIGH',
                        f'msg': f'L{i+1} 外部 monkey-patch 读取 rfile，会吃空数据',
                        'detail': '外部包裹读取 rfile 会导致原始 do_POST 数据解析为空',
                        'line': i
                    })
                    break

    return issues

def print_report(issues, filepath):
    print(f'\n{"="*60}')
    print(f'审计注入检查: {os.path.basename(filepath)}')
    print(f'{"="*60}')

    if not issues:
        print('\n✅ 检查通过，未发现问题')
        return

    high = [i for i in issues if i['severity'] == 'HIGH']
    medium = [i for i in issues if i['severity'] == 'MEDIUM']
    low = [i for i in issues if i['severity'] == 'LOW']

    if high:
        print(f'\n[RED] HIGH ({len(high)})')
        for i in high:
            print(f'  {i["msg"]}')
            print(f'    {i["detail"]}')

    if medium:
        print(f'\n[YELLOW] MEDIUM ({len(medium)})')
        for i in medium:
            print(f'  {i["msg"]}')
            print(f'    {i["detail"]}')

    issues_found = len(high) + len(medium) if high else 0
    if issues_found:
        print(f'\n[FAIL] {issues_found} 个问题')
    else:
        print(f'\n[PASS] 检查通过')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        filepath = 'D:\\AISleepGen_Optimized\\deepseek_proxy.py'
    else:
        filepath = sys.argv[1]

    if not os.path.exists(filepath):
        print(f'文件不存在: {filepath}')
        sys.exit(1)

    issues = check_audit_injection(filepath)
    print_report(issues, filepath)
