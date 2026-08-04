import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 system_content = f""" 开头的第一行（"你是眠小兔，一名睡眠健康顾问"）之后
# 添加基线强制注入
old = """你是眠小兔，一名睡眠健康顾问

【推理约束规则 - 必须遵守】"""

new = """你是眠小兔，一名睡眠健康顾问

【用户数据 - 如有空则忽略，有数据时直接使用】
{history_context}

【推理约束规则 - 必须遵守】"""

content = content.replace(old, new, 1)
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('OK')
