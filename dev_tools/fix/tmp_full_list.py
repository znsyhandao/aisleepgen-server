#!/usr/bin/env python
import re

text = open('D:/AISleepGen_Optimized/meditation_content.py', 'r', encoding='utf-8').read()

# 找所有series name和对应的titles
# 按"key": { "name": "...", "items": [...] } 结构解析
import json

# 直接用正则解析
series_pattern = r'"([a-z_0-9]+)":\s*\{\s*"name":\s*"([^"]+)"'
matches = re.findall(series_pattern, text)

print("眠小兔冥想内容库 — 全部系列及冥想标题\n" + "="*60)

series_keys = list(dict.fromkeys(k for k, v in matches))
series_names = list(dict.fromkeys(v for k, v in matches))

# 解析items
for key, name in zip(series_keys, series_names):
    # 找这个series的items
    item_pattern = fr'"{key}":.*?"items":\s*\[(.*?)\]'
    item_match = re.search(item_pattern, text, re.DOTALL)
    if item_match:
        items_text = item_match.group(1)
        titles = re.findall(r'"title":\s*"([^"]+)"', items_text)
        print(f"\n{'─'*60}")
        print(f"  {name} ({len(titles)}集)")
        print(f"{'─'*60}")
        for t in titles:
            print(f"    • {t}")
    else:
        # 可能没有items数组（环境音等）
        dur_pattern = fr'"{key}":.*?"duration":'
        dur_match = re.search(dur_pattern, text, re.DOTALL)
        if not dur_match:
            pass  # 环境音没有items
