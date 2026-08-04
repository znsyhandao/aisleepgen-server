#!/usr/bin/env python
import re

f = open('D:/AISleepGen_Optimized/meditation_content.py', 'r', encoding='utf-8').read()
names = re.findall(r'"name": "(.+?)"', f)
titles = re.findall(r'"title": "(.+?)"', f)

print(f"Total series: {len(names)}")
for i, n in enumerate(names):
    print(f"  {i+1}. {n}")

print(f"\nTotal meditation items (titles): {len(titles)}")
print("First 30:")
for t in titles[:30]:
    print(f"  - {t}")
