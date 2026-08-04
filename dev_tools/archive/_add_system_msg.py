# -*- coding: utf-8 -*-
"""在chat.js中插入_addSystemMessage方法"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'D:\AISleepGen_Optimized\miniprogram\pages\chat\chat.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 toggleVoiceInput 和 startRecording 之间插入
insert_after = 'this.setData({ showVoiceInput: !this.data.showVoiceInput });'
idx = content.find(insert_after)
if idx >= 0:
    # 找到这个语句结尾的分号或逗号
    end = content.find(',', idx)
    if end < 0: end = content.find(';', idx)
    if end < 0: end = idx + len(insert_after)
    
    new_func = '''

  // 在对话中插入系统消息
  _addSystemMessage(msg) {
    var list = this.data.messages.slice();
    list.push({ role: 'ai', id: Date.now(), content: msg });
    this.setData({ messages: list });
  },
'''
    content = content[:end+1] + new_func + content[end+1:]
    
    with open(r'D:\AISleepGen_Optimized\miniprogram\pages\chat\chat.js', 'w', encoding='utf-8') as f:
        f.write(content)
    
    # 验证
    if 'function _addSystemMessage' in content or '_addSystemMessage(msg)' in content:
        print('已插入 _addSystemMessage')
else:
    print('找不到插入点')
