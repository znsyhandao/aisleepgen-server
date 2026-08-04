# -*- coding: utf-8 -*-
"""在首页grid末尾添加半夜语音唤醒入口 v2"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'D:\AISleepGen_Optimized\miniprogram\pages\index\index.wxml', 'r', encoding='utf-8') as f:
    content = f.read()

# 找grid结束的标记
# 模式：quick-grid 区域后有一个 </view> 闭合
grid_end = content.find('quick-grid')
if grid_end < 0: grid_end = content.find('grid-container')
if grid_end < 0: grid_end = content.find('quick-wrapper')
print(f'grid标记 at: {grid_end}')

# 直接找 '绑定手环' 或最后一个quick-item后的闭合
# 在 '绑定手环' 后面加
bind_idx = content.find('绑定手环')
if bind_idx < 0:
    bind_idx = content.find('身体扫描')
print(f'绑定手环 at: {bind_idx}')

if bind_idx > 0:
    # 找到这个item的结束标签
    item_close = content.find('</view>', bind_idx)
    if item_close > 0:
        insert = '''
  <view class="quick-item" bindtap="goChatVoiceSleep">
    <text class="quick-icon">🌙</text>
    <text class="quick-label">半夜醒来</text>
    <text class="quick-desc">按住说话，AI陪你</text>
  </view>'''
        content = content[:item_close+7] + insert + content[item_close+7:]
        with open(r'D:\AISleepGen_Optimized\miniprogram\pages\index\index.wxml', 'w', encoding='utf-8') as f:
            f.write(content)
        print('已插入半夜唤醒入口')
else:
    print('找不到绑定手环')
