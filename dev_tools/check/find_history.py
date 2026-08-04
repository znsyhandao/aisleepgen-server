"""
find_history.py — 用户历史记录检索

从底层 deepseek_proxy.py 的 content 中提取用户历史上下文构建逻辑，
用于调试和审查消息拼接是否正确。
用法: python dev_tools/check/find_history.py
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read(1000000)

# 找 history_context 后 messages 的构建
idx = content.find('history_context')
sub = content[idx:idx+50000]

# 打印 history_context 之后5000字符内所有 messages 拼接
# 先找 history_context 被使用的具体位置
lines = content[:idx+50000].split('\n')
for i, line in enumerate(lines):
    if 'history_context' in line and 'build' not in line and 'def' not in line:
        print(f'Line {i+1}: {line[:150]}')
