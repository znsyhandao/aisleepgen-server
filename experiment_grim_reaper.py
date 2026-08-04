#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
experiment_grim_reaper.py — 实验终结者 v1

职责：不是手动清理，而是自适应判断实验生死。
规则:
  - 启动超过 max_idle_days 且无新 feedback → abandoned
  - 启动超过 min_days * 2 且数据量不足 → inconclusive → finished
  - 启动超过 max_days 且数据充足 → auto_completed
  
数据驱动的收敛，不依赖外部指令。
"""

import json, os, time, sys
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\AISleepGen_Optimized'
EXPT_DIR = os.path.join(BASE, 'data', 'experiments')
FB_PATH = os.path.join(BASE, 'data', 'feedback.json')

# ═══ 参数 ═══
DEFAULT_CONFIG = {
    'max_idle_hours': 24,        # 超过24小时无新feedback→abandon
    'max_days': 14,              # 14天后自动完成
    'min_users_for_pass': 3,     # 至少3个用户数据才算pass
    'idle_check_enabled': True,
}

def _log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] {msg}')


def _load_config():
    cfg_path = os.path.join(EXPT_DIR, '_grim_reaper_config.json')
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    except:
        return dict(DEFAULT_CONFIG)


def _get_feedback_stats():
    """计算每个实验创建以来的新feedback数"""
    if not os.path.exists(FB_PATH):
        return {}
    try:
        with open(FB_PATH, 'r', encoding='utf-8') as f:
            fbs = json.load(f)
        if not isinstance(fbs, list):
            return {}
        return {
            'total': len(fbs),
            'real_count': sum(1 for fb in fbs if fb.get('openid','') not in ('reg_test','test')),
            'latest_ts': fb.get('time', '') if fbs else '',
        }
    except:
        return {'total': 0, 'real_count': 0, 'latest_ts': ''}


def _age_hours(created_str):
    """从ISO时间戳计算存活小时数"""
    try:
        created = datetime.fromisoformat(created_str)
        delta = datetime.now() - created
        return delta.total_seconds() / 3600
    except:
        return None


def reap():
    """
    收割：检查所有running/suspended实验，决定生死
    
    返回: dict {收敛实验id: 状态}
    """
    config = _load_config()
    fb_stats = _get_feedback_stats()
    now = datetime.now()
    
    expts = [f for f in os.listdir(EXPT_DIR) 
             if f.endswith('.json') and not f.startswith('_')]
    
    reaped = {}
    
    for fn in expts:
        fp = os.path.join(EXPT_DIR, fn)
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                d = json.load(f)
        except:
            continue
        
        status = d.get('status', d.get('_status', '?'))
        if status in ('completed', 'rolled_back', 'abandoned', 'finished', 'finished_inconclusive'):
            continue
        
        name = d.get('name', '?')
        created = d.get('created_at', d.get('started_at', ''))
        min_days = d.get('min_days', 3)
        max_idle_hours = config.get('max_idle_hours', 24)
        min_users = config.get('min_users_for_pass', 3)
        max_days = config.get('max_days', 14)
        
        age_h = _age_hours(created)
        if age_h is None:
            continue
        
        decision = None
        new_status = None
        reason = None
        
        # 规则1: 超过max_days → 自动完成（有数据用completed，无数据用inconclusive）
        if age_h > max_days * 24:
            if fb_stats.get('real_count', 0) >= min_users:
                decision = 'completed'
                new_status = 'completed'
                reason = f'运行{age_h:.0f}h超过{max_days}天, 有{fb_stats.get("real_count",0)}个真实用户反馈'
            else:
                decision = 'finished_inconclusive'
                new_status = 'finished_inconclusive'
                reason = f'运行{age_h:.0f}h超过{max_days}天, 仅有{fb_stats.get("real_count",0)}用户数据(<{min_users})'
        
        # 规则2: 超过min_days * 2 且数据量不足 → inconclusive
        elif age_h > min_days * 24 * 2:
            if fb_stats.get('real_count', 0) < min_users:
                decision = 'finished_inconclusive'
                new_status = 'finished_inconclusive'
                reason = f'运行{age_h:.0f}h超{min_days*2}天, 数据不足(真实用户{fb_stats.get("real_count",0)}<{min_users})'
        
        # 规则3: 超过max_idle_hours无新feedback → abandoned
        if decision is None and config.get('idle_check_enabled'):
            latest_str = fb_stats.get('latest_ts', '')
            if latest_str:
                try:
                    latest_fb = datetime.fromisoformat(latest_str)
                    idle_hours = (now - latest_fb).total_seconds() / 3600
                    if idle_hours > max_idle_hours:
                        # 但跳过7月7日新创建的实验（才几小时）
                        if age_h > max_idle_hours:
                            decision = 'abandoned'
                            new_status = 'abandoned'
                            reason = f'{idle_hours:.0f}h无新feedback, 超过{max_idle_hours}h门限'
                except:
                    pass
        
        if decision:
            d['_previous_status'] = d.get('status', d.get('_status', '?'))
            d['status'] = new_status
            d['_status'] = new_status
            d['reaped_at'] = now.isoformat()
            d['reap_reason'] = reason
            d['grim_reaper'] = True
            
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            
            reaped[fn] = {
                'name': name,
                'old_status': d['_previous_status'],
                'new_status': new_status,
                'reason': reason,
                'age_hours': round(age_h, 1),
            }
            _log(f'收割: {name:40s} ({age_h:.0f}h) {d["_previous_status"]} → {new_status}')
            _log(f'  理由: {reason}')
    
    if not reaped:
        _log('收割: 无完成条件的实验')
    
    return reaped


def status():
    """查看当前实验状态摘要"""
    expts = [f for f in os.listdir(EXPT_DIR) 
             if f.endswith('.json') and not f.startswith('_')]
    
    counts = {'running': 0, 'suspended': 0, 'completed': 0, 
              'rolled_back': 0, 'finished': 0, 'abandoned': 0, 
              'finished_inconclusive': 0, 'other': 0}
    
    for fn in expts:
        try:
            with open(os.path.join(EXPT_DIR, fn), 'r', encoding='utf-8') as f:
                d = json.load(f)
            st = d.get('status', d.get('_status', '?'))
            if st in counts:
                counts[st] += 1
            else:
                counts['other'] += 1
        except:
            counts['other'] += 1
    
    total = sum(counts.values())
    return {'total': total, **counts}


if __name__ == '__main__':
    print('实验终结者 v1')
    print('=' * 40)
    
    # 先看当前状态
    st = status()
    print(f'当前状态: {json.dumps(st, indent=2)}')
    
    # 运行收割
    print(f'\n开始收割...')
    r = reap()
    print(f'\n收割结果: {len(r)} 个实验')
    
    # 最终状态
    st2 = status()
    print(f'\n最终状态: {json.dumps(st2, indent=2)}')
    
    print(f'\n✅ 实验终结者就绪')
