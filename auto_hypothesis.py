#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_hypothesis.py — 反事实假说生成器 v1

"从尸体里挖种子"。

职责：每周/每触发，扫描过去所有实验的失败记录，
归纳系统在哪些维度上输了、为什么输、
然后生成3个反事实假说注入实验队列。

反事实假说类型：
  1. 反向验证：先前rollback的参数，尝试反方向调
  2. 交叉补偿：如果A参数上调导致某指标下降，尝试A上调+B下调同时
  3. 跨维度共振：两个不相关维度同时调，看交互效应

不是收割实验——是从尸体里挖下一代问题的种子。
"""

import json, os, time, sys, math
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\AISleepGen_Optimized'
EXPT_DIR = os.path.join(BASE, 'data', 'experiments')
FB_PATH = os.path.join(BASE, 'data', 'feedback.json')
CAL_PATH = os.path.join(EXPT_DIR, 'calibration.json')
BRIDGE_PATH = r'D:\super_frontier_radar\frontier_data\_for_xiaotiantian_bridge.json'
HYPOTHESIS_PATH = os.path.join(EXPT_DIR, '_auto_hypotheses.json')

# ═══ 参数相似度映射：一个参数被rollback过，它的"兄弟姐妹"也可能有问题 ═══
KNOB_FAMILIES = {
    '_regression_coefs.pain_flag': ['_regression_coefs.pain_penalty', 'pain_penalty_base'],
    '_regression_coefs.latency': ['_regression_coefs.duration', '_regression_coefs.awake'],
    '_regression_coefs.awake': ['_regression_coefs.latency', '_regression_coefs.duration'],
    '_regression_coefs.duration': ['_regression_coefs.latency', '_regression_coefs.awake'],
    '_regression_coefs.stress': ['_regression_coefs.wm_score'],
    '_regression_coefs.wm_score': ['_regression_coefs.stress', '_regression_coefs.rating_mood'],
    'avg_user_rating': ['happy_ratio', 'avg_wm_at_feedback'],
}

# ═══ 已知的参数安全范围 ═══
SAFE_RANGES = {
    'pain_penalty_base': (0.05, 0.25),
    'pain_flag': (-0.5, -0.1),
    'latency': (-0.1, 0.05),
    'duration': (-0.05, 0.1),
    'awake': (-0.3, -0.05),
    'stress': (-0.1, 0.1),
    'wm_score': (-0.1, 0.05),
    'health': (60, 120),
    'health_score': (30, 60),
    'samples': (100, 200),
    'avg_user_rating': (2.5, 5.0),
    'happy_ratio': (0.3, 0.8),
    'avg_wm_at_feedback': (40, 80),
    'split_ratio': (30, 70),
}


def _log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] [Hypothesis] {msg}')


def _load_calibration():
    try:
        with open(CAL_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}


def _get_experiment_deaths():
    """收集所有死亡实验"""
    expts = [f for f in os.listdir(EXPT_DIR) 
             if f.endswith('.json') and not f.startswith('_')]
    
    dead = []
    for fn in expts:
        fp = os.path.join(EXPT_DIR, fn)
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                d = json.load(f)
            st = d.get('status', d.get('_status', '?'))
            if st in ('rolled_back', 'abandoned', 'finished_inconclusive'):
                dead.append({
                    'fn': fn,
                    'name': d.get('name', '?'),
                    'knob': d.get('knob_key', '?'),
                    'old_val': d.get('old_value'),
                    'new_val': d.get('new_value'),
                    'created': d.get('created_at', d.get('started_at', '')),
                    'reason': d.get('rollback_reason', d.get('reap_reason', '')),
                })
        except:
            pass
    return dead


def _get_alive_run_params():
    """收集当前正在试验的参数组"""
    expts = [f for f in os.listdir(EXPT_DIR) 
             if f.endswith('.json') and not f.startswith('_')]
    
    alive = []
    for fn in expts:
        fp = os.path.join(EXPT_DIR, fn)
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                d = json.load(f)
            st = d.get('status', d.get('_status', '?'))
            if st in ('running', 'suspended'):
                alive.append({
                    'knob': d.get('knob_key', '?'),
                    'old_val': d.get('old_value'),
                    'new_val': d.get('new_value'),
                })
        except:
            pass
    return alive


def _knob_short_name(knob):
    """从全路径提取短名（如 calibration._regression_coefs.pain_flag → pain_flag）"""
    return knob.split('.')[-1] if '.' in knob else knob


def _should_try_counter(dead_experiments, knob_short):
    """
    判断一个参数是否值得尝试反方向
    规则：被rollback过 >= 1 次 & 当前无正在运行的实验
    """
    dead_count = sum(1 for d in dead_experiments 
                     if _knob_short_name(d['knob']) == knob_short)
    return dead_count


def _safe_clamp(knob_short, val):
    """把数值钳制在安全范围内"""
    if knob_short in SAFE_RANGES:
        lo, hi = SAFE_RANGES[knob_short]
        return max(lo, min(hi, val))
    return max(0.01, min(val, 1000))


def generate_hypotheses():
    """
    生成反事实假说
    
    返回: 假说列表
    """
    deaths = _get_experiment_deaths()
    alive = _get_alive_run_params()
    cal = _load_calibration()
    
    if not deaths:
        _log('无死亡实验数据，无法生成假说')
        return []
    
    _log(f'扫描 {len(deaths)} 个死亡实验, {len(alive)} 个存活实验')
    
    # 收集被kill的参数维度
    killed_knobs = set()
    for d in deaths:
        killed_knobs.add(d['knob'])
    
    hypotheses = []
    used_knobs = set(a['knob'] for a in alive)
    
    # ═══ 类型1: 反向验证 ═══
    # 对每个被kill过的参数，尝试反方向
    for knob in sorted(killed_knobs):
        short = _knob_short_name(knob)
        
        # 找到这个参数的所有死亡记录
        this_deaths = [d for d in deaths if d['knob'] == knob]
        if not this_deaths:
            continue
        
        # 检查当前是否已在running
        if knob in used_knobs:
            continue
        
        # 查看最后一次死亡的方向
        last_death = this_deaths[-1]
        old_val = last_death['old_val']
        new_val = last_death['new_val']
        
        if old_val is None or new_val is None:
            continue
        
        # 反方向：如果之前是下调整，建议上调整；反之亦然
        direction = 'up' if new_val < old_val else 'down'
        factor = 0.5  # 反力臂：只调一半幅度
        diff = abs(new_val - old_val or 0.01) * factor
        
        if direction == 'up':
            counter_val = old_val + diff
        else:
            counter_val = old_val - diff
        
        counter_val = _safe_clamp(short, counter_val)
        if counter_val == old_val:
            continue  # 被安全范围钳制到原地
        
        hypothesis = {
            'type': 'reverse_validate',
            'name': f'counter_{short}_{time.strftime("%m%d")}',
            'knob_key': knob,
            'old_value': old_val,
            'proposed_value': round(counter_val, 4),
            'direction': direction,
            'rationale': f'前次{short}从{old_val}调至{new_val}后rollback，怀疑方向错误，尝试反方向调至{round(counter_val,4)}',
            'confidence': min(0.5, 0.3 + 0.1 * _should_try_counter(deaths, short)),
        }
        hypotheses.append(hypothesis)
    
    # ═══ 类型2: 交叉补偿 ═══
    # 如果参数A上调导致某指标恶化，尝试A上调+B下调（补偿）
    death_by_knob = defaultdict(list)
    for d in deaths:
        death_by_knob[d['knob']].append(d)
    
    for knob, this_deaths in death_by_knob.items():
        short = _knob_short_name(knob)
        
        if knob in used_knobs:
            continue
        
        # 找到该参数的"兄弟姐妹"
        family = []
        for family_key, members in KNOB_FAMILIES.items():
            if short in members or family_key == short:
                family = members
                break
        
        if not family:
            continue
        
        # 对每个兄弟姐妹，尝试交叉
        for member in family:
            if member == short:
                continue
            member_full = None
            for d in deaths:
                if member in d['knob']:
                    member_full = d['knob']
                    break
            if not member_full:
                # 尝试从校准文件找
                for cal_key in cal:
                    if member in cal_key and cal_key not in used_knobs:
                        member_full = cal_key
                        break
            
            if not member_full or member_full in used_knobs:
                continue
            
            base_val = cal.get(member_full, 0.1)
            current_death = this_deaths[-1]
            old_val = current_death['old_val'] or base_val
            
            # 补偿方向：主参数上调时，补偿参数下调（假设负相关）
            if new_val := current_death['new_val']:
                comp_direction = 'down' if new_val > (old_val or 0) else 'up'
                comp_factor = 0.3
                comp_diff = abs((new_val if new_val else old_val) - old_val) * comp_factor
                comp_val = base_val - comp_diff if comp_direction == 'down' else base_val + comp_diff
                comp_val = _safe_clamp(member, comp_val)
                
                hypothesis = {
                    'type': 'cross_compensation',
                    'name': f'cross_{short}_{member}_{time.strftime("%m%d")}',
                    'knob_key': knob,
                    'old_value': old_val,
                    'proposed_value': round(new_val, 4),  # 主参数保持原方向
                    'compensate_knob': member_full,
                    'compensate_old': base_val,
                    'compensate_value': round(comp_val, 4),
                    'direction': 'cross',
                    'rationale': f'{short}调整时rollback，怀疑需{member}同步{comp_direction}补偿至{round(comp_val,4)}',
                    'confidence': 0.35,
                }
                hypotheses.append(hypothesis)
    
    # ═══ 类型3: 跨维度共振 ═══
    # 选取两个不同家族的参数，同时微调（看交互效应）
    if len(death_by_knob) >= 2:
        knob_names = list(death_by_knob.keys())
        for i in range(min(3, len(knob_names) - 1)):
            k1 = knob_names[i]
            k2 = knob_names[i + 1]
            
            if k1 in used_knobs or k2 in used_knobs:
                continue
            
            s1 = _knob_short_name(k1)
            s2 = _knob_short_name(k2)
            
            d1 = death_by_knob[k1][-1]
            d2 = death_by_knob[k2][-1]
            
            o1 = d1.get('old_val') or cal.get(k1, 0.1)
            o2 = d2.get('old_val') or cal.get(k2, 0.1)
            
            v1 = _safe_clamp(s1, o1 * 1.1)
            v2 = _safe_clamp(s2, o2 * 0.95)
            
            hypothesis = {
                'type': 'resonance',
                'name': f'reso_{s1}_{s2}_{time.strftime("%m%d")}',
                'knob_key': k1,
                'old_value': o1,
                'proposed_value': round(v1, 4),
                'co_knob': k2,
                'co_old': o2,
                'co_value': round(v2, 4),
                'rationale': f'同时微调{s1}(+10%)和{s2}(-5%)，看跨维度交互效应',
                'confidence': 0.25,
            }
            hypotheses.append(hypothesis)
    
    _log(f'生成 {len(hypotheses)} 个反事实假说')
    for h in hypotheses:
        _log(f'  [{h["type"]}] {h["name"]} → {_knob_short_name(h["knob_key"])}: {h.get("rationale","")[:80]}')
    
    return hypotheses


def inject_to_bridge(hypotheses):
    """写入bridge供实验平台消费"""
    if not hypotheses:
        return
    
    bridge = {
        'source': 'auto_hypothesis',
        'timestamp': time.time(),
        'hypotheses': hypotheses,
    }
    
    os.makedirs(os.path.dirname(HYPOTHESIS_PATH), exist_ok=True)
    with open(HYPOTHESIS_PATH, 'w', encoding='utf-8') as f:
        json.dump(bridge, f, ensure_ascii=False, indent=2)
    
    # 也写入实验bridge目录
    if os.path.exists(os.path.dirname(BRIDGE_PATH)):
        with open(BRIDGE_PATH.replace('for_xiaotiantian', 'for_experiment_hypotheses'), 'w', encoding='utf-8') as f:
            json.dump(bridge, f, ensure_ascii=False, indent=2)
    
    _log(f'写入 {len(hypotheses)} 个假说到bridge')
    
    # 将假说作为实验提案写入 experiments 目录
    # 高置信度的(>=0.4) 自动创建实验
    for h in hypotheses:
        if h.get('confidence', 0) >= 0.4:
            exp = {
                'experiment_id': f'hyp_{h["name"]}_{int(time.time())}',
                'name': h['name'],
                'knob_key': h['knob_key'],
                'old_value': h['old_value'],
                'new_value': h['proposed_value'],
                'hypothesis_rationale': h['rationale'],
                'min_days': 7,
                'min_users_per_group': 3,
                'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'status': 'pending',
            }
            exp_path = os.path.join(EXPT_DIR, f'hyp_{h["name"]}_{int(time.time())}.json')
            with open(exp_path, 'w', encoding='utf-8') as f:
                json.dump(exp, f, ensure_ascii=False, indent=2)
            _log(f'  自动创建实验: {exp["name"]}')
    
    return bridge


if __name__ == '__main__':
    print('反事实假说生成器 v1')
    print('=' * 40)
    
    hyps = generate_hypotheses()
    if hyps:
        inject_to_bridge(hyps)
    else:
        print('(无假说生成)')
    
    print(f'\n✅ done')
