# -*- coding: utf-8 -*-
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

d = json.load(open(r'D:\AISleepGen_Optimized\data\_prioritized_action.json', 'r', encoding='utf-8'))
print(f'行动: {d["action"]}')
print(f'置信度: {d["action_confidence"]}')
print()
for k, v in d['vector'].items():
    print(f'  {k}: {v}')
print()
for k, v in d['entropy_map'].items():
    print(f'  {k}: {v}')
