# -*- coding: utf-8 -*-
"""继续替换剩余的错误返回"""
import py_compile

fp = r'D:\AISleepGen_Optimized\deepseek_proxy.py'
with open(fp, 'r', encoding='utf-8') as f:
    content = f.read()

replacements = {
    "语音识别失败，请重试或手动输入": "没听清楚，能再说一次吗？或者打字告诉我",
    "用户不存在": "好像第一次见面？让我认识一下你",
    "用户数据不存在": "还没记录过睡眠数据，先睡一觉再来聊",
    "数据不足，请先记录睡眠": "数据还不够多，多记录几次睡眠我就能更好地帮你了",
}

changed = 0
for old_msg, new_msg in replacements.items():
    if old_msg in content:
        content = content.replace(old_msg, new_msg)
        changed += 1
        print(f'替换: {old_msg}')

if changed > 0:
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'\n共修改 {changed} 处')

try:
    py_compile.compile(fp, doraise=True)
    print('编译通过')
except py_compile.PyCompileError as e:
    print(f'编译失败: {e}')
