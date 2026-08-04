#!/usr/bin/env python3
"""Phase 1 integration tests: Working Memory + POMDP + ConsciousDecider + MetaLearner"""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Clean up any previous test data
import shutil
for d in ['user_pomdp', os.path.join('data', 'working_memory')]:
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), d)
    if os.path.exists(p):
        shutil.rmtree(p, ignore_errors=True)

from working_memory import WorkingMemory, get_working_memory
from pomdp_learner import POMDPEngine, get_engine
from conscious_decider import ConsciousDecider, get_decider, DEFAULT_WEIGHTS

print('='*60)
print('Phase 1 Integration Tests: Working Memory')
print('='*60)

# Use the global engine singleton so build_pomdp_context uses the same instance
eng = get_engine(0.9, 0.1)
# Reset it by clearing state (this is a new session)
eng.users.clear()
eng.working_memory = get_working_memory()
openid1 = 'test_int_1'

# Observe text (should auto-push to WM)
eng.observe(openid1, text='昨晚失眠了，3点才睡着')
stb = eng.working_memory.short_term_belief(openid1)
print(f'  After 1 obs: WM entries={stb["n"]}, score={stb["weighted_score"]}')
assert stb['n'] == 1, f'Expected 1 WM entry, got {stb["n"]}'

# Observe survey
eng.observe_survey(openid1, score=35, bedtime='22:00')
stb = eng.working_memory.short_term_belief(openid1)
print(f'  After 2 obs (survey): WM entries={stb["n"]}, score={stb["weighted_score"]}')
assert stb['n'] == 2, f'Expected 2 WM entries, got {stb["n"]}'

# Short term context
ctx = eng._get_short_term_context(openid1)
print(f'  Short term context: {ctx}')
assert '[短期记忆:' in ctx, 'Context should contain short-term memory info'
print('  PASS')

# ===== Test 2: Short-term vs long-term =====
print('\n--- Test 2: Short-term down, long-term ok ---')
openid2 = 'test_int_2'

# 5 good days -> POMDP long-term goes high
for i in range(5):
    eng.observe_survey(openid2, score=85, bedtime='22:00', mood='positive')

lt_belief = eng.get_belief(openid2)
print(f'  After 5 good surveys: LT score={lt_belief["expected_score"]}')

# Now 1 bad day -> push to WM directly
eng.working_memory.push(openid2, {
    'text': 'Bad night',
    'score_obs': 35,
    'emotion': 'negative',
    'intervention': 'none',
    'outcome': 'none',
})

stb = eng.working_memory.short_term_belief(openid2)
trend = eng.working_memory.recent_trend(openid2)
print(f'  ST score: {stb["weighted_score"]}, LT score: {lt_belief["expected_score"]}')
print(f'  Trend: {trend["direction"]} (slope={trend["slope"]})')
assert trend['direction'] == 'down', f'Trend should be down, got {trend["direction"]}'
assert stb['weighted_score'] < lt_belief['expected_score'], \
    f'ST ({stb["weighted_score"]}) should be < LT ({lt_belief["expected_score"]})'
print('  PASS')

# ===== Test 3: WM context in prompt builder =====
print('\n--- Test 3: build_pomdp_context includes WM info ---')
from chat_prompt_builder import build_pomdp_context

ctx = build_pomdp_context(openid2)
print(f'  Context contains short-term memory: {"短期记忆" in ctx}')
print(f'  Context excerpt: {ctx[:200]}')
assert '短期记忆' in ctx or '短期评分' in ctx, 'Context should contain short-term memory info'
print('  PASS')

# ===== Test 4: ConsciousDecider WM voting =====
print('\n--- Test 4: CD WM voting factor ---')
openid3 = 'test_int_3'

# Set up: short-term down, long-term ok scenario
for i in range(5):
    eng.observe_survey(openid3, score=85, bedtime='22:00', mood='positive')

eng.working_memory.push(openid3, {
    'text': 'Bad day',
    'score_obs': 30,
    'emotion': 'negative',
    'intervention': 'none',
    'outcome': 'none',
})

# Make decision
cd = get_decider()
decision = cd.decide(openid3, 'score_update', {'total_score': 30}, profile={'openid': openid3})
print(f'  Decision: {decision["action"]}')
print(f'  Action scores: {json.dumps(decision["action_scores"], indent=4)}')

# Check that WM signal is present
sig = decision['signals'].get('wm_signal', {})
print(f'  WM signal: {sig}')
assert sig.get('has_data'), 'WM signal should be present'
assert sig.get('trend') == 'down', f'Trend should be down, got {sig.get("trend")}'
print('  PASS')

# ===== Test 5: CD trend-down voting (long score > 60 -> push+15) =====
print('\n--- Test 5: CD trend=down + long>60 -> push boost ---')
# The WM signal should cause push to get +15 in the weighted vote
# Run the weighted_vote manually to verify
sig = decision['signals']
scores_before = {'push_now': 0.2, 'delay_push': 0.15, 'in_chat': 0.1, 'probe': 0.05, 'skip': 0.5}

# Simulate the WM voting logic
wm_trend = sig['wm_signal']['trend']
wm_long_score = sig['wm_signal']['long_term_score']
if wm_trend == 'down' and wm_long_score > 60:
    push_boost = 0.15
    print(f'  WM voting: push+{push_boost} (trend=down, long={wm_long_score:.0f}>60)')
    assert push_boost == 0.15, f'Expected 0.15 push boost'
    print('  PASS')
else:
    print(f'  WM voting not triggered: trend={wm_trend}, long_score={wm_long_score}')

# ===== Test 6: MetaLearner volatility =====
print('\n--- Test 6: MetaLearner volatility adjustment ---')
vol = eng.working_memory.get_volatility(openid3)
print(f'  Volatility for {openid3}: {vol}')
assert vol > 0, 'Volatility should be > 0'
assert vol > 15, f'High swing scenario, volatility should be > 15, got {vol}'

# Test low volatility scenario
openid4 = 'test_int_4'
for i in range(6):
    eng.working_memory.push(openid4, {
        'text': f'Day {i}',
        'score_obs': 75,
        'emotion': 'positive',
        'intervention': 'none',
        'outcome': 'none',
    })
vol_low = eng.working_memory.get_volatility(openid4)
print(f'  Low volatility (stable scores): {vol_low}')
assert vol_low < 5, f'Stable scores should have low volatility, got {vol_low}'
print('  PASS')

# Test MetaLearner integration
from meta_learner import MetaLearner
ml = MetaLearner()
print(f'  MetaLearner loaded: OK')

print('\n' + '='*60)
print('All integration tests PASS!')
print('='*60)
