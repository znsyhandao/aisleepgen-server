#!/usr/bin/env python3
"""Verify intervention tracking fix"""
import urllib.request, json, sys
sys.path.insert(0, r'D:\AISleepGen_Optimized')

# Step 1: trigger world-step
data = json.dumps({
    'openid': 'test_user',
    'hr': 72, 'stress': 7,
    'elapsed_s': 10
}).encode()
r = urllib.request.urlopen('http://localhost:8090/api/sleep/world-step', data=data, timeout=15)
resp = json.loads(r.read())
candidates = resp.get('intervention_candidates', [])
print(f'Candidates: {len(candidates)}')
for c in candidates[:2]:
    print(f'  {c["id"]}: score={c.get("score","?")}, confidence={c.get("confidence","?")}')

# Step 2: check perception graph
from wm_memory import get_perception_graph
pg = get_perception_graph()
records = [n for nid, n in pg.graph['nodes'].items() if n.get('type') == 'intervention_record']
print(f'\nPerception graph has {len(records)} intervention records')
if records:
    r = records[-1]
    print(f'  Latest: action={r["action_id"]}, score_delta={r["score_delta"]}, completed={r["completed"]}')
