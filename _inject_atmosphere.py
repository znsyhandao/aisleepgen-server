# -*- coding: utf-8 -*-
"""Inject ambient atmosphere into meditation-plan response."""
import sys, json, re
sys.path.insert(0, r'D:\AISleepGen_Optimized')

with open('dp_router.py', 'r', encoding='utf-8') as f:
    c = f.read()

# The return dict starts with:
#     return {
#         'protocol': protocol,
#         ... (5 fields)
#     }

# Find the exact return block for handle_meditation_plan
func_start = c.find('def handle_meditation_plan')
ret_start = c.find("return {", func_start)
ret_end = c.find("\n}\n", ret_start) + 4  # include \n}\n

ret_block = c[ret_start:ret_end]
print(f'Return block: {ret_block[:200]}')
print(f'Return block length: {len(ret_block)}')

# The block has 5 fields, we want to add ambient_atmosphere as 6th
# Find the last field before closing }
# Look for the pattern:     }
lines = ret_block.split('\n')
print(f'Return lines: {len(lines)}')
for i, line in enumerate(lines):
    print(f'  {i}: {line[:80]}')

# The insert point is right before the "    }"
# In the original it's: "        '_safe_constraint': 'xxx',\n    }"
# We add after _safe_constraint line

close_idx = ret_block.rfind("    }")
ambient_block = """        '_safe_constraint': '安全协议，不做自由生成',
        # ===== 场景氛围参数（前端用于渲染背景/灯光/色调） =====
        'ambient_atmosphere': {
            'name': '4-7-8 呼吸法',
            'bg_top': '#0a0a2e',
            'bg_mid': '#12125a',
            'bg_bot': '#1a0a3a',
            'text': '#e8e0ff',
            'accent': '#7c4dff',
            'vibe': 'calm',
        }"""

# Find the current last field line and replace it
old_end = """        '_safe_constraint': '安全协议，不做自由生成',
    }"""

if old_end in ret_block:
    new_ret = ret_block.replace(old_end, ambient_block)
    c = c.replace(ret_block, new_ret)
    print(f'Replaced return block: {len(ret_block)} -> {len(new_ret)}')
    
    # Now replace the static ambient with dynamic protocol-based values
    # Find the ambient we just inserted and make it dynamic
    c = c.replace(ambient_block, """        '_safe_constraint': '安全协议，不做自由生成',
        # ===== 场景氛围参数 =====
        'ambient_atmosphere': _get_atmosphere(protocol, p)""")
    
    # Add the _get_atmosphere function
    insert_pos = ret_end
    # Find position after the closing }));
    
    func = """

def _get_atmosphere(protocol, p):
    atmosphere_map = {
        '4-7-8': {'name': '4-7-8 呼吸法', 'bg_top': '#0a0a2e', 'bg_mid': '#12125a', 'bg_bot': '#1a0a3a', 'text': '#e8e0ff', 'accent': '#7c4dff', 'vibe': 'calm'},
        'box_breathing': {'name': '盒式呼吸', 'bg_top': '#0a1628', 'bg_mid': '#0f2847', 'bg_bot': '#0a1a2e', 'text': '#e0f0ff', 'accent': '#448aff', 'vibe': 'focus'},
        'breathing': {'name': '正念呼吸', 'bg_top': '#0a1a1a', 'bg_mid': '#0f2a1f', 'bg_bot': '#0a1a2e', 'text': '#e0ffe8', 'accent': '#4caf50', 'vibe': 'natural'},
        'pursed_lip': {'name': '缩唇呼吸', 'bg_top': '#080818', 'bg_mid': '#1a1040', 'bg_bot': '#0d0d2b', 'text': '#e8e0ff', 'accent': '#9c27b0', 'vibe': 'soft'},
        'body_scan': {'name': '身体扫描', 'bg_top': '#1a120a', 'bg_mid': '#2a1a0a', 'bg_bot': '#1a1008', 'text': '#ffe8d0', 'accent': '#ff9800', 'vibe': 'warm'},
        'pmr': {'name': '渐进肌肉放松', 'bg_top': '#1a1008', 'bg_mid': '#2a1808', 'bg_bot': '#1a0e06', 'text': '#ffead0', 'accent': '#e65100', 'vibe': 'grounding'},
        'autogenic': {'name': '自律训练', 'bg_top': '#1a0e08', 'bg_mid': '#2a1410', 'bg_bot': '#1a0c08', 'text': '#ffded0', 'accent': '#d50000', 'vibe': 'womb'},
        'safe_place': {'name': '安全岛', 'bg_top': '#1a1408', 'bg_mid': '#2a1c0a', 'bg_bot': '#1a1206', 'text': '#fff0d0', 'accent': '#ffab00', 'vibe': 'safe'},
        'cloud_float': {'name': '云端漂浮', 'bg_top': '#0a1428', 'bg_mid': '#1a2840', 'bg_bot': '#0a1a30', 'text': '#d0f0ff', 'accent': '#40c4ff', 'vibe': 'floating'},
        'sound_bath': {'name': '声音浴', 'bg_top': '#0a0820', 'bg_mid': '#1a1048', 'bg_bot': '#0a0830', 'text': '#e0d8ff', 'accent': '#7c4dff', 'vibe': 'expansion'},
        'cognitive_unloading': {'name': '担忧日记', 'bg_top': '#14100e', 'bg_mid': '#1e1814', 'bg_bot': '#14100c', 'text': '#e8e0d8', 'accent': '#a1887f', 'vibe': 'release'},
        'paradoxical_intention': {'name': '努力清醒', 'bg_top': '#0e1018', 'bg_mid': '#181e2e', 'bg_bot': '#0e101a', 'text': '#d8e0f0', 'accent': '#78909c', 'vibe': 'surrender'},
        'stimulus_control': {'name': '刺激控制', 'bg_top': '#0e1410', 'bg_mid': '#182418', 'bg_bot': '#0e140e', 'text': '#d8f0e0', 'accent': '#689f63', 'vibe': 'structure'},
        'sleep_hygiene': {'name': '睡前检查', 'bg_top': '#120e14', 'bg_mid': '#20182a', 'bg_bot': '#100e18', 'text': '#e0d8f0', 'accent': '#9c8ab5', 'vibe': 'preparation'},
        'cognitive_restructuring': {'name': '挑战坏想法', 'bg_top': '#14100e', 'bg_mid': '#221c18', 'bg_bot': '#14100c', 'text': '#f0e8d8', 'accent': '#bcaaa4', 'vibe': 'clarity'},
    }
    atm = atmosphere_map.get(protocol, atmosphere_map['4-7-8'])
    if isinstance(p, dict):
        atm['name'] = p.get('name', atm['name'])
    return atm

"""
    
    # Insert the function right after handle_meditation_plan ends
    # Find where the function ends (next @route or def)
    next_def = c.find('\n@route(', ret_end)
    if next_def > 0:
        c = c[:ret_end + 1] + func + c[next_def:]
        print(f'Inserted _get_atmosphere function ({len(func)} chars)')
    
    import py_compile
    try:
        py_compile.compile('dp_router.py', doraise=True)
        print('COMPILATION: OK')
    except py_compile.PyCompileError as e:
        print(f'COMPILE ERROR: {e}')
else:
    print(f'OLD END NOT FOUND in ret_block')
    print(f'Last 50 chars of ret_block: {ret_block[-50:]}')
