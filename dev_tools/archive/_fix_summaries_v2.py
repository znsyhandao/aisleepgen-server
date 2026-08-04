# -*- coding: utf-8 -*-
"""正确删除_build_history_context中多余的summaries赋值"""
import sys, py_compile
sys.stdout.reconfigure(encoding='utf-8')

fp = r'D:\AISleepGen_Optimized\deepseek_proxy.py'

with open(fp, 'r', encoding='utf-8') as f:
    content = f.read()

# 确认重复：在 lines = [] 注释之后、if today_entries 块内
# 找 "确保 summaries" 后面的那个 duplicates
marker = "    # 确保 summaries 在整个作用域可用"
idx = content.find(marker)

# 在这个后面找第二个 "summaries = profile.get('conversation_summaries', [])"
after = content[idx:]
line_start = after.find('summaries = profile.get')
if line_start >= 0:
    first = content[idx:idx+line_start].count('\n')
    # 找第二个
    line_start2 = after.find('summaries = profile.get', line_start + 1)
    if line_start2 >= 0:
        second = content[idx:idx+line_start2].count('\n')
        # 看看是不是在"今天的情况"分支内
        snippet = after[line_start:line_start2+100]
        print(f'第一个在 {first} 行后')
        print(f'第二个在 {second} 行后')
        print(f'前20字符: {snippet[:20]}')
        print(f'后20字符: {snippet[-20:]}')
        
        # 删除的是第160行后的那个（emotion_timeline函数里的）
        # 实际上我们需要删的是第一个附近、但第二个（在L2619）那个
        # 但L2619是在 if today_entries 分支内的——不应该删
        # 真正的问题是L2619的分支内赋值让python认为summaries是局部变量
        
        # 更干净的修复：不删L2619，而是把L2605的values也放到if外或删掉L2619
        # 但删L2619会让today_entries分支内用不了summaries
        # 所以应该改L2652的循环：用全局的summaries而不是局部
        pass

# 实际修复：只改L2652那行，在循环之前加一句值提取
# L2652: "for s in reversed(summaries):"
# 改成在每个分支前先确保summaries可用

# 看L2652上下文
lines = content.split('\n')
for i, l in enumerate(lines, 1):
    if i == 2652 or (2648 <= i <= 2660):
        print(f'L{i}: {l}')
