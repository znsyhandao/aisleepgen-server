# -*- coding: utf-8 -*-
"""统一替换deepseek_proxy.py中冷冰冰的错误返回为人性化版本"""
import sys, re, py_compile
sys.stdout.reconfigure(encoding='utf-8')

fp = r'D:\AISleepGen_Optimized\deepseek_proxy.py'

with open(fp, 'r', encoding='utf-8') as f:
    content = f.read()

replacements = [
    # 1. 语音识别失败（L5494）
    ("{'ok': False, 'error': '语音识别失败，请重试或手动输'}",
     "{'ok': False, 'error': '没听清楚，能再说一次吗？或者打字告诉我'}"),
    
    # 2. except块中的通用错误（L5516）
    ("{'ok': False, 'error': str(e)[:100]}", 
     "{'ok': False, 'error': '连接好像不太稳定，稍等一下我重试好吗？'}"),
    
    # 3. 缺少语音文件（L5484）
    ("{'ok': False, 'error': '缺少语音文件'}",
     "{'ok': False, 'error': '好像没有收到语音，能再发一次吗？'}"),
    
    # 4. 缺少用户标识（L5680）
    ("{'success': False, 'error': '缺少用户标识'}",
     "{'success': False, 'error': '身份验证出了点小问题，重新进入一下就好'}"),
    
    # 5. 用户不存在（L5692）
    ("{'success': False, 'error': '用户不存'}",
     "{'success': False, 'error': '好像第一次见面？让我认识一下你'}"),
    
    # 6. 用户数据不存在（L6552）
    ("{'success': False, 'error': '用户数据不存'}",
     "{'success': False, 'error': '还没记录过睡眠数据，先睡一觉再来聊'}"),
    
    # 7. 数据不足（L6560）
    ("{'success': False, 'error': '数据不足，请先记录睡'}",
     "{'success': False, 'error': '数据还不够多，多记录几次睡眠我就能更好地帮你了'}"),
    
    # 8. 通用错误 - no_data（L8446）
    ("{'success': False, 'recall_text': '', 'error': 'no_data'}",
     "{'success': False, 'recall_text': '', 'error': '还没有记录，先聊聊你最近睡得怎么样？'}"),
]

changes = 0
for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        changes += 1
        print(f'  ✅ 替换: {old[:40]}...')
    else:
        print(f'  ⚠️  未找到: {old[:40]}...')

if changes > 0:
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'\n完成: 替换 {changes} 处')
else:
    print('\n无需更改')

try:
    py_compile.compile(fp, doraise=True)
    print('编译通过 ✅')
except py_compile.PyCompileError as e:
    print(f'编译失败: {e}')
