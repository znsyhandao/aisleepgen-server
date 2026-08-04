# -*- coding: utf-8 -*-
import json, os, sys
sys.stdout.reconfigure(encoding='utf-8')

arch = json.load(open(r'D:\AISleepGen_Optimized\data\algorithm_archive.json', 'r', encoding='utf-8'))
if isinstance(arch, list):
    for x in arch:
        if isinstance(x, dict):
            p = x.get('priority', '?')
            n = x.get('name', '')
            l = x.get('landed', False)
            print(f'  [{p}] {n:45s} landed={l}')
    n_landed = sum(1 for x in arch if isinstance(x, dict) and x.get('landed'))
    print(f'\n总计{len(arch)}条, 已落地{n_landed}')
