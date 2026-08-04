# -*- coding: utf-8 -*-
"""注入今日对话信号"""
import json, time, sys
sys.stdout.reconfigure(encoding='utf-8')

fp = r'D:\AISleepGen_Optimized\data\implicit_signals.json'

with open(fp, 'r', encoding='utf-8') as f:
    d = json.load(f)
    
print(f'当前模式: {d.get("current_mode")}')
print(f'信号数: {d.get("total_signals")}')

# 注入今天至尊宝说的关键词
new_signals = [
    {'keyword': '哈撒比斯', 'dimension': 'creativity', 'intensity': 0.8, 'direction': 'diverge', 'source_date': '2026-07-07', 'decoded_at': '2026-07-07T11:55:00'},
    {'keyword': '忘掉哪些指标', 'dimension': 'mode', 'intensity': 0.9, 'direction': 'diverge', 'source_date': '2026-07-07', 'decoded_at': '2026-07-07T11:48:00'},
    {'keyword': '充分发挥创造力', 'dimension': 'mode', 'intensity': 0.9, 'direction': 'diverge', 'source_date': '2026-07-07', 'decoded_at': '2026-07-07T11:48:00'},
    {'keyword': '你觉得这个哈撒比斯', 'dimension': 'challenge', 'intensity': 0.7, 'direction': 'push', 'source_date': '2026-07-07', 'decoded_at': '2026-07-07T11:55:00'},
    {'keyword': '就这么点改变', 'dimension': 'challenge', 'intensity': 0.9, 'direction': 'push', 'source_date': '2026-07-07', 'decoded_at': '2026-07-07T11:55:00'},
    {'keyword': '不是补丁', 'dimension': 'correction', 'intensity': 0.7, 'direction': 'reframe', 'source_date': '2026-07-07', 'decoded_at': '2026-07-07T11:55:00'},
    {'keyword': '不是插件', 'dimension': 'correction', 'intensity': 0.7, 'direction': 'reframe', 'source_date': '2026-07-07', 'decoded_at': '2026-07-07T11:55:00'},
    {'keyword': '换架构', 'dimension': 'correction', 'intensity': 0.9, 'direction': 'reframe', 'source_date': '2026-07-07', 'decoded_at': '2026-07-07T11:55:00'},
    {'keyword': '死亡实验', 'dimension': 'concept', 'intensity': 0.6, 'direction': 'new_framework', 'source_date': '2026-07-07', 'decoded_at': '2026-07-07T11:56:00'},
    {'keyword': '复活', 'dimension': 'concept', 'intensity': 0.6, 'direction': 'new_framework', 'source_date': '2026-07-07', 'decoded_at': '2026-07-07T11:56:00'},
    {'keyword': '按最佳实践干', 'dimension': 'mode', 'intensity': 0.6, 'direction': 'converge', 'source_date': '2026-07-07', 'decoded_at': '2026-07-07T11:50:00'},
]

for s in new_signals:
    d.setdefault('signal_log', []).append(s)
    d['total_signals'] = d.get('total_signals', 0) + 1

# 重新计算模式
recent = d['signal_log'][-20:]
converge_count = sum(1 for s in recent if s.get('direction') in ('converge', 'go'))
diverge_count = sum(1 for s in recent if s.get('direction') in ('diverge', 'push', 'new_framework'))

if diverge_count > converge_count:
    d['current_mode'] = 'diverge'
elif converge_count > diverge_count:
    d['current_mode'] = 'converge'

# 计算紧急度
urgency_sigs = [s for s in recent if s.get('dimension') == 'urgency']
if urgency_sigs:
    d['urgency'] = sum(s['intensity'] for s in urgency_sigs[-3:]) / min(3, len(urgency_sigs))
else:
    d['urgency'] = 0.3

# 创造力拉力
crea_sigs = [s for s in recent if s.get('dimension') in ('creativity', 'mode') and s.get('direction') == 'diverge']
if crea_sigs:
    d['creativity_pull'] = max(s['intensity'] for s in crea_sigs[-3:])
else:
    d['creativity_pull'] = 0.3

# 挑战级
chal_sigs = [s for s in recent if s.get('dimension') in ('challenge', 'correction')]
if chal_sigs:
    d['challenge_level'] = max(s['intensity'] for s in chal_sigs[-3:])
else:
    d['challenge_level'] = 0.0

d['last_decode'] = time.time()
d['signal_log'] = d['signal_log'][-50:]

with open(fp, 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print(f'注入后: mode={d["current_mode"]}, urgency={d["urgency"]:.1f}, creativity={d["creativity_pull"]:.1f}, challenge={d["challenge_level"]:.1f}')
print(f'信号总数: {d["total_signals"]}')
