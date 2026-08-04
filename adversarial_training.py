#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adversarial_training.py — 本能对抗训练（魔鬼实验）v1

"跟自己打架。"

设计原理：系统定期 spawn 故意反向的参数组。
不是等待失败发生，是主动安排失败—反应—适应的循环。

生成规则：
  1. 从当前 running 实验中选一个 "宿主实验"
  2. 对宿主参数的相近维度，生成反向实验（对抗实验）
  3. 对抗实验不会影响真实用户——它跑的是仿真数据
  4. 观察系统在没有人为干预下，能否自动补偿

这是"反事实假说生成器"的镜像：它不挖尸体，而是主动制造尸体。
"""

import json, os, time, sys, math, random

sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\AISleepGen_Optimized'
EXPT_DIR = os.path.join(BASE, 'data', 'experiments')
CAL_PATH = os.path.join(BASE, 'data', 'calibration.json')

# ═══ 对抗参数对 ═══
# 宿主参数 → 对抗参数（反向方向，幅度比例）
ADVERSARIAL_PAIRS = [
    # 宿主knob_contains → (对抗knob_contains, 对抗方向, 幅度比)
    ('latency', ('awake', 'reverse', 0.7)),        # latency上调→awake下调70%
    ('awake', ('latency', 'reverse', 0.7)),         # awake上调→latency下调70%
    ('pain_flag', ('pain_penalty', 'reverse', 0.5)), # pain_flag上调→pain_penalty下调50%
    ('duration', ('latency', 'reverse', 0.3)),      # duration上调→latency下调30%
    ('health', ('health_score', 'same', 0.5)),       # health上调→health_score也上调50%
    ('avg_user_rating', ('happy_ratio', 'same', 0.8)), # rating上调→happy_ratio上调80%
    ('samples', ('count', 'same', 0.6)),              # samples上调→count上调60%
    ('stress', ('wm_score', 'reverse', 0.6)),         # stress上调→wm_score下调60%
    ('wm_score', ('stress', 'reverse', 0.6)),         # wm_score下调→stress上调60%
]

ANOMALY_PAIRS = [
    # 毫无关联的参数对——制造"混乱信号"
    (('latency', 'health'), 0.3),
    (('pain_flag', 'happy_ratio'), 0.2),
    (('samples', 'wm_score'), 0.2),
]


def _log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] [Adversarial] {msg}')


def _load_calibration():
    try:
        with open(CAL_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}


def _get_running_exps():
    """获取当前running的实验"""
    expts = [f for f in os.listdir(EXPT_DIR) 
             if f.endswith('.json') and not f.startswith('_')]
    
    running = []
    for fn in expts:
        fp = os.path.join(EXPT_DIR, fn)
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                d = json.load(f)
            st = d.get('status', d.get('_status', '?'))
            if st == 'running':
                running.append({
                    'fn': fn,
                    'name': d.get('name', '?'),
                    'knob': d.get('knob_key', '?'),
                    'old_val': d.get('old_value'),
                    'new_val': d.get('new_value'),
                    'created': d.get('created_at', ''),
                })
        except:
            pass
    return running


def _knob_short(knob):
    return knob.split('.')[-1] if '.' in knob else knob


def _find_adversarial(host_knob, old_val, new_val, cal):
    """为宿主实验生成对抗实验参数"""
    short = _knob_short(host_knob)
    
    for host_pattern, (adv_pattern, direction, ratio) in ADVERSARIAL_PAIRS:
        if host_pattern in short:
            # 找对抗参数在当前校准中的值
            adv_key = None
            for cal_key in cal:
                if adv_pattern in cal_key:
                    adv_key = cal_key
                    break
            if not adv_key:
                continue
            
            base_val = cal.get(adv_key, 0.1)
            if base_val is None:
                base_val = 0.1
            
            # 计算变化幅度
            old_v = old_val if old_val else base_val
            if new_val:
                diff = new_val - old_v
            else:
                diff = base_val * 0.1  # 默认±10%
            
            # 对抗幅度
            adv_diff = diff * ratio
            
            if direction == 'reverse':
                adv_new = base_val - adv_diff
            else:  # 'same'
                adv_new = base_val + adv_diff
            
            # 安全范围
            adv_new = max(-1.0, min(1.0, adv_new))
            
            return {
                'knob_key': adv_key,
                'old_value': base_val,
                'new_value': round(adv_new, 4),
                'type': 'adversarial',
                'rationale': f'对抗 {short}({round(diff,4)}) → {adv_pattern}({direction}×{ratio}={round(adv_diff,4)})',
            }
    
    return None


def generate_adversarials():
    """
    为主实验生成对抗组
    
    返回: 对抗实验列表
    """
    running = _get_running_exps()
    cal = _load_calibration()
    
    if not running:
        _log('无running实验，跳过对抗生成')
        return []
    
    _log(f'扫描 {len(running)} 个running实验')
    
    adversarials = []
    
    # 为每个running实验生成对抗组
    for exp in running:
        adv = _find_adversarial(exp['knob'], exp['old_val'], exp['new_val'], cal)
        if adv:
            adv['host_name'] = exp['name']
            adv['host_knob'] = exp['knob']
            adversarials.append(adv)
    
    # 去重（同一个对抗knob可能被多个宿主提出）
    seen_knobs = set()
    unique = []
    for a in adversarials:
        if a['knob_key'] not in seen_knobs:
            seen_knobs.add(a['knob_key'])
            unique.append(a)
    
    # 添加1-2个"异常对"（完全无关的参数）
    if len(running) >= 2 and random.random() < 0.5:
        exp_sample = random.sample(running, 2)
        for (p1, p2), strength in ANOMALY_PAIRS:
            k1, k2 = None, None
            for cal_key in cal:
                if p1 in cal_key: k1 = cal_key
                if p2 in cal_key: k2 = cal_key
            if k1 and k2 and k1 != k2:
                v1 = cal.get(k1, 0.5)
                v2 = cal.get(k2, 0.5)
                anomaly = {
                    'knob_key': k1,
                    'old_value': v1,
                    'new_value': round(v1 * (1 + strength * random.choice([-1, 1])), 4),
                    'co_knob': k2,
                    'co_value': round(v2 * (1 + strength * random.uniform(-0.5, 0.5)), 4),
                    'type': 'anomaly',
                    'rationale': f'混沌信号: {p1}({k1})和{p2}({k2})同时微调 ({strength})',
                    'host_name': 'none',
                }
                unique.append(anomaly)
                break
    
    _log(f'生成 {len(unique)} 个对抗/异常实验')
    for a in unique:
        short = _knob_short(a.get('knob_key', '?'))
        if a.get('type') == 'adversarial':
            _log(f'  ⚔️ 对抗: host={a.get("host_name","?")} → {short}: {a["old_value"]}→{a["new_value"]} ({a.get("rationale","")[:60]})')
        else:
            _log(f'  🌪️ 异常: {short}/{_knob_short(a.get("co_knob",""))}: 混沌信号')
    
    return unique


def write_adversarial_experiments(adversarials):
    """将对抗实验写入实验目录"""
    if not adversarials:
        return
    
    # 查看最近是否已经创建过类似实验（去重）
    existing = [f for f in os.listdir(EXPT_DIR) if f.startswith('adv_') or f.startswith('ano_')]
    
    for a in adversarials:
        ts = int(time.time())
        short = _knob_short(a.get('knob_key', '?'))
        
        if a['type'] == 'adversarial':
            exp_name = f'adv_{short}_{ts}'
        else:
            exp_name = f'ano_{short}_{ts}'
        
        # 防止重复
        if any(exp_name in f for f in existing):
            _log(f'  跳过: {exp_name} 已存在')
            continue
        
        exp = {
            'experiment_id': exp_name,
            'name': exp_name,
            'knob_key': a['knob_key'],
            'old_value': a['old_value'],
            'new_value': a['new_value'],
            'type': a['type'],
            'rationale': a['rationale'],
            'host_name': a.get('host_name', ''),
            'min_days': 14,
            'min_users_per_group': 2,
            'simulated': True,
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'status': 'running',
        }
        
        fp = os.path.join(EXPT_DIR, f'{exp_name}.json')
        with open(fp, 'w', encoding='utf-8') as f:
            json.dump(exp, f, ensure_ascii=False, indent=2)
        
        _log(f'  ✅ 创建对抗实验: {exp_name}')
    
    _log(f'共创建 {len(adversarials)} 个对抗/异常实验')


if __name__ == '__main__':
    print('本能对抗训练 v1')
    print('=' * 40)
    advs = generate_adversarials()
    if advs:
        write_adversarial_experiments(advs)
    print(f'\n✅ 完成')
