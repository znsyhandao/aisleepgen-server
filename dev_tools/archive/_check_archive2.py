# -*- coding: utf-8 -*-
import json, os, sys
sys.stdout.reconfigure(encoding='utf-8')

d = json.load(open(r'D:\AISleepGen_Optimized\data\algorithm_archive.json', 'r', encoding='utf8'))
for k, v in list(d.items())[:10]:
    landed = v.get('landed')
    pri = v.get('priority', '?')
    print(f'{k}: landed={landed}, priority={pri}')
print(f'\nKey数量: {len(d)}')
