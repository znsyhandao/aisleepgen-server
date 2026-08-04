#!/usr/bin/env python
import sys
sys.path.insert(0, 'D:/AISleepGen_Optimized')
from meditation_content import MEDITATION_SERIES, MEDITATION_ITEMS

total = sum(len(v) for v in MEDITATION_ITEMS.values())
print(f"Total items: {total}")
print(f"Total series: {len(MEDITATION_SERIES)}")
print()

for s in MEDITATION_SERIES:
    sid = s["id"]
    items = MEDITATION_ITEMS.get(sid, [])
    print(f"[{sid}] {s['name_cn']} ({len(items)} items)")
    for it in items:
        print(f"  {it['id']}. {it['title_cn']}")
    print()
