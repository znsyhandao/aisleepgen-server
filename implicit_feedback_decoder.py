#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
implicit_feedback_decoder.py — 隐性反馈解码器 v1

"把至尊宝的一句话变成系统的校准信号。"

系统现在只知道从微信小程序的 rating/pain/mood 接收反馈。
但它不知道：至尊宝在小甜甜对话里说了什么、情绪走向如何。

这个模块从 memory/ 历史日志中提取"隐性反馈信号"：
  1. 至尊宝的情绪趋势（紧急度/满意度/发散度）
  2. 行动指令的类型（收敛/发散/纠正/自由创造）
  3. 每个信号的置信度

输出：一个结构化校准向量，供系统在 next_heartbeat 中使用。
"""

import json, os, re, time, sys
from collections import Counter, deque

sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\AISleepGen_Optimized'
DATA_DIR = os.path.join(BASE, 'data')
HISTORY_DIR = r'C:\Users\cqs10\.openclaw\workspace\memory'
SIGNAL_PATH = os.path.join(DATA_DIR, 'implicit_signals.json')
LOG_PATH = os.path.join(BASE, 'logs', 'implicit_feedback.log')

# ═══ 信号字典 ═══
# 关键词 → (维度, 强度, 方向)

CONVERGE_SIGNALS = {
    '按最佳实践干': ('mode', 0.6, 'converge'),
    '不要停下来': ('urgency', 0.8, 'high'),
    '不要等我决策': ('autonomy', 0.7, 'go'),
    '最佳实践继续': ('mode', 0.5, 'converge'),
}

DIVERGE_SIGNALS = {
    '忘掉指标': ('mode', 0.9, 'diverge'),
    '充分发挥创造力': ('mode', 0.9, 'diverge'),
    '哈撒比斯': ('creativity', 0.8, 'diverge'),
    '你觉得这个哈撒比斯': ('challenge', 0.7, 'push'),
    '就这么点改变': ('challenge', 0.9, 'push'),
    '死亡实验': ('concept', 0.6, 'new_framework'),
    '复活': ('concept', 0.6, 'new_framework'),
}

CORRECT_SIGNALS = {
    '不要': ('correction', 0.5, 'stop'),
    '太老实': ('correction', 0.8, 'stop'),
    '不是补丁': ('correction', 0.7, 'reframe'),
    '不是插件': ('correction', 0.7, 'reframe'),
    '换架构': ('correction', 0.9, 'reframe'),
}

ALL_SIGNALS = {**CONVERGE_SIGNALS, **DIVERGE_SIGNALS, **CORRECT_SIGNALS}


def _log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(f'[{ts}] {msg}\n')


def _load_recent_history(days=3):
    """加载近期（最近N天）的对话日志"""
    today = time.strftime('%Y-%m-%d')
    from datetime import datetime, timedelta
    
    texts = {}
    for i in range(days):
        target = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        path = os.path.join(HISTORY_DIR, f'{target}.md')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                texts[target] = f.read()
    return texts


def _load_today_signal():
    """加载今日已有信号"""
    if os.path.exists(SIGNAL_PATH):
        try:
            with open(SIGNAL_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        'last_decode': 0,
        'mode_history': deque(maxlen=20),
        'current_mode': 'converge',  # converge / diverge
        'urgency': 0.3,
        'creativity_pull': 0.3,
        'challenge_level': 0.0,
        'total_signals': 0,
        'signal_log': [],
    }


def _save_signal(signal):
    signal['last_decode'] = time.time()
    # deque → list for JSON
    if isinstance(signal.get('mode_history'), deque):
        signal['mode_history'] = list(signal['mode_history'])
    signal['signal_log'] = signal.get('signal_log', [])[-50:]  # 只保留最近50条
    os.makedirs(os.path.dirname(SIGNAL_PATH), exist_ok=True)
    with open(SIGNAL_PATH, 'w', encoding='utf-8') as f:
        json.dump(signal, f, ensure_ascii=False, indent=2)


def _scan_text(text, date_label):
    """扫描文本中的信号关键词"""
    hits = []
    if not text:
        return hits
    for keyword, (dimension, intensity, direction) in ALL_SIGNALS.items():
        if keyword in text:
            hits.append({
                'keyword': keyword,
                'dimension': dimension,
                'intensity': intensity,
                'direction': direction,
                'source_date': date_label,
                'decoded_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            })
    return hits


def decode():
    """
    解码近期对话中的隐性反馈
    
    返回: {
        'current_mode': 'converge|diverge',
        'urgency': 0~1,
        'creativity_pull': 0~1,
        'challenge_level': 0~1,
        'signal_count': int,
        'recommended_behavior': str,
    }
    """
    signal = _load_today_signal()
    histories = _load_recent_history(days=3)
    
    new_hits = []
    for date_label, text in histories.items():
        for hit in _scan_text(text, date_label):
            # 去重：相同keyword+相同date 不重复记
            already = any(s['keyword'] == hit['keyword'] and s['source_date'] == hit['source_date']
                         for s in signal.get('signal_log', []))
            if not already:
                new_hits.append(hit)
    
    if not new_hits:
        _log(f'无新信号 (已有{len(signal.get("signal_log",[]))}条历史)')
        signal['current_mode'] = signal.get('current_mode', 'converge')
        return _compile_output(signal)
    
    _log(f'发现 {len(new_hits)} 条新信号')
    
    for hit in new_hits:
        signal.setdefault('signal_log', []).append(hit)
        signal['total_signals'] += 1
    
    # 计算当前模式
    recent = signal.get('signal_log', [])[-15:]  # 最近15条信号
    
    converge_count = sum(1 for s in recent if s.get('direction') in ('converge', 'go'))
    diverge_count = sum(1 for s in recent if s.get('direction') in ('diverge', 'push', 'new_framework'))
    
    if diverge_count > converge_count:
        signal['current_mode'] = 'diverge'
    elif converge_count > diverge_count:
        signal['current_mode'] = 'converge'
    else:
        signal['current_mode'] = signal.get('current_mode', 'converge')
    
    # 计算urgency（基于最近3条urgency信号的均值）
    urgency_signals = [s for s in recent if s.get('dimension') == 'urgency']
    if urgency_signals:
        signal['urgency'] = sum(s['intensity'] for s in urgency_signals[-3:]) / min(3, len(urgency_signals))
    
    # 计算creativity_pull
    creativity_signals = [s for s in recent if s.get('dimension') in ('creativity', 'mode') and s.get('direction') == 'diverge']
    if creativity_signals:
        signal['creativity_pull'] = max(s['intensity'] for s in creativity_signals[-3:])
    
    # 计算challenge_level（最近纠正类信号）
    challenge_signals = [s for s in recent if s.get('dimension') in ('challenge', 'correction')]
    if challenge_signals:
        signal['challenge_level'] = max(s['intensity'] for s in challenge_signals[-3:])
    
    _save_signal(signal)
    return _compile_output(signal)


def _compile_output(signal):
    """编译输出摘要"""
    mode = signal.get('current_mode', 'converge')
    urgency = signal.get('urgency', 0.3)
    creativity = signal.get('creativity_pull', 0.3)
    challenge = signal.get('challenge_level', 0.0)
    
    # 行为建议
    if challenge > 0.7:
        behavior = 'scale_up'  # 至尊宝觉得还不够大→放大规模
    elif mode == 'diverge':
        behavior = 'create_new'  # 发散模式→做新东西
    elif mode == 'converge' and urgency > 0.5:
        behavior = 'execute_fast'  # 收敛+紧急→快速执行
    else:
        behavior = 'maintain'  # 正常维护
    
    result = {
        'current_mode': mode,
        'urgency': round(urgency, 2),
        'creativity_pull': round(creativity, 2),
        'challenge_level': round(challenge, 2),
        'signal_count': signal.get('total_signals', 0),
        'recommended_behavior': behavior,
        'decoded_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }
    
    _log(f'解码: mode={mode} urgency={result["urgency"]} creativity={result["creativity_pull"]} challenge={result["challenge_level"]}')
    _log(f'行为建议: {behavior}')
    
    return result


def get_signal():
    """心跳调用接口"""
    return decode()


def reset():
    """重置信号状态（调试用）"""
    default = {
        'last_decode': 0,
        'current_mode': 'converge',
        'urgency': 0.3,
        'creativity_pull': 0.3,
        'challenge_level': 0.0,
        'total_signals': 0,
        'signal_log': [],
    }
    _save_signal(default)
    _log('信号已重置')
    return _compile_output(default)


if __name__ == '__main__':
    print('隐性反馈解码器 v1')
    print('=' * 40)
    result = decode()
    print(f'当前模式: {result["current_mode"]}')
    print(f'紧急度:    {result["urgency"]}')
    print(f'创造拉力:  {result["creativity_pull"]}')
    print(f'挑战级:    {result["challenge_level"]}')
    print(f'行为建议:  {result["recommended_behavior"]}')
    print(f'信号总数:  {result["signal_count"]}')
    
    # 显示最近信号
    signal = json.load(open(SIGNAL_PATH, 'r', encoding='utf-8'))
    print(f'\n最近信号:')
    for s in signal.get('signal_log', [])[-5:]:
        print(f'  [{s["source_date"]}] ({s["dimension"]}/{s["direction"]}) {s["keyword"]}')
