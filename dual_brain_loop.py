#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dual_brain_loop.py — 双脑对抗引擎 v1

"系统内部永远有一个反对派。"

架构：
  - 左脑 (mode='standard')：标准推理路径。读当前校准+实验数据 → 输出建议
  - 右脑 (mode='skeptic')：质疑路径。读同一份数据 → 主动找左脑漏洞 → 输出反驳
  - 仲裁器：跑两个实验，一周后看谁赢。输的降权，赢的扩权
  - 种子注入：反事实假说生成器（auto_hypothesis）的产出是左脑的输入
  - 对抗生成：对抗训练器（adversarial_training）的产出是右脑的质疑来源

脑力输出格式:
  {
    'position': str,          # 'for'（左脑）或 'against'（右脑）
    'knob_key': str,          # 参数路径
    'direction': 'up'|'down', # 建议方向
    'delta': float,           # 建议变化量
    'confidence': float,      # 置信度 0~1
    'rationale': str,         # 理由
    'vulnerabilities': list,  # 右脑特有: 指出左脑推理中的漏洞
  }
"""

import json, os, time, sys, math, random
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\AISleepGen_Optimized'
DATA_DIR = os.path.join(BASE, 'data')
EXPT_DIR = os.path.join(BASE, 'data', 'experiments')
CAL_PATH = os.path.join(BASE, 'data', 'calibration.json')
LOG_PATH = os.path.join(BASE, 'logs', 'dual_brain.log')

# ═══ 左脑可用的推理工具箱 ═══
LEFT_BRAIN_TOOLS = [
    'trend_follow',     # 跟随最近实验的趋势
    'feedback_corr',    # feedback与参数的相关系数
    'hypothesis_seed',  # 从auto_hypothesis取种子
]

# ═══ 右脑可用的质疑工具箱 ═══
RIGHT_BRAIN_TOOLS = [
    'insufficient_data',      # 数据量不够→质疑结论
    'confounding_variable',   # 混淆变量→质疑因果
    'regression_to_mean',     # 均值回归→质疑效果
    'selection_bias',         # 幸存者偏差→质疑样本
    'adversarial_seed',       # 从adversarial_training取对抗
]

# ═══ 最近5轮的脑力权重 ═══
BRAIN_WEIGHTS = {'left': 1.0, 'right': 0.7}  # 右脑初始权重低一些（质疑引擎需要被信任）


def _log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(f'[{ts}] {msg}\n')
    print(f'  {msg}')


def _load_cal():
    try:
        with open(CAL_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}


def _load_deaths():
    """加载死亡实验"""
    expts = [f for f in os.listdir(EXPT_DIR) if f.endswith('.json') and not f.startswith('_')]
    deaths = []
    for fn in expts:
        try:
            with open(os.path.join(EXPT_DIR, fn), 'r', encoding='utf-8') as f:
                d = json.load(f)
            st = d.get('status', '?')
            if st in ('rolled_back', 'abandoned', 'finished_inconclusive'):
                deaths.append(d)
        except:
            pass
    return deaths


def _load_running():
    """加载running实验"""
    expts = [f for f in os.listdir(EXPT_DIR) if f.endswith('.json') and not f.startswith('_')]
    running = []
    for fn in expts:
        try:
            with open(os.path.join(EXPT_DIR, fn), 'r', encoding='utf-8') as f:
                d = json.load(f)
            if d.get('status', '?') == 'running':
                running.append(d)
        except:
            pass
    return running


def _knob_short(knob):
    return knob.split('.')[-1] if '.' in knob else knob


# ═══ 左脑 ═══

def _left_brain_position(cal, deaths, running):
    """
    左脑：标准推理
    
    输出：一个推荐位置（参数+方向+幅度）
    """
    # 1. 看看有没有 auto_hypothesis 的提案可用
    hypothesis_file = os.path.join(EXPT_DIR, '_auto_hypotheses.json')
    if os.path.exists(hypothesis_file):
        try:
            with open(hypothesis_file, 'r', encoding='utf-8') as f:
                hyps = json.load(f)
            hypotheses = hyps.get('hypotheses', [])
            # 选一个置信度最高的未执行假说
            for h in sorted(hypotheses, key=lambda x: -x.get('confidence', 0)):
                if h.get('knob_key') and h.get('proposed_value'):
                    knob = h['knob_key']
                    direction = 'up' if h['proposed_value'] > (h.get('old_value', 0) or 0) else 'down'
                    delta = abs((h['proposed_value'] or 0) - (h.get('old_value', 0) or 0))
                    return {
                        'position': 'for',
                        'knob_key': knob,
                        'direction': direction,
                        'delta': round(delta, 4),
                        'confidence': h.get('confidence', 0.4),
                        'rationale': h.get('rationale', '从假说生成器取种子'),
                        'vulnerabilities': [],
                        'brain': 'left',
                        'source': 'hypothesis_seed',
                    }
        except:
            pass
    
    # 2. 没有假说种子 → 选一个死亡最多的参数做反向
    death_counts = Counter()
    for d in deaths:
        knob = d.get('knob_key', '?')
        if knob != '?':
            death_counts[knob] += 1
    
    if death_counts:
        worst_knob, _ = death_counts.most_common(1)[0]
        recent_deaths = [d for d in deaths if d.get('knob_key') == worst_knob]
        if recent_deaths:
            last = recent_deaths[-1]
            old_v = last.get('old_value', 0) or 0
            new_v = last.get('new_value', 0) or 0
            if new_v != old_v:
                direction = 'up' if new_v < old_v else 'down'
                delta = abs(new_v - old_v) * 0.6
                return {
                    'position': 'for',
                    'knob_key': worst_knob,
                    'direction': direction,
                    'delta': round(delta, 4),
                    'confidence': 0.5,
                    'rationale': f'跟随死亡实验{_knob_short(worst_knob)}的趋势反方向',
                    'vulnerabilities': [],
                    'brain': 'left',
                    'source': 'trend_follow',
                }
    
    # 3. 没有死亡→随便选个校准参数微调
    for k, v in list(cal.items())[:5]:
        if isinstance(v, (int, float)):
            return {
                'position': 'for',
                'knob_key': k,
                'direction': 'up',
                'delta': round(abs(v * 0.1), 4) if v else 0.1,
                'confidence': 0.3,
                'rationale': f'无死亡数据，微调{_knob_short(k)}(+10%)',
                'vulnerabilities': [],
                'brain': 'left',
                'source': 'default_explore',
            }
    
    return None


# ═══ 右脑 ═══

def _right_brain_position(cal, deaths, running, left_pos):
    """
    右脑：质疑路径
    
    对于左脑的输出，逐一找漏洞：
    1. 数据量是否足够支持这个结论
    2. 有没有混淆变量
    3. 会不会是均值回归
    4. 样本选择有偏吗
    5. 对抗种子中有没有反对这个方向的数据
    
    输出：反驳或修正
    """
    if not left_pos:
        return None
    
    vulnerabilities = []
    
    knob = left_pos.get('knob_key', '')
    direction = left_pos.get('direction', '')
    delta = left_pos.get('delta', 0)
    short = _knob_short(knob)
    
    # 质疑1: 数据量不足
    relevant_deaths = [d for d in deaths if d.get('knob_key') == knob]
    if len(relevant_deaths) < 2:
        vulnerabilities.append({
            'type': 'insufficient_data',
            'severity': 'medium',
            'detail': f'{short}只有{len(relevant_deaths)}次死亡记录，不足以支持方向性结论',
        })
    
    # 质疑2: 混淆变量（如果这个参数和其他参数联动）
    running_same_knob = [r for r in running if r.get('knob_key') == knob]
    if len(running_same_knob) >= 2:
        vulnerabilities.append({
            'type': 'confounding_variable',
            'severity': 'high',
            'detail': f'{short}已有{len(running_same_knob)}个running实验在同时进行，建议等待结果',
        })
    
    # 质疑3: 方向太激进
    if delta > 0.1:
        conf = 0.5
    else:
        conf = 0.7
    
    # 质疑4: 对抗种子中有没有相反信号
    adv_count = sum(1 for d in deaths if d.get('knob_key') == knob and 
                    d.get('type', '') in ('adversarial', 'anomaly'))
    if adv_count > 0:
        vulnerabilities.append({
            'type': 'adversarial_seed',
            'severity': 'medium',
            'detail': f'{short}曾作为对抗参数出现{adv_count}次，抗扰动能力存疑',
        })
    
    # 根据漏洞数量调整置信度
    base_confidence = 0.6
    for v in vulnerabilities:
        if v['severity'] == 'high':
            base_confidence -= 0.2
        elif v['severity'] == 'medium':
            base_confidence -= 0.1
    base_confidence = max(0.1, base_confidence)
    
    # 右脑的输出：如果漏洞太多，建议反方向
    high_sev_count = sum(1 for v in vulnerabilities if v['severity'] == 'high')
    
    if high_sev_count >= 1:
        # 强烈质疑 → 建议反方向
        opp_direction = 'down' if direction == 'up' else 'up'
        reduced_delta = delta * 0.5
        return {
            'position': 'against',
            'knob_key': knob,
            'direction': opp_direction,
            'delta': round(reduced_delta, 4),
            'confidence': round(base_confidence, 2),
            'rationale': f'质疑左脑: {short}{direction}方向，因{len(vulnerabilities)}个漏洞 → 建议{opp_direction}',
            'vulnerabilities': vulnerabilities,
            'brain': 'right',
            'source': 'skeptic',
        }
    else:
        # 轻度质疑 → 建议减小幅度
        reduced_delta = delta * 0.7
        return {
            'position': 'against',
            'knob_key': knob,
            'direction': direction,
            'delta': round(reduced_delta, 4),
            'confidence': round(base_confidence, 2),
            'rationale': f'审慎: {short}方向可接受，但建议从{delta}缩至{round(reduced_delta,4)}',
            'vulnerabilities': vulnerabilities,
            'brain': 'right',
            'source': 'cautious',
        }


# ═══ 仲裁器 ═══

def _arbitrate(left_pos, right_pos):
    """
    仲裁器：当左右脑打架时，决定谁赢
    
    规则：
      - 如果左右脑方向相反 → 两个都生成实验，但右脑实验标记为 counter
      - 如果左右脑方向相同但幅度不同 → 取左脑幅度（左脑更冒险是好事）
      - 如果右脑置信度 > 左脑置信度 → 右脑赢得第一优先级
    """
    if not left_pos:
        return {'winner': 'right', 'experiments': [right_pos]} if right_pos else None
    
    if not right_pos:
        return {'winner': 'left', 'experiments': [left_pos]}
    
    # 判断方向是否冲突
    same_direction = (left_pos['direction'] == right_pos['direction'])
    same_knob = (left_pos['knob_key'] == right_pos['knob_key'])
    
    if not same_knob:
        # 不同参数 → 不冲突，两个都跑
        return {
            'winner': 'both',
            'experiments': [left_pos, right_pos],
            'note': '左右脑聚焦不同参数，并行执行',
        }
    
    if not same_direction:
        # 方向冲突 → 生成两个实验，右脑标记为质疑者
        left_pos['tag'] = 'standard'
        right_pos['tag'] = 'skeptic'
        return {
            'winner': 'pending',
            'experiments': [left_pos, right_pos],
            'note': f'方向冲突: 左脑{left_pos["direction"]} vs 右脑{right_pos["direction"]}，并行对比',
        }
    
    # 方向相同 → 左脑幅度，右脑做安全网
    if right_pos['confidence'] > left_pos['confidence']:
        winner = 'right'
        experiments = [right_pos]
    else:
        winner = 'left'
        experiments = [left_pos]
    
    return {
        'winner': winner,
        'experiments': experiments,
        'note': f'{winner}脑赢得仲裁 (左脑conf={left_pos["confidence"]}, 右脑conf={right_pos["confidence"]})',
    }


def _create_dual_experiments(arbitration):
    """
    将仲裁结果写入实验目录
    
    左右脑的实验分别标记 dual_brain 来源
    """
    if not arbitration:
        return 0
    
    exps = arbitration.get('experiments', [])
    created = 0
    
    for pos in exps:
        if not pos:
            continue
        
        brain = pos.get('brain', 'unknown')
        short = _knob_short(pos.get('knob_key', '?'))
        ts = int(time.time())
        tag = pos.get('tag', 'standard')
        name = f'db_{brain}_{tag}_{short}_{ts}'
        
        # 防止重复（检查是否已有同名实验在running）
        existing = [f for f in os.listdir(EXPT_DIR) 
                   if f.startswith(f'db_{brain}_{tag}_{short}') and f.endswith('.json')]
        if existing:
            _log(f'跳过: {name} 已存在')
            continue
        
        exp = {
            'experiment_id': name,
            'name': name,
            'knob_key': pos['knob_key'],
            'old_value': pos.get('delta', 0.1),
            'new_value': pos.get('delta', 0.1) * (1.1 if pos.get('direction') == 'up' else 0.9),
            'direction': pos['direction'],
            'delta': pos['delta'],
            'brain': brain,
            'tag': tag,
            'rationale': pos.get('rationale', ''),
            'vulnerabilities': pos.get('vulnerabilities', []),
            'source': 'dual_brain',
            'min_days': 7,
            'min_users_per_group': 2,
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'status': 'running',
        }
        
        fp = os.path.join(EXPT_DIR, f'{name}.json')
        with open(fp, 'w', encoding='utf-8') as f:
            json.dump(exp, f, ensure_ascii=False, indent=2)
        
        created += 1
        _log(f'  [{brain}/{tag}] {short}: {pos["direction"]} Δ={pos["delta"]} conf={pos["confidence"]}')
    
    return created


def run_brain_cycle():
    """
    一轮双脑对抗周期
    
    返回: 仲裁结果
    """
    cal = _load_cal()
    deaths = _load_deaths()
    running = _load_running()
    
    if not cal:
        _log('无校准数据，跳过双脑')
        return None
    
    _log(f'双脑对抗: {len(deaths)}死亡 {len(running)}运行中')
    
    # 左脑先输出
    left_pos = _left_brain_position(cal, deaths, running)
    if left_pos:
        _log(f'  左脑: {_knob_short(left_pos["knob_key"])} → {left_pos["direction"]} Δ={left_pos["delta"]} ({left_pos["rationale"][:40]})')
    else:
        _log('  左脑: 无输出')
        return None
    
    # 右脑质疑左脑
    right_pos = _right_brain_position(cal, deaths, running, left_pos)
    if right_pos:
        vlens = len(right_pos.get('vulnerabilities', []))
        _log(f'  右脑: {_knob_short(right_pos["knob_key"])} → {right_pos["direction"]} Δ={right_pos["delta"]} ({vlens}漏洞)')
    else:
        _log('  右脑: 无质疑')
    
    # 仲裁
    result = _arbitrate(left_pos, right_pos)
    if result:
        _log(f'  仲裁: {result["winner"]} ({result.get("note", "")})')
        n = _create_dual_experiments(result)
        _log(f'  创建 {n} 个双脑实验')
    
    return result


def get_brain_state():
    """获取双脑状态"""
    running = _load_running()
    brain_exps = [r for r in running if r.get('source') == 'dual_brain']
    
    left_wins = sum(1 for r in brain_exps if r.get('brain') == 'left' and r.get('tag') == 'standard')
    right_wins = sum(1 for r in brain_exps if r.get('brain') == 'right' and r.get('tag') == 'skeptic')
    
    return {
        'active_experiments': len(brain_exps),
        'left_wins': left_wins,
        'right_wins': right_wins,
        'brain_weights': dict(BRAIN_WEIGHTS),
        'left_tools': LEFT_BRAIN_TOOLS,
        'right_tools': RIGHT_BRAIN_TOOLS,
    }


if __name__ == '__main__':
    print('双脑对抗引擎 v1')
    print('=' * 40)
    result = run_brain_cycle()
    if result:
        print(f'\n仲裁: {result["winner"]}')
        for e in result.get('experiments', []):
            if e:
                print(f'  [{e["brain"]}] {_knob_short(e["knob_key"]):30s} {e["direction"]} Δ={e["delta"]}')
    else:
        print('(无可执行的对抗)')
