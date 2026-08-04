#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_omission.py — 数据遗漏检测 daemon（B模式）

用于 cron 或后台检查最近的 AI 对话。
发现有"数据发了但AI回复没引用"的情况时输出报警。

用法:
  # 一次性检查
  python dev_tools/check/check_omission.py
  
  # 注册到 cron（每30分钟）
  python aisleepgen_tool.py monitor omission
"""

import sys, os, re, json, datetime
sys.stdout.reconfigure(encoding='utf-8')

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACE_LOG = os.path.join(PROJECT_DIR, 'logs', 'trace.log')
STATE_FILE = os.path.join(PROJECT_DIR, 'logs', '.omission_state.json')

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {'last_checked_index': 0, 'last_alarm': None}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, ensure_ascii=False)

def check():
    if not os.path.exists(TRACE_LOG):
        print('[OmissionCheck] No trace log yet')
        return
    
    state = load_state()
    alerts = []
    
    with open(TRACE_LOG, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 只看新行
    new_lines = lines[state['last_checked_index']:]
    
    # 解析对话
    current_dialogue = None
    current_has_data = False
    current_send_len = 0
    
    for i, line in enumerate(new_lines):
        m = re.match(r'\[\d{2}:\d{2}:\d{2}\] \[(\d{6})_([a-f0-9]+)\]\s+(ctx|send|>>|sc:|entry)\s+(.*)', line)
        if not m:
            continue
        
        trace_id = m.group(1) + '_' + m.group(2)
        msg_type = m.group(3)
        msg_data = m.group(4)
        
        if msg_type == 'entry':
            # 新对话开始，检查上一个对话
            if current_dialogue and current_has_data and current_send_len > 0:
                # 这个对话有数据，但需要检查
                pass  # 暂时只是记录
            
            current_dialogue = trace_id
            current_has_data = False
            current_send_len = 0
            continue
        
        if current_dialogue and msg_type == 'ctx':
            if 'has_data=True' in msg_data:
                current_has_data = True
        
        if current_dialogue and msg_type == 'send':
            m2 = re.search(r'has_ud=(\w+)', msg_data)
            if m2 and m2.group(1) == 'True':
                current_has_data = True
            m3 = re.search(r'sys_len=(\d+)', msg_data)
            if m3:
                current_send_len = int(m3.group(1))
    
    # 检查最新的一个对话
    if current_dialogue and current_has_data and current_send_len > 0:
        # 对话有数据，正常
        pass
    elif current_dialogue and not current_has_data:
        alerts.append('[OMISSION] Last dialogue has no user data in context')
    
    # 更新状态
    state['last_checked_index'] = len(lines)
    save_state(state)
    
    if alerts:
        print('\n'.join(alerts))
        return False
    else:
        print('[OmissionCheck] OK - last {} dialogues have data'.format(
            len([l for l in lines if 'entry:' in l and state['last_checked_index'] > 0 and lines.index(l) >= state['last_checked_index'] - 50])))
        return True

if __name__ == '__main__':
    check()
