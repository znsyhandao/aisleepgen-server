# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'D:\AISleepGen_Optimized')
from dp_router import handle_chat

tests = [
    ('做个放松练习', '4-7-8'),
    ('身体扫描一下', 'body_scan'),
    ('正念呼吸', 'breathing'),
    ('渐进肌肉放松', 'pmr'),
    ('盒式呼吸', 'box_breathing'),
    ('缩唇呼吸', 'pursed_lip'),
    ('自律训练', 'autogenic'),
    ('安全岛', 'safe_place'),
    ('云端漂浮', 'cloud_float'),
    ('声音浴', 'sound_bath'),
    ('做认知卸荷', 'cognitive_unloading'),
    ('矛盾意向', 'paradoxical_intention'),
    ('刺激控制', 'stimulus_control'),
    ('睡眠卫生', 'sleep_hygiene'),
    ('认知重构', 'cognitive_restructuring'),
    ('红酒刺激胃酸', None),
]

ok = 0
for msg, expected in tests:
    result = handle_chat({'openid':'test','message':msg,'history':[],'persona':'sweet'})
    actual = result.get('action')
    if actual == expected:
        ok += 1
        print(f'  OK  {msg}')
    else:
        print(f'  FAIL {msg} -> {actual} (expected {expected})')

print(f'\n{ok}/{len(tests)} passing')
