# -*- coding: utf-8 -*-
"""在chat.js的butlerCheck回调中添加姬心脏话题卡片注入"""
import py_compile

fp = r'D:\AISleepGen_Optimized\miniprogram\pages\chat\chat.js'

with open(fp, 'r', encoding='utf-8') as f:
    content = f.read()

# 找到 butlerCheck().then(function(res) 中设置butlerAlert的部分之后
# 插入点：在设完butlerAlert后，检查 active_conversation
insertion_marker = "console.log('[Butler]"
idx = content.find(insertion_marker)
if idx < 0:
    print('找不到插入点')
    exit()

# 找到then回调的完整结构
# 找到setData设置butlerAlert的地方
setdata_marker = "butlerAlert: alert"
idx2 = content.find(setdata_marker, idx)
if idx2 < 0:
    print('找不到setData点')
    exit()

# 在butlerAlert设置后的分号/逗号后插入active_conversation逻辑
# 找这个setData调用结束的括号
snippet = content[idx2:idx2+300]
print(f'找到setData点: {snippet[:150]}')

# 注入点：在 // 设置初始快速话题之前或之后
# 找 setData({ 完整的结束 
brace_open = content.find('{', idx2)
# 找匹配的 }
depth = 0
brace_close = -1
for i in range(brace_open, len(content)):
    if content[i] == '{': depth += 1
    if content[i] == '}': depth -= 1
    if depth == 0:
        brace_close = i
        break

print(f'setData括号: {brace_open} -> {brace_close}')

if brace_close > brace_open:
    # 在setData内添加activeConversation
    # 先找到quickReplies的赋值
    qr_marker = 'quickReplies:'
    qr_idx = content.find(qr_marker, idx, brace_close)
    
    print(f'quickReplies found at: {qr_idx}')
    
    if qr_idx > 0:
        # 找到同逗号结尾的
        qr_end = content.find(',', qr_idx)
        # quickReplies: [],  -> quickReplies: [...],
        new_code = (",activeConversation: res.active_conversation || null" + 
                    "/*himiko_inject*/")
        # 在quickReplies行前插入
        pre_qr = content.rfind('\n', 0, qr_idx)
        content = content[:pre_qr] + new_code + content[pre_qr:]
        print(f'注入activeConversation到data: +{len(new_code)} 字符')
    else:
        print('quickReplies不在当前setData中')
else:
    print(f'无法找到setData结束位置')

with open(fp, 'w', encoding='utf-8') as f:
    f.write(content)

# 验证
import os
print(f'文件大小: {os.path.getsize(fp)}')

# 找所有butlerCheck调用
idx = content.find('butlerCheck().then')
if idx >= 0:
    # 看看active_conversation有没有被引用
    ac_idx = content.find('active_conversation', idx)
    print(f'active_conversation 引用: {ac_idx}')
    if ac_idx >= 0:
        print('已注入active_conversation到data')
