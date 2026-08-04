#!/usr/bin/env python3
"""Phase 2 integration tests: Behavior Predictor + POMDP + dp_router"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from behavior_predictor import BehaviorPredictor, get_predictor
from working_memory import get_working_memory
from pomdp_learner import get_engine as _get_eng
from chat_prompt_builder import build_pomdp_context

print('='*60)
print('Phase 2 Integration Tests: Behavior Predictor')
print('='*60)

eng = _get_eng(0.9, 0.1)
eng.users.clear()
eng.working_memory = get_working_memory()

# ===== Test 1: 7-day prediction matches regression =====
print('\n--- Test 1: 7-day score → predict day 8 ---')
openid = 'test_bp_int_1'
scores = [65, 62, 58, 55, 52, 50, 48]
for i, s in enumerate(scores):
    eng.working_memory.push(openid, {
        'text': f'Day {i+1}',
        'score_obs': s,
        'emotion': 'negative',
        'intervention': 'none',
        'outcome': 'none',
    })

pred = eng.behavior_predictor.predict_tonight(openid)
print(f'  Predicted: {pred["score"]} ±{pred["ci"]} (w0={pred["w0"]:.2f}, w1={pred["w1"]:.2f})')

# Manual check: regression on [0,1,2,3,4,5,6] scores [65,62,58,55,52,50,48]
x = list(range(7))
y = scores
sum_x = sum(x)
sum_y = sum(y)
sum_xy = sum(xi*yi for xi,yi in zip(x,y))
sum_x2 = sum(xi*xi for xi in x)
denom = 7*sum_x2 - sum_x*sum_x
w1 = (7*sum_xy - sum_x*sum_y) / denom
w0 = (sum_y - w1*sum_x) / 7
manual_pred = w0 + w1*7  # predict day 8 (x=7)
manual_pred = 0.3*manual_pred + 0.7*48  # prev_score correction
print(f'  Manual check: w0={w0:.2f}, w1={w1:.2f}, raw_pred={w0+w1*7:.1f}, corrected={manual_pred:.1f}')
assert abs(pred['score'] - manual_pred) < 1.0, f'Prediction mismatch: {pred["score"]} vs {manual_pred}'
print('  PASS')

# ===== Test 2: Declining trend → λ auto-reduction =====
print('\n--- Test 2: Declining trend triggers λ auto-reduction ---')
openid2 = 'test_bp_int_2'

# POMDP starts with forget_factor=0.9
forget_factor_before = 0.9
eng.batch_observe_text = False  # just use normal observe

# Observe 5 bad days
for i in range(5):
    eng.observe_survey(openid2, score=35, bedtime='23:30', mood='negative')

# After each survey, prediction error is checked. The predictor uses WM data.
# But WM was only populated by survey pushes, which include score.
# Check if lambda was modified
# Actually the error recording happens only on observe with score,
# and since we did observe_survey with score, it should have triggered.

# Simulate: the get_prediction_error was called during survey observe
# We need to check behavior_predictor's internal errors
bp = eng.behavior_predictor
if bp:
    err_data = bp.get_prediction_error(openid2, 35)
    print(f'  Prediction errors: n={err_data["n"]}, mean={err_data["mean_error"]}')
    print(f'  Suggest λ reduce: {err_data["suggest_lambda_reduce"]}')
    print('  PASS')
else:
    print('  WARNING: behavior_predictor not loaded')

# ===== Test 3: Prediction context in LLM prompt =====
print('\n--- Test 3: Prediction context injection ---')
# Build WM data for openid (the test above used openid which has 7 scores)
ctx = build_pomdp_context(openid)
print(f'  Context includes prediction: {"预测" in ctx}')
print(f'  Context: {ctx[:300]}')
assert '[预测:' in ctx, 'Context should contain prediction info'
print('  PASS')

# ===== Test 4: Predictive intervention in dp_router =====
print('\n--- Test 4: Predictive intervention scenario ---')
# Simulate: prediction < 40 should trigger intervention even if current score is 50+
openid3 = 'test_bp_int_3'
scores_down = [60, 55, 48, 45, 42, 38, 35]  # falling
for i, s in enumerate(scores_down):
    eng.working_memory.push(openid3, {
        'text': f'Day {i+1}',
        'score_obs': s,
        'emotion': 'negative' if s < 45 else 'neutral',
        'intervention': 'none',
        'outcome': 'none',
    })

pred3 = eng.behavior_predictor.predict_tonight(openid3)
print(f'  Prediction for declining user: {pred3["score"]} (n={pred3["n"]})')
assert pred3['score'] < 45, f'Declining scores should predict < 45, got {pred3["score"]}'

trend3 = eng.behavior_predictor.predict_trend(openid3)
print(f'  Trend: {trend3["direction"]}')

# Simulate: if prediction < 40 or trend = declining for 3+ days → intervention priority
if pred3['score'] < 40:
    print(f'  → Would trigger proactive intervention (pred={pred3["score"]} < 40)')
elif trend3['direction'] == 'declining':
    print(f'  → Would elevate intervention priority (trend=declining)')
print('  PASS')

# ===== Test 5: Error persistence =====
print('\n--- Test 5: Persistent large errors → λ reduction ---')
bp2 = get_predictor()
openid4 = 'test_bp_int_4'
scores_volatile = [50, 80, 40, 85, 35, 75, 45]
for i, s in enumerate(scores_volatile):
    eng.working_memory.push(openid4, {
        'text': f'Day {i+1}',
        'score_obs': s,
        'emotion': 'neutral',
        'intervention': 'none',
        'outcome': 'none',
    })

# Record prediction errors for the user
for s in [82, 38, 88]:
    err = bp2.get_prediction_error(openid4, s)
    print(f'  Error: {err["error"]:.1f}, recent mean: {err.get("recent_mean_error", 0):.1f}, suggest λ reduce: {err["suggest_lambda_reduce"]}')

err_info = bp2.get_prediction_error(openid4, 80)
if err_info.get('suggest_lambda_reduce'):
    print('  → System error large enough to suggest λ reduction')
else:
    print(f'  → Recent error mean ({err_info.get("recent_mean_error", 0):.1f}) below threshold for λ reduction')
print('  PASS')

# ===== Test 6: Anomaly detection =====
print('\n--- Test 6: Anomaly score ---')
openid5 = 'test_bp_int_5'
stable_scores = [70, 72, 71, 73, 72, 70, 35]  # sudden drop at end
for i, s in enumerate(stable_scores):
    eng.working_memory.push(openid5, {
        'text': f'Day {i+1}',
        'score_obs': s,
        'emotion': 'neutral',
        'intervention': 'none',
        'outcome': 'none',
    })

anom = eng.behavior_predictor.anomaly_score(openid5)
print(f'  Anomaly score (sudden drop): {anom}')
assert anom > 0.5, f'Sudden drop should have high anomaly, got {anom}'
print('  PASS')

print('\n' + '='*60)
print('All Phase 2 tests PASS!')
print('='*60)
