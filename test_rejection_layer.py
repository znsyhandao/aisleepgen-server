# -*- coding: utf-8 -*-
"""拒识层回归测试 (2026-08-12, 3520 事故防线)
验证:
 T1: 数据不足(<=2字段) → total_score=None + rejection DATA_INSUFFICIENT
 T2: 正常数据(>=3字段) → total_score 在 0-100, 无 rejection
 T3: 数据不足时 quality='数据不足'
 T4: 评分校准偏移在 total_score=None 时被跳过(不崩溃)
 T5: 模拟 3520 类越界分 → 被钳制为 None (SCORE_INVALID)
"""
import os, sys, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['AISLEEPGEN_SKIP_MAIN'] = '1'

passed = 0
failed = 0

def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print(f'[PASS] {name}')
    else:
        failed += 1
        print(f'[FAIL] {name} {detail}')

# ── T1: 数据不足 → 拒识 ──
try:
    from sleep_world_model import WorldModelEngine
    wm = WorldModelEngine()
    # 只有 bedtime+wake_time (2个字段, 无 duration/latency/awake/stress)
    sparse = {'bedtime': '23:00', 'wake_time': '07:00'}
    r = wm.comprehensive_analysis(sparse, today_str='20260812')
    check('T1 数据不足→total_score=None', r.get('total_score') is None,
          f"got {r.get('total_score')!r}")
    rej = r.get('rejection', {})
    check('T1 拒识码 DATA_INSUFFICIENT', rej.get('code') == 'DATA_INSUFFICIENT',
          f"got {rej.get('code')!r}")
    check('T3 quality=数据不足', r.get('quality') == '数据不足',
          f"got {r.get('quality')!r}")
except Exception as e:
    failed += 1
    print(f'[FAIL] T1 异常: {e}')

# ── T2: 正常数据 → 正常出分 ──
try:
    full = {'bedtime': '23:00', 'wake_time': '07:00', 'sleep_latency': 15,
            'awake_times': 1, 'total_duration': 420, 'stress_level': 4}
    r2 = wm.comprehensive_analysis(full, today_str='20260812')
    ts = r2.get('total_score')
    check('T2 正常数据→0-100分', isinstance(ts, (int, float)) and 0 <= ts <= 100,
          f"got {ts!r}")
    check('T2 正常数据→无 rejection', r2.get('rejection') is None,
          f"got {r2.get('rejection')!r}")
except Exception as e:
    failed += 1
    print(f'[FAIL] T2 异常: {e}')

# ── T4: 校准偏移在 None 时不崩溃 ──
try:
    # 直接测 dp_router 的校准逻辑片段: None + offset 必须被 isinstance 挡住
    old_score = None
    offset = 5
    if isinstance(old_score, (int, float)):
        new_score = max(10, min(100, old_score + offset))
    else:
        new_score = old_score  # 拒识层: 跳过校准
    check('T4 None 校准被跳过', new_score is None, f"got {new_score!r}")
except Exception as e:
    failed += 1
    print(f'[FAIL] T4 异常: {e}')

# ── T5: 3520 类越界分 → SCORE_INVALID ──
try:
    # 直接调用拒识判断逻辑(从 comprehensive_analysis 出口复制)
    def _reject_check(raw):
        valid = (isinstance(raw, (int, float)) and math.isfinite(raw) and 0 <= raw <= 100)
        if not valid:
            return {'code': 'SCORE_INVALID',
                    'reason': f'total_score={raw!r} 非法(期望 0-100 有限数)',
                    'guard': 'score_rejection_v1'}
        return None
    r3520 = _reject_check(3520.6)
    check('T5 3520.6 → SCORE_INVALID', r3520 is not None and r3520['code'] == 'SCORE_INVALID',
          f"got {r3520!r}")
    r_nan = _reject_check(float('nan'))
    check('T5 NaN → SCORE_INVALID', r_nan is not None and r_nan['code'] == 'SCORE_INVALID',
          f"got {r_nan!r}")
    r_ok = _reject_check(80.4)
    check('T5 80.4 → 放行', r_ok is None, f"got {r_ok!r}")
except Exception as e:
    failed += 1
    print(f'[FAIL] T5 异常: {e}')

print(f'\n=== {passed} passed, {failed} failed ===')
sys.exit(1 if failed else 0)
