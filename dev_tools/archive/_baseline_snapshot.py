# -*- coding: utf-8 -*-
"""当前系统基线快照（停手前记录）"""
import json, os, sys, time
sys.stdout.reconfigure(encoding='utf-8')

BASE = r'D:\AISleepGen_Optimized'
EXPT_DIR = os.path.join(BASE, 'data', 'experiments')
FB_PATH = os.path.join(BASE, 'data', 'feedback.json')
CAL_PATH = os.path.join(BASE, 'data', 'calibration.json')
SIGNAL_PATH = os.path.join(BASE, 'data', 'implicit_signals.json')
ACTION_PATH = os.path.join(BASE, 'data', '_prioritized_action.json')

def safe_open(p):
    try: return json.load(open(p, 'r', encoding='utf-8'))
    except: return None

ts = time.strftime('%Y-%m-%d %H:%M:%S')
print(f'=== 基线快照 {ts} ===')

# 实验统计
expts = [f for f in os.listdir(EXPT_DIR) if f.endswith('.json') and not f.startswith('_')]
statuses = {}
for fn in expts:
    d = safe_open(os.path.join(EXPT_DIR, fn))
    if d:
        s = d.get('status', '?')
        statuses.setdefault(s, 0)
        statuses[s] += 1
print(f'\n实验: {len(expts)} 个')
for s, c in sorted(statuses.items()):
    print(f'  {s}: {c}')

# feedback统计
fbs = safe_open(FB_PATH)
real = [fb for fb in fbs if not str(fb.get('openid','')).startswith('virt_') and fb.get('openid','') not in ('reg_test','test')]
virt = [fb for fb in fbs if str(fb.get('openid','')).startswith('virt_')]
print(f'\nfeedback: {len(fbs)} 条 (真实{len(real)} + 虚拟{len(virt)})')

# 双脑状态
brain_expts = [d for d in [safe_open(os.path.join(EXPT_DIR,f)) for f in expts] if d and d.get('source')=='dual_brain']
print(f'双脑实验: {len(brain_expts)} 个')
for b in brain_expts:
    print(f'  {b.get("brain","?")}/{b.get("tag","?")}: {b.get("knob_key","?")} {b.get("direction","?")} {b.get("status","?")}')

# 对抗实验
adv_expts = [d for d in [safe_open(os.path.join(EXPT_DIR,f)) for f in expts] if d and d.get('source')=='adversarial']
print(f'对抗实验: {len(adv_expts)} 个')

# 信号
sig = safe_open(SIGNAL_PATH)
if sig:
    print(f'\n至尊宝信号: mode={sig.get("current_mode","?")} creativity={sig.get("creativity","?")} challenge={sig.get("challenge_level","?")}')

# 压缩器建议
act = safe_open(ACTION_PATH)
if act:
    print(f'\n压缩器建议: {act.get("action","?")} (conf={act.get("action_confidence","?")})')

print(f'\n基线记录完成。下一轮观察：12小时后。')
