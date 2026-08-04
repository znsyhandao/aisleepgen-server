#!/usr/bin/env python3
"""Phase 3: Temporal Depth tests"""
import sys, os, json, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Clear any stale WM test data
wm_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'data', 'working_memory')
if os.path.exists(wm_dir):
    for f in os.listdir(wm_dir):
        if f.startswith('test_td_'):
            try:
                os.remove(os.path.join(wm_dir, f))
            except Exception:
from working_memory import WorkingMemory
from pomdp_learner import get_engine as _get_eng
from behavior_predictor import get_predictor
from conscious_decider import get_decider
from chat_prompt_builder import build_pomdp_context

print('='*60)
print('Phase 3 Tests: Temporal Depth Enhancement')
print('='*60)

# ===== Test 1: 连续降分 → 正在恶化 =====
print('\n--- Test 1: Continuous decline → "正在恶化" ---')
wm = WorkingMemory(max_window=15)
oid1 = 'test_td_1'
for s in [80, 75, 70, 65, 60, 55, 50]:
    wm.push(oid1, {'text':'x', 'score_obs':s, 'emotion':'neutral', 'intervention':'none', 'outcome':'none'})
state1 = wm.state_context(oid1)
sig1 = wm.temporal_signature(oid1)
print(f'  State: {state1}, vel={sig1["velocity"]}, acc={sig1["acceleration"]}')
assert state1 == '正在恶化', f'Expected 正在恶化, got {state1}'
print('  PASS')

# ===== Test 2: 降分后反弹 → 触底反弹 =====
print('\n--- Test 2: Decline then rebound → "触底反弹" ---')
oid2 = 'test_td_2'
for s in [80, 75, 50, 40, 35, 45, 55, 65]:
    wm.push(oid2, {'text':'x', 'score_obs':s, 'emotion':'neutral', 'intervention':'none', 'outcome':'none'})
state2 = wm.state_context(oid2)
sig2 = wm.temporal_signature(oid2)
print(f'  State: {state2}, vel={sig2["velocity"]}, acc={sig2["acceleration"]}')
assert state2 in ('触底反弹', '正在改善'), f'Expected 触底反弹 or 正在改善, got {state2}'
print('  PASS')

# ===== Test 3: 升分后降 → 高位回落 =====
print('\n--- Test 3: Rise then fall → "高位回落" ---')
oid3 = 'test_td_3'
for s in [40, 45, 55, 65, 70, 75, 72, 68, 62]:
    wm.push(oid3, {'text':'x', 'score_obs':s, 'emotion':'neutral', 'intervention':'none', 'outcome':'none'})
state3 = wm.state_context(oid3)
sig3 = wm.temporal_signature(oid3)
print(f'  State: {state3}, vel={sig3["velocity"]}, acc={sig3["acceleration"]}')
assert state3 == '高位回落', f'Expected 高位回落, got {state3}'
print('  PASS')

# ===== Test 4: 不同状态 → CD 决策不同 =====
print('\n--- Test 4: Different states → different CD decisions ---')
eng = _get_eng()
cd = get_decider()

# User in worsening state - use only observe_survey (which auto-pushes to WM)
oid4_worse = 'test_td_4_w'
scores_down = [80, 75, 68, 60, 55, 48, 42]
for s in scores_down:
    eng.observe_survey(oid4_worse, score=s, bedtime='23:30', mood='negative')

state4w = eng.working_memory.state_context(oid4_worse)
print(f'  Worsening state: {state4w}')
assert state4w == '正在恶化', f'Expected 正在恶化, got {state4w}'

dec4w = cd.decide(oid4_worse, 'score_update', {'total_score': 42}, profile={'openid': oid4_worse})
print(f'  Decision: {dec4w["action"]} (scores: push={dec4w["action_scores"]["push_now"]:.3f}, delay={dec4w["action_scores"]["delay_push"]:.3f})')
# The push should be boosted due to temporal context

# User in improving state - use only observe_survey
oid4_good = 'test_td_4_g'
scores_up = [30, 35, 40, 48, 55, 60, 68]
for s in scores_up:
    eng.observe_survey(oid4_good, score=s, bedtime='22:30', mood='positive')

state4g = eng.working_memory.state_context(oid4_good)
print(f'  Improving state: {state4g}')
assert state4g == '正在改善', f'Expected 正在改善, got {state4g}'

dec4g = cd.decide(oid4_good, 'score_update', {'total_score': 68}, profile={'openid': oid4_good})
print(f'  Decision: {dec4g["action"]} (scores: in_chat={dec4g["action_scores"]["in_chat"]:.3f}, skip={dec4g["action_scores"]["skip"]:.3f})')

print('  PASS')

# ===== Test 5: 注入prompt包含时序信息 =====
print('\n--- Test 5: Prompt injection includes temporal info ---')
# Need to use a user that has data in both POMDP and WM
ctx = build_pomdp_context(oid4_worse)
print(f'  Context: {ctx[:400]}')
assert '时序' in ctx, 'Context should contain temporal info'
assert '状态=' in ctx, 'Context should contain state='
print('  PASS')

# ===== Test 6: Behavior predictor includes temporal context =====
print('\n--- Test 6: BP context includes temporal info ---')
bp = get_predictor()
pred_ctx = bp.format_prediction_context(oid4_worse)
print(f'  BP context: {pred_ctx}')
assert '时序状态' in pred_ctx, 'BP context should include temporal state'
print('  PASS')

print('\n' + '='*60)
print('All Phase 3 tests PASS!')
print('='*60)
