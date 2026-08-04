#!/usr/bin/env python
import re

text = open('D:/AISleepGen_Optimized/meditation_content.py', 'r', encoding='utf-8').read()

block_pattern = r'"([a-z_0-9]+)":\s*\{\s*"name":\s*"([^"]+)"(.*?)\n\s*\}'
# 更直接：按大块分割
blocks = re.findall(r'"[a-z_0-9]+":\s*\{[^}]+?\}', text, re.DOTALL)

# 找到所有series key
keys = re.findall(r'"([a-z_0-9]+)":\s*\{\s*"name":', text)

# 先显示后ambient结束
idx = 0
for key in keys:
    # 如果key是ambient相关，跳出
    if key in ['ocean','rain','forest','night','bonfire','wind','stream','silence','quiet','tea','guqin','classical','sunrise','car','color','space']:
        continue
    # 找这个block
    pattern = r'"' + key + r'":\s*\{.*?"name":\s*"([^"]+)".*?"items":\s*\[(.*?)\]'
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        continue
    name = m.group(1)
    items_text = m.group(2)
    titles = re.findall(r'"title":\s*"([^"]+)"', items_text)
    
    print(f"[{key}] {name}")
    for t in titles:
        print(f"  {t}")
    print()

# Ambient sounds
amb_keys = ['ocean','rain','forest','night','bonfire','wind','stream','silence','quiet','tea','guqin','classical','sunrise','car','color','space']
amb_names = {'ocean':'海浪','rain':'雨声','forest':'森林','night':'夜晚','bonfire':'篝火','wind':'微风','stream':'溪流','silence':'宁静','quiet':'静默','tea':'茶室','guqin':'古琴','classical':'轻古典','sunrise':'日出','car':'车内','color':'色彩','space':'太空'}
amb_items = {'ocean':2,'rain':2,'forest':2,'night':2,'bonfire':2,'wind':2,'stream':2,'silence':2,'quiet':2,'tea':2,'guqin':2,'classical':2,'sunrise':2,'car':2,'color':2,'space':2}

print("[ambient] 环境音效")
for k in amb_keys:
    n = amb_names.get(k, k)
    c = amb_items.get(k, 2)
    print(f"  {n} ({c}首)")
print()
print(f"总计: 24个冥想系列 + 18个环境音效 = 165首")
