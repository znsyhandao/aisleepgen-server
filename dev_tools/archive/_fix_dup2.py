import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = """【有历史数据时的特殊情况 - 覆盖规则1和规则2】
{history_context} 中包含了用户的睡眠数据。直接使用这些数据进行讨论和分析。禁止问"你几点睡几点起"——数据已在上下文中提供。直接说"你平时23:30睡7:00起..."或引用评分作分析。提问限于"昨晚和之前比有变化吗？""入睡快些了吗？"这类进阶问题。"""

new = """【有历史数据时的特殊情况 - 覆盖规则1和规则2】
上面【用户数据】中包含了用户的睡眠数据。直接使用这些数据进行讨论和分析。禁止问"你几点睡几点起"——数据已在上下文中提供。直接说"你平时23:30睡7:00起..."或引用评分作分析。提问限于"昨晚和之前比有变化吗？""入睡快些了吗？"这类进阶问题。"""

content = content.replace(old, new, 1)
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'w', encoding='utf-8') as f:
    f.write(content)

count = content.count('{history_context}')
print(f'剩余 {history_context} 出现次数: {count}')
