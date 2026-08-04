#!/usr/bin/env python3
"""Verify all 3 broken flows fixed"""
import urllib.request, json, sys
sys.path.insert(0, r'D:\AISleepGen_Optimized')

# 1. Trigger world-step
data = json.dumps({
    'openid': 'test_user',
    'hr': 72, 'stress': 7,
    'elapsed_s': 10
}).encode()
r = urllib.request.urlopen('http://localhost:8090/api/sleep/world-step', data=data, timeout=15)
resp = json.loads(r.read())
print('=== ③ 推演重排 ===')
candidates = resp.get('intervention_candidates', [])
if candidates:
    print(f'  Top candidate: {candidates[0]["id"]} (score={candidates[0].get("score","?")})')

print('\n=== ① 历史观测 ===')
# Check observation written
import glob, os
obs_dir = r'D:\AISleepGen_Optimized\data\sleep_time_series\test_user'
obs_files = glob.glob(os.path.join(obs_dir, '*.jsonl'))
if obs_files:
    latest = max(obs_files, key=os.path.getmtime)
    with open(latest, encoding='utf-8') as f:
        lines = [l for l in f if l.strip()]
    print(f'  {len(lines)} observations written')
    
print('\n=== ② 情景记忆 ===')
ctx = resp.get('_memory_context', None)
if ctx:
    print(f'  Memory context: {len(ctx["summaries"])} summaries')
    for s in ctx['summaries'][:3]:
        print(f'    {s}')
else:
    print('  No memory context (expected if no episodic data yet)')

# 3. Verify coordinator loaded observations
from world_model_coordinator import WorldModelCoordinator
c = WorldModelCoordinator('test_user')
c._lazy_load()
obs_count = len(getattr(c, '_recent_observations', [])) 
mem_count = len(getattr(c, '_recent_memories', []))
print(f'\n  Observations loaded: {obs_count}')
print(f'  Memories loaded: {mem_count}')
