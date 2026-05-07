# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'D:\AISleepGen_Optimized')
from dp_router import handle_chat
import json

tests = [
    ('做个放松练习', '4-7-8'),
    ('身体扫描一下', 'body_scan'),
    ('做认知卸荷', 'cognitive_unloading'),
    ('矛盾意向疗法', 'paradoxical_intention'),
    ('刺激控制引导', 'stimulus_control'),
    ('睡眠卫生检查', 'sleep_hygiene'),
    ('认知重构一下', 'cognitive_restructuring'),
    ('红酒刺激胃酸', None),
]

all_ok = True
for msg, expected in tests:
    result = handle_chat({'openid':'test','message':msg,'history':[],'persona':'sweet'})
    actual = result.get('action')
    status = 'OK' if actual == expected else f'FAIL'
    if actual != expected:
        all_ok = False
    print(f'  [{status}] {msg} -> action={actual}')

print(f'\nALL OK: {all_ok}')
