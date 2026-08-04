import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 去掉 "{history_context}\n\n" 的第一个出现后的所有出现
# 更安全: 用尾部替换
old_tail = "\n\n{history_context}\n\n{wm_context}{evidence_context}{scene_context}"
new_tail = "\n\n【用户数据】\n{history_context}\n\n{wm_context}{evidence_context}{scene_context}"

# 实际上尾部的 {history_context} 后面还有内容，直接用更精确的替换
# 查找 "{history_context}\n\n{wm_context}{evidence_context}{scene_context}""""
tail_marker = '{history_context}\n\n{wm_context}{evidence_context}{scene_context}"""'
if tail_marker in content:
    content = content.replace(tail_marker, '{wm_context}{evidence_context}{scene_context}"""', 1)
    print('尾部重复的 {history_context} 已移除')
else:
    print('未找到尾部标记')

with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'w', encoding='utf-8') as f:
    f.write(content)

# 验证
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()
count = content.count('{history_context}')
print(f'剩余 {history_context} 出现次数: {count}')
