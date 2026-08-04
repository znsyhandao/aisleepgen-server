#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
input_compressor.py — 反熵压缩器 v1

"今天最值得做的一件事"

不是今日总结。是系统主动压缩信息熵——在最混乱的地方，找出最准的一拳。

流程：
  1. 扫描所有数据源 → 计算每个数据源的"熵值"（混乱度）
  2. 输出10维状态向量（每个维度是"这个数据源今天值得关注的程度"）
  3. 基于向量推理出"今天最值得做的一件事"
  4. 这件事被写入 _prioritized_action.json，供下一轮心跳使用
"""

import json, os, time, sys, math
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\AISleepGen_Optimized'
RADAR = r'D:\super_frontier_radar'
DATA_DIR = os.path.join(BASE, 'data')
EXPT_DIR = os.path.join(BASE, 'data', 'experiments')
FB_PATH = os.path.join(DATA_DIR, 'feedback.json')
CAL_PATH = os.path.join(DATA_DIR, 'calibration.json')
SIGNAL_PATH = os.path.join(DATA_DIR, 'implicit_signals.json')
BAOWANG_PATH = os.path.join(DATA_DIR, 'baowang_model.json')
ARCHIVE_PATH = os.path.join(DATA_DIR, 'algorithm_archive.json')
ACTION_PATH = os.path.join(DATA_DIR, '_prioritized_action.json')
LOG_PATH = os.path.join(BASE, 'logs', 'compressor.log')

# ═══ 10个数据源维度 ═══
DIMENSIONS = [
    'experiment_chaos',     # 实验平台混乱度（挂起+废弃实验数 / 总实验）
    'feedback_freshness',   # 反馈新鲜度（最新feedback距今多久）
    'feedback_volume',      # 反馈总量（用户数据量）
    'paper_backlog',        # 未消化论文积压
    'death_density',        # 死亡实验密集度（死亡数 / 总实验）
    'brain_conflict',       # 双脑冲突度（左右脑实验数 / 总running）
    'baowang_urgency',      # 至尊宝情绪紧急度
    'baowang_scale',        # 至尊宝规模偏好
    'baowang_challenge',    # 至尊宝挑战级别
    'system_variance',      # 系统状态方差（校准参数的标准差）
]

# ═══ 压缩阈值 ═══
ENTROPY_THRESHOLDS = {
    'high': 0.7,   # 熵>=0.7 → 这个维度极度混乱，需要干预
    'mid': 0.4,    # 熵>=0.4 → 中等混乱，关注
    'low': 0.2,    # 熵<0.2 → 稳定
}


def _log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(f'[{ts}] {msg}\n')
    print(f'  {msg}')


def _load_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default


def _compute_entropy(counts):
    """计算离散分布的香农熵"""
    total = sum(counts)
    if total == 0:
        return 0.0
    entropy = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            entropy -= p * math.log2(p)
    # 归一化到 [0, 1]
    max_entropy = math.log2(len(counts)) if len(counts) > 1 else 1
    return entropy / max_entropy if max_entropy > 0 else 0.0


def compress():
    """
    反熵压缩主入口
    
    返回: {
        'vector': {dim: float},          # 10维状态向量
        'entropy_map': {dim: str},        # 每个维度的熵级别
        'action': str,                    # 今天最值得做的一件事
        'action_confidence': float,       # 这件事的置信度
        'timestamp': str,
    }
    """
    vector = {}
    entropy_map = {}
    
    # ─── 维度1: 实验混乱度 ───
    expts = [f for f in os.listdir(EXPT_DIR) if f.endswith('.json') and not f.startswith('_')]
    total_expts = len(expts)
    statuses = Counter()
    for fn in expts:
        d = _load_json(os.path.join(EXPT_DIR, fn), {})
        statuses[d.get('status', d.get('_status', '?'))] += 1
    
    chaos = _compute_entropy(list(statuses.values()))
    vector['experiment_chaos'] = round(chaos, 3)
    entropy_map['experiment_chaos'] = _label_entropy(chaos)
    
    # ─── 维度2: 反馈新鲜度 ───
    fbs = _load_json(FB_PATH, [])
    if fbs and isinstance(fbs, list) and len(fbs) > 0:
        # 最新feedback的时间离现在多久（小时）
        latest_ts = max(f.get('time', '') for f in fbs if f.get('time'))
        if latest_ts:
            from datetime import datetime
            try:
                latest_dt = datetime.fromisoformat(latest_ts)
                hours_ago = (datetime.now() - latest_dt).total_seconds() / 3600
                freshness = max(0, min(1, 1 - hours_ago / 48))  # 48小时→0, 现在→1
            except:
                freshness = 0.3
        else:
            freshness = 0.1
    else:
        freshness = 0.0
    vector['feedback_freshness'] = round(freshness, 3)
    entropy_map['feedback_freshness'] = _label_entropy(1 - freshness)
    
    # ─── 维度3: 反馈量 ───
    if isinstance(fbs, list):
        real_count = sum(1 for f in fbs if f.get('openid', '') not in ('reg_test', 'test'))
        vol = min(1.0, real_count / 50)  # 50条=满分
    else:
        vol = 0.0
    vector['feedback_volume'] = round(vol, 3)
    entropy_map['feedback_volume'] = _label_entropy(1 - vol)
    
    # ─── 维度4: 论文积压 ───
    paper_db = _load_json(os.path.join(RADAR, 'frontier_data', 'scanned_papers_db.json'), {})
    papers = paper_db.get('scanned_papers', [])
    # 未消化的（检查 digester 的记录）
    digested_db = _load_json(os.path.join(RADAR, 'frontier_data', 'digested_papers.json'), {})
    digested_ids = set(digested_db.get('digested_ids', []))
    pending = sum(1 for p in papers if p.get('id') not in digested_ids)
    backlog = min(1.0, pending / 10)  # 10篇积压=满分
    vector['paper_backlog'] = round(backlog, 3)
    entropy_map['paper_backlog'] = _label_entropy(backlog)
    
    # ─── 维度5: 死亡密集度 ───
    dead_count = sum(1 for s in statuses if s in ('rolled_back', 'abandoned', 'finished_inconclusive'))
    death_density = dead_count / max(1, total_expts)
    vector['death_density'] = round(death_density, 3)
    entropy_map['death_density'] = _label_entropy(death_density)
    
    # ─── 维度6: 双脑冲突度 ───
    brain_expts = sum(1 for fn in expts if 'db_' in fn)
    running_brain = sum(1 for fn in expts if 'db_' in fn and 
                       (s := _load_json(os.path.join(EXPT_DIR, fn), {}).get('status', '') == 'running'))
    conflict = min(1.0, running_brain / max(1, total_expts) * 3)
    vector['brain_conflict'] = round(conflict, 3)
    entropy_map['brain_conflict'] = _label_entropy(conflict)
    
    # ─── 维度7-9: 至尊宝信号 ───
    sig = _load_json(SIGNAL_PATH, {})
    vector['baowang_urgency'] = round(sig.get('urgency', 0.3), 3)
    entropy_map['baowang_urgency'] = _label_entropy(vector['baowang_urgency'])
    
    bw = _load_json(BAOWANG_PATH, {})
    if bw and isinstance(bw, dict):
        # 找scale_preference的均值
        scales = []
        for profile in bw.values():
            if isinstance(profile, dict):
                scales.append(profile.get('scale_preference', 0.5))
        avg_scale = sum(scales) / len(scales) if scales else 0.5
    else:
        avg_scale = 0.5
    vector['baowang_scale'] = round(avg_scale, 3)
    entropy_map['baowang_scale'] = _label_entropy(avg_scale)
    
    vector['baowang_challenge'] = round(sig.get('challenge_level', 0.0), 3)
    entropy_map['baowang_challenge'] = _label_entropy(vector['baowang_challenge'])
    
    # ─── 维度10: 系统状态方差 ───
    cal = _load_json(CAL_PATH, {})
    if cal and isinstance(cal, dict):
        numeric_vals = [v for v in cal.values() if isinstance(v, (int, float))]
        if numeric_vals:
            mean = sum(numeric_vals) / len(numeric_vals)
            variance = sum((v - mean) ** 2 for v in numeric_vals) / len(numeric_vals)
            variance = min(1.0, variance / 10)  # 归一化
        else:
            variance = 0.1
    else:
        variance = 0.1
    vector['system_variance'] = round(variance, 3)
    entropy_map['system_variance'] = _label_entropy(variance)
    
    # ─── 推理: 今天最值得做的一件事 ───
    action, action_conf = _infer_action(vector, entropy_map)
    
    result = {
        'vector': vector,
        'entropy_map': entropy_map,
        'action': action,
        'action_confidence': round(action_conf, 2),
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }
    
    _save_action(result)
    _log(f'反熵压缩: vector={vector}')
    _log(f'行动: {action} (conf={action_conf:.2f})')
    
    return result


def _label_entropy(value):
    if value >= ENTROPY_THRESHOLDS['high']:
        return 'HIGH'
    elif value >= ENTROPY_THRESHOLDS['mid']:
        return 'MID'
    else:
        return 'LOW'


def _infer_action(vector, entropy_map):
    """
    从10维向量推理"今天最值得做的一件事"
    
    规则引擎（可扩展为RL）:
    """
    # 找出最高熵维度
    high_dims = [k for k, v in entropy_map.items() if v == 'HIGH']
    mid_dims = [k for k, v in entropy_map.items() if v == 'MID']
    
    confidence = 0.0
    action = ''
    
    # 规则1: 死亡密集 + 双脑冲突 → 今天应该复盘死亡实验，提炼新假说
    if 'death_density' in high_dims and 'brain_conflict' in mid_dims:
        action = '复盘死亡实验，为双脑对抗注入新种子'
        confidence = 0.7
    # 规则2: 至尊宝高挑战 + 论文积压 → 今天应该做大规模新尝试
    elif 'baowang_challenge' in high_dims and 'paper_backlog' in mid_dims:
        action = '基于论文积压，生成攻击性假说并创建大尺度实验'
        confidence = 0.8
    # 规则3: 至尊宝高紧急 + 实验混乱 → 今天应该清理实验平台
    elif 'baowang_urgency' in high_dims and 'experiment_chaos' in high_dims:
        action = '先清理实验平台，再推新实验'
        confidence = 0.6
    # 规则4: 反馈新鲜度低（太久没反馈）→ 今天应该检查用户管道
    elif 'feedback_freshness' in high_dims:
        action = '用户数据陈旧，检查feedback管道是否有堵塞'
        confidence = 0.5
    # 规则5: 系统方差高 + 无冲突 → 今天应该校准系统参数
    elif 'system_variance' in high_dims and 'brain_conflict' == 'LOW':
        action = '系统方差偏高且无内部质疑，今天做参数校准'
        confidence = 0.6
    # 规则6: 论文积压 + 至尊宝发散 → 今天做论文消化+转发
    elif 'paper_backlog' in high_dims and vector.get('baowang_scale', 0) > 0.5:
        action = '消化积压论文并注入实验队列'
        confidence = 0.7
    # 默认: 维持当前节奏
    else:
        action = '维持当前心跳管线节奏，重点观察双脑对抗进展'
        confidence = 0.4
    
    return action, confidence


def _save_action(result):
    """写入_prioritized_action.json供心跳使用"""
    with open(ACTION_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def get_priority():
    """外部接口：获取今天的优先行动"""
    if os.path.exists(ACTION_PATH):
        return _load_json(ACTION_PATH, {})
    return compress()


if __name__ == '__main__':
    print('反熵压缩器 v1')
    print('=' * 40)
    
    result = compress()
    print(f'\n10维状态向量:')
    for dim, val in result['vector'].items():
        level = result['entropy_map'][dim]
        icon = '🔴' if level == 'HIGH' else '🟡' if level == 'MID' else '🟢'
        print(f'  {icon} {dim:25s} = {val:.3f} [{level}]')
    print(f'\n今日行动: {result["action"]}')
    print(f'置信度: {result["action_confidence"]}')
