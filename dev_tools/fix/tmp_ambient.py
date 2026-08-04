#!/usr/bin/env python
import re

text = open('D:/AISleepGen_Optimized/meditation_content.py', 'r', encoding='utf-8').read()

# 找ambient音效
ambient_match = re.search(r'AMBIENT_SOUNDS\s*=\s*\{.*?\}', text, re.DOTALL)
if ambient_match:
    ambient_text = ambient_match.group()
    sounds = re.findall(r'"([^"]+)":\s*\{', ambient_text)
    print("🌙 环境音效系列:")
    for s in sounds:
        print(f"    • {s}")

print("\n\n=== 总数统计 ===")
all_titles = re.findall(r'"title":\s*"([^"]+)"', text)
print(f"冥想+环境音总条目: {len(all_titles)}")
