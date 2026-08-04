"""
find_messages.py — 聊天消息检索

从 deepseek_proxy.py 中定位 messages 列表的组装位置，
确认 system_content + history_context + wm_context 的正确拼接。
用法: python dev_tools/check/find_messages.py
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# system_content 后面找 messages 组装
in_section = False
for i, line in enumerate(lines):
    if 'system_content = f' in line:
        in_section = True
    if in_section and "messages = [" in line:
        for j in range(i, min(i+20, len(lines))):
            print(f'{j+1}: {lines[j].rstrip()[:150]}')
        break
