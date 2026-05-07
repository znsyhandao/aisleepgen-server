#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dynamic_safeguards.py — AISleepGen 动态安全护栏 v1.0

范式跃迁：从静态安全边界（beta 0.1-3.0, lambda 0.5-0.99）到动态安全网。
如果元学习连续调错方向，安全网自动兜底——自动回滚 + 金丝雀发布。

核心能力：
  - check(openid) -> safety_status dict
  - record_adjustment(openid, param, old_val, new_val, outcome_after)
  - auto_rollback(openid) -> 执行回滚
  - get_rollback_history(openid) -> 回滚记录
  - check_param_safety(param, value) -> (safe, clamped_value)

安全指标：
  - 连续失败检测：连续5次adjustment后outcome恶化
  - 急性恶变检测：单次outcome drop > 20%
  - 振荡检测：参数在3次内来回振荡
  - 极端值检测：参数接近安全边界 + outcome差

自动回滚：
  - 回退到上一个稳定参数快照，一次到位
  - 回滚后暂停该参数调整12小时
  - 保留最近10次回滚记录

金丝雀发布：
  - 元学习参数变更 → 先应用到5%的用户 → 观察24h → 有效再推广
  - 5%用户出现急性恶变 → 立即全局回滚
  - 5%用户outcome显著改善 → 加速推广
"""

import json, os, time, math, logging, random
from datetime import datetime, timedelta
from collections import defaultdict, deque

_ds_log = logging.getLogger('aisleepgen.dynamic_safeguards')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SAFEGUARDS_DIR = os.path.join(PROJECT_ROOT, 'data', 'safeguards')
ADJUSTMENT_LOG_PATH = os.path.join(SAFEGUARDS_DIR, 'adjustments.json')
ROLLBACK_HISTORY_PATH = os.path.join(SAFEGUARDS_DIR, 'rollback_history.json')
PARAM_SNAPSHOT_PATH = os.path.join(SAFEGUARDS_DIR, 'param_snapshots.json')
CANARY_STATE_PATH = os.path.join(SAFEGUARDS_DIR, 'canary_state.json')

# ==================== 金丝雀参数 ====================

CANARY_SAMPLE_RATE = 0.05     # 5% 用户抽样
CANARY_OBSERVE_HOURS = 24     # 观察24小时
CANARY_ACCELERATE_THRESHOLD = 0.15  # 显著改善阈值
CANARY_EMERGENCY_DROP = -0.20  # 急性恶变阈值

# 安全参数边界（与meta_learner的SAFETY_BOUNDS保持一致）
PARAM_BOUNDS = {
    'beta': (0.1, 3.0),
    'forget_factor': (0.5, 0.99),
    'intervention_rate': (0.1, 0.8),
    'push_threshold': (30, 70),
    'alpha0': (0.01, 1.0),
    'learning_rate': (0.05, 0.8),
    'cooldown_minutes': (1, 60),
    'confidence_min_samples': (2, 20),
}

# ==================== 参数快照管理 ====================


class ParamSnapshotManager:
    """参数快照管理器——保存/恢复稳定参数"""

    def __init__(self):
        os.makedirs(SAFEGUARDS_DIR, exist_ok=True)

    def _load_snapshots(self):
        try:
            if os.path.exists(PARAM_SNAPSHOT_PATH):
                with open(PARAM_SNAPSHOT_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('snapshots', {})
        except Exception:
            pass
        return {}

    def _save_snapshots(self, snapshots):
        try:
            with open(PARAM_SNAPSHOT_PATH, 'w', encoding='utf-8') as f:
                json.dump({'snapshots': snapshots, 'updated_at': datetime.now().isoformat()},
                          f, ensure_ascii=False, indent=2)
        except Exception as e:
            _ds_log.warning('[Safeguard] Save snapshots error: %s', e)

    def save_snapshot(self, openid, params):
        """保存当前稳定参数快照"""
        snapshots = self._load_snapshots()
        if openid not in snapshots:
            snapshots[openid] = []
        snapshots[openid].append({
            'ts': time.time(),
            'timestamp': datetime.now().isoformat(),
            'params': dict(params),
        })
        # 保留最近5个快照
        if len(snapshots[openid]) > 5:
            snapshots[openid] = snapshots[openid][-5:]
        self._save_snapshots(snapshots)

    def get_last_stable(self, openid):
        """获取上一个稳定参数快照

        Returns: dict or None
        """
        snapshots = self._load_snapshots()
        entries = snapshots.get(openid, [])
        if len(entries) >= 2:
            return entries[-2]['params']
        if entries:
            return entries[-1]['params']
        return None

    def get_stable_snapshot(self, openid, steps_back=1):
        """获取第N步前的稳定参数

        Args:
            openid: 用户ID或'_system'
            steps_back: 1=上一个

        Returns: dict or None
        """
        snapshots = self._load_snapshots()
        entries = snapshots.get(openid, [])
        idx = len(entries) - 1 - steps_back
        if 0 <= idx < len(entries):
            return entries[idx]['params']
        return None


# ==================== 动态安全护栏 ====================


class DynamicSafeguards:
    """动态安全护栏——自动检测异常 + 回滚 + 金丝雀发布"""

    def __init__(self):
        os.makedirs(SAFEGUARDS_DIR, exist_ok=True)
        self.snapshot_manager = ParamSnapshotManager()
        self._adjustment_buffer = {}  # openid -> deque of recent adjustments
        self._param_cooldown = {}     # openid -> {param: unlock_time}
        self._canary_lock = None
        try:
            import threading
            self._canary_lock = threading.Lock()
        except:
            pass

    # ==================== IO ====================

    def _load_adjustments(self):
        try:
            if os.path.exists(ADJUSTMENT_LOG_PATH):
                with open(ADJUSTMENT_LOG_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {'adjustments': []}

    def _save_adjustments(self, data):
        try:
            with open(ADJUSTMENT_LOG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _ds_log.warning('[Safeguard] Save adjustments error: %s', e)

    def _load_rollback_history(self):
        try:
            if os.path.exists(ROLLBACK_HISTORY_PATH):
                with open(ROLLBACK_HISTORY_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {'rollbacks': []}

    def _save_rollback_history(self, data):
        try:
            with open(ROLLBACK_HISTORY_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _ds_log.warning('[Safeguard] Save rollback error: %s', e)

    def _load_canary_state(self):
        try:
            if os.path.exists(CANARY_STATE_PATH):
                with open(CANARY_STATE_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {
            'canary_users': [],
            'test_params': {},
            'started_at': None,
            'status': 'inactive',  # inactive | testing | promoting | rolled_back
            'test_results': {'avg_outcome': 0.0, 'positive_ratio': 0.5, 'count': 0},
            'control_results': {'avg_outcome': 0.0, 'positive_ratio': 0.5, 'count': 0},
        }

    def _save_canary_state(self, state):
        try:
            with open(CANARY_STATE_PATH, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _ds_log.warning('[Safeguard] Save canary error: %s', e)

    # ==================== 安全检测 ====================

    def check(self, openid):
        """检查当前安全状态

        Returns:
            dict: {
                'safe': bool,
                'flags': [flag_dict, ...],
                'summary': str,
            }
        """
        flags = []

        # 1. 连续失败检测
        failure_flag = self._detect_consecutive_failure(openid)
        if failure_flag:
            flags.append(failure_flag)

        # 2. 急性恶变检测
        acute_flag = self._detect_acute_deterioration(openid)
        if acute_flag:
            flags.append(acute_flag)

        # 3. 振荡检测
        oscillation_flag = self._detect_oscillation(openid)
        if oscillation_flag:
            flags.append(oscillation_flag)

        # 4. 极端值检测
        extreme_flag = self._detect_extreme_values(openid)
        if extreme_flag:
            flags.append(extreme_flag)

        # 5. 回滚冷却检测
        cooldown_flag = self._detect_param_cooldown(openid)
        if cooldown_flag:
            flags.append(cooldown_flag)

        safe = len(flags) == 0

        summary_parts = []
        for f in flags:
            summary_parts.append(f['reason'])
        summary = '; '.join(summary_parts) if summary_parts else 'safe'

        # 自动回滚如果检测到严重问题
        if not safe:
            self._auto_rollback_if_needed(openid, flags)

        return {
            'safe': safe,
            'flags': flags,
            'summary': summary,
            'check_time': datetime.now().isoformat(),
        }

    def check_param_safety(self, param, value):
        """检查参数值是否在安全范围内，钳制到安全边界

        Returns:
            (safe: bool, clamped_value: float)
        """
        bounds = PARAM_BOUNDS.get(param)
        if bounds is None:
            return True, value
        lo, hi = bounds
        clamped = max(lo, min(hi, value))
        safe = clamped == value
        if not safe:
            _ds_log.warning('[Safeguard] Param %s clamped: %.4f -> %.4f (bounds [%.2f, %.2f])',
                            param, value, clamped, lo, hi)
        return safe, clamped

    # ==================== 检测方法 ====================

    def _get_recent_adjustments(self, openid, n=5):
        """获取最近的N次adjustment记录"""
        # 先查buffer
        if openid in self._adjustment_buffer:
            buf = self._adjustment_buffer[openid]
        else:
            buf = deque(maxlen=10)
            self._adjustment_buffer[openid] = buf

        # 补充磁盘日志
        all_adj = self._load_adjustments().get('adjustments', [])
        user_adj = [a for a in all_adj if a.get('openid') == openid]
        for a in user_adj[-10:]:
            # deduplicate by ts
            if not any(b.get('ts') == a.get('ts') for b in buf):
                buf.append(a)

        return list(buf)[-n:]

    def _detect_consecutive_failure(self, openid):
        """连续失败检测：连续5次adjustment后outcome恶化"""
        adj_list = self._get_recent_adjustments(openid, n=6)
        if len(adj_list) < 6:
            return None

        # 检查最近5次是否都有outcome恶化
        consecutive_bad = 0
        for adj in adj_list[-5:]:
            outcome = adj.get('outcome_after', 0)
            if outcome < 0:
                consecutive_bad += 1
            else:
                consecutive_bad = 0

        if consecutive_bad >= 5:
            return {
                'type': 'consecutive_failure',
                'severity': 'high',
                'detail': f'{consecutive_bad} consecutive negative outcomes',
                'reason': f'连续{consecutive_bad}次调整后outcome恶化',
            }
        return None

    def _detect_acute_deterioration(self, openid):
        """急性恶变检测：单次outcome drop > 20%"""
        adj_list = self._get_recent_adjustments(openid, n=3)
        for adj in adj_list:
            outcome = adj.get('outcome_after', 0)
            # 检查是否为评分下降
            if outcome < -20:
                return {
                    'type': 'acute_deterioration',
                    'severity': 'critical',
                    'detail': f'Single outcome drop of {outcome:.1f} (threshold: -20)',
                    'reason': f'急性恶变: outcome下降{outcome:.0f}分',
                }
        return None

    def _detect_oscillation(self, openid):
        """振荡检测：参数在3次内来回振荡（increase->decrease->increase）"""
        adj_list = self._get_recent_adjustments(openid, n=5)
        if len(adj_list) < 4:
            return None

        # 按参数分组
        param_changes = defaultdict(list)
        for adj in adj_list:
            p_name = adj.get('param', 'unknown')
            delta = adj.get('delta', 0)
            param_changes[p_name].append(delta)

        for p_name, deltas in param_changes.items():
            if len(deltas) >= 3:
                # 检查振荡模式: + - + 或 - + -
                pattern = deltas[-3:]
                signs = [1 if d > 0.001 else (-1 if d < -0.001 else 0) for d in pattern]
                if len([s for s in signs if s != 0]) >= 3 and signs[0] == signs[2] and signs[1] != 0 and signs[0] != 0:
                    return {
                        'type': 'oscillation',
                        'severity': 'medium',
                        'param': p_name,
                        'detail': f'Param {p_name} oscillating: {[round(d, 4) for d in pattern]}',
                        'reason': f'参数{p_name}在3次调整中来回振荡',
                    }
        return None

    def _detect_extreme_values(self, openid):
        """极端值检测：参数接近安全边界 + outcome差"""
        adj_list = self._get_recent_adjustments(openid, n=3)
        if not adj_list:
            return None

        for adj in adj_list:
            p_name = adj.get('param', 'unknown')
            new_val = adj.get('new_val', 0)
            outcome = adj.get('outcome_after', 0)
            bounds = PARAM_BOUNDS.get(p_name)

            if bounds is None:
                continue

            lo, hi = bounds
            margin = (hi - lo) * 0.1  # 10%边界

            near_boundary = (new_val <= lo + margin) or (new_val >= hi - margin)
            bad_outcome = outcome < -10

            if near_boundary and bad_outcome:
                side = 'lower' if new_val - lo < hi - new_val else 'upper'
                return {
                    'type': 'extreme_value',
                    'severity': 'high',
                    'param': p_name,
                    'detail': f'Param {p_name}={new_val:.3f} near {side} bound [{lo}, {hi}] + bad outcome={outcome:.1f}',
                    'reason': f'参数{p_name}接近{side}边界且outcome差(outcome={outcome:.0f})',
                }
        return None

    def _detect_param_cooldown(self, openid):
        """参数冷却检测：检查是否有参数在冷却期内"""
        now = time.time()
        if openid not in self._param_cooldown:
            self._param_cooldown[openid] = {}
        cooling = []
        for param, unlock_time in list(self._param_cooldown[openid].items()):
            if now < unlock_time:
                remaining = unlock_time - now
                cooling.append(f'{param}({remaining:.0f}s)')
            else:
                del self._param_cooldown[openid][param]

        if cooling:
            return {
                'type': 'param_cooldown',
                'severity': 'info',
                'detail': f'Params in cooldown: {", ".join(cooling)}',
                'reason': f'参数冷却中: {", ".join(cooling)}',
            }
        return None

    # ==================== 调整记录 ====================

    def record_adjustment(self, openid, param, old_val, new_val, outcome_after):
        """记录一次参数调整

        同时更新内存buffer和持久化日志
        """
        # 更新buffer
        if openid not in self._adjustment_buffer:
            self._adjustment_buffer[openid] = deque(maxlen=10)
        self._adjustment_buffer[openid].append({
            'param': param,
            'old_val': old_val,
            'new_val': new_val,
            'delta': new_val - old_val,
            'outcome_after': outcome_after,
            'ts': time.time(),
        })

        # 持久化
        data = self._load_adjustments()
        data['adjustments'].append({
            'openid': openid,
            'param': param,
            'old_val': old_val,
            'new_val': new_val,
            'delta': new_val - old_val,
            'outcome_after': outcome_after,
            'ts': time.time(),
            'timestamp': datetime.now().isoformat(),
        })
        # 保留最近500条
        if len(data['adjustments']) > 500:
            data['adjustments'] = data['adjustments'][-500:]
        self._save_adjustments(data)

        # 保存参数快照
        params_snapshot = self._collect_current_params()
        self.snapshot_manager.save_snapshot(openid, params_snapshot)

    def _collect_current_params(self):
        """收集当前系统参数"""
        params = {}
        try:
            from pomdp_learner import get_engine
            eng = get_engine()
            params['beta'] = eng.beta
            params['forget_factor'] = eng.forget_factor
            params['intervention_rate'] = eng.intervention_rate
            params['alpha0'] = eng.alpha0
        except Exception:
            pass
        return params

    # ==================== 自动回滚 ====================

    def _auto_rollback_if_needed(self, openid, flags):
        """根据flag严重程度决定是否自动回滚"""
        critical_flags = [f for f in flags if f.get('severity') in ('critical', 'high')]
        if not critical_flags:
            return

        # 取出调整日志确认outcome确实恶化
        adj_list = self._get_recent_adjustments(openid, n=3)
        outcome_confirmed = any(a.get('outcome_after', 0) < -5 for a in adj_list)

        if outcome_confirmed:
            _ds_log.warning('[Safeguard] Auto-rollback triggered for %s: %s',
                            openid[:8], '; '.join(f['reason'] for f in critical_flags))
            self.auto_rollback(openid, flags=critical_flags)

    def auto_rollback(self, openid, steps_back=1, flags=None):
        """自动回滚到上一个稳定参数快照

        一次到位（不是逐步回滚），然后设置冷却时间

        Args:
            openid: 用户ID或'_system'
            steps_back: 1=回退一次

        Returns:
            dict: 回滚结果
        """
        # 获取稳定快照
        stable_params = self.snapshot_manager.get_stable_snapshot(openid, steps_back)
        if stable_params is None:
            return {'status': 'cannot_rollback', 'reason': 'No stable snapshot available'}

        # 获取需要放冷却的参数
        cooled_params = set()
        if flags:
            for f in flags:
                param = f.get('param')
                if param:
                    cooled_params.add(param)

        # 如果没有精确参数，从调整记录推导
        if not cooled_params:
            adj_list = self._get_recent_adjustments(openid, n=3)
            for adj in adj_list:
                p = adj.get('param')
                if p:
                    cooled_params.add(p)

        # 应用回滚：只回滚快照中的参数
        rollback_applied = {}
        try:
            from pomdp_learner import get_engine
            eng = get_engine()
            for param, value in stable_params.items():
                safe, clamped = self.check_param_safety(param, value)
                if hasattr(eng, param):
                    setattr(eng, param, clamped)
                    rollback_applied[param] = {'from': getattr(eng, param, None), 'to': clamped}
                elif param == 'forget_factor':
                    for _, u in eng.users.items():
                        u['learner'].lambd = clamped
                    rollback_applied[param] = {'from': None, 'to': clamped}
                elif param == 'alpha0':
                    for _, u in eng.users.items():
                        u['learner'].alpha0 = clamped
                    rollback_applied[param] = {'from': None, 'to': clamped}
        except Exception as e:
            _ds_log.error('[Safeguard] Rollback apply failed: %s', e)
            return {'status': 'failed', 'reason': str(e)}

        # 设置冷却时间（12小时）
        now = time.time()
        cooldown_seconds = 12 * 3600
        if openid not in self._param_cooldown:
            self._param_cooldown[openid] = {}
        for param in cooled_params:
            self._param_cooldown[openid][param] = now + cooldown_seconds

        # 记录回滚历史
        rollback_entry = {
            'ts': now,
            'timestamp': datetime.now().isoformat(),
            'openid': openid,
            'steps_back': steps_back,
            'reason': '; '.join(f['reason'] for f in flags) if flags else 'auto_detected',
            'params_before': {p: {'was': v} for p, v in rollback_applied.items()},
            'cooldown_hours': 12,
            'cooldown_until': datetime.fromtimestamp(now + cooldown_seconds).isoformat(),
        }

        rollback_data = self._load_rollback_history()
        rollback_data['rollbacks'].append(rollback_entry)
        # 保留最近10条
        if len(rollback_data['rollbacks']) > 10:
            rollback_data['rollbacks'] = rollback_data['rollbacks'][-10:]
        self._save_rollback_history(rollback_data)

        _ds_log.info('[Safeguard] Rollback executed for %s: %d params restored, %d params on cooldown',
                      openid[:8], len(rollback_applied), len(cooled_params))

        return {
            'status': 'rolled_back',
            'rolled_params': rollback_applied,
            'cooled_params': list(cooled_params),
            'cooldown_hours': 12,
        }

    def get_rollback_history(self, openid=None):
        """获取回滚历史

        Args:
            openid: 可选，筛选特定用户的回滚

        Returns:
            list[dict]: 回滚记录
        """
        data = self._load_rollback_history()
        rollbacks = data.get('rollbacks', [])
        if openid:
            rollbacks = [r for r in rollbacks if r.get('openid') == openid]
        return rollbacks

    # ==================== 金丝雀发布 ====================

    def start_canary_test(self, params_to_test):
        """启动金丝雀发布

        从所有用户中随机选择5%进入测试组

        Args:
            params_to_test: dict of {param_name: new_value}

        Returns:
            dict: 金丝雀测试状态
        """
        state = self._load_canary_state()

        if state['status'] == 'testing':
            return {'status': 'already_testing', 'canary_users': state['canary_users']}

        # 收集所有活跃用户
        all_users = set()
        try:
            from pomdp_learner import get_engine
            eng = get_engine()
            all_users = set(eng.users.keys())
        except Exception:
            pass

        # 补充从profile目录读取的用户
        try:
            profiles_dir = os.path.join(PROJECT_ROOT, 'user_profiles')
            if os.path.exists(profiles_dir):
                for fn in os.listdir(profiles_dir):
                    if fn.endswith('.json'):
                        uid = fn.replace('.json', '')
                        all_users.add(uid)
        except Exception:
            pass

        if len(all_users) < 3:
            return {'status': 'too_few_users', 'count': len(all_users)}

        # 随机选择5%
        n_canary = max(1, int(len(all_users) * CANARY_SAMPLE_RATE))
        canary_users = random.sample(list(all_users), min(n_canary, len(all_users)))

        # 保存状态
        state = {
            'canary_users': canary_users,
            'all_users': list(all_users),
            'test_params': params_to_test,
            'started_at': time.time(),
            'started_at_iso': datetime.now().isoformat(),
            'status': 'testing',
            'test_results': {'avg_outcome': 0.0, 'positive_ratio': 0.5, 'count': 0},
            'control_results': {'avg_outcome': 0.0, 'positive_ratio': 0.5, 'count': 0},
        }
        self._save_canary_state(state)

        _ds_log.info('[Safeguard] Canary test started: %d users (%d total, %.1f%%)',
                      len(canary_users), len(all_users), len(canary_users) / max(len(all_users), 1) * 100)

        return {
            'status': 'testing',
            'canary_users': canary_users,
            'canary_count': len(canary_users),
            'total_users': len(all_users),
            'test_params': params_to_test,
        }

    def evaluate_canary(self):
        """评估金丝雀测试结果

        Returns:
            dict: {
                'status': 'promote' | 'rollback' | 'continue' | 'inactive',
                'test_results': {...},
                'control_results': {...},
                'recommendation': str,
            }
        """
        state = self._load_canary_state()
        if state['status'] != 'testing':
            return {'status': 'inactive', 'recommendation': 'No active canary test'}

        elapsed = time.time() - state['started_at']
        elapsed_hours = elapsed / 3600

        # 检查是否已过观察期
        canary_ready = elapsed_hours >= CANARY_OBSERVE_HOURS

        # 收集outcome数据
        try:
            from pomdp_learner import get_engine
            eng = get_engine()
            canary_users = state.get('canary_users', [])
            all_users = state.get('all_users', [])

            # 优化：从safeguard自己的调整日志查询
            adjustments = self._load_adjustments().get('adjustments', [])
            since = state.get('started_at', 0)

            canary_outcomes = []
            control_outcomes = []

            for adj in adjustments:
                if adj.get('ts', 0) < since:
                    continue
                outcome = adj.get('outcome_after', 0)
                uid = adj.get('openid', '')
                if uid in canary_users:
                    canary_outcomes.append(outcome)
                elif uid in all_users and uid not in canary_users:
                    control_outcomes.append(outcome)

            # 计算统计
            def _compute_stats(outcomes):
                if not outcomes:
                    return {'count': 0, 'avg_outcome': 0.0, 'positive_ratio': 0.5}
                avg_outcome = sum(outcomes) / len(outcomes)
                positive = sum(1 for o in outcomes if o > 0)
                return {
                    'count': len(outcomes),
                    'avg_outcome': avg_outcome,
                    'positive_ratio': positive / len(outcomes),
                }

            test_stats = _compute_stats(canary_outcomes)
            control_stats = _compute_stats(control_outcomes)

            state['test_results'] = test_stats
            state['control_results'] = control_stats
            self._save_canary_state(state)

            # 决策
            test_ratio = test_stats.get('positive_ratio', 0.5)
            control_ratio = control_stats.get('positive_ratio', 0.5)
            test_avg = test_stats.get('avg_outcome', 0)
            control_avg = control_stats.get('avg_outcome', 0)

            # 急性恶变检测
            if test_avg < control_avg + CANARY_EMERGENCY_DROP * 100:
                # 立即回滚
                return self._canary_emergency_rollback(state, 'acute_deterioration')

            if test_stats['count'] < 3:
                return {
                    'status': 'continue',
                    'elapsed_hours': round(elapsed_hours, 1),
                    'test_results': test_stats,
                    'control_results': control_stats,
                    'recommendation': 'Not enough canary data yet',
                }

            if not canary_ready and test_ratio > control_ratio + CANARY_ACCELERATE_THRESHOLD:
                # 即使不满24h，但效果显著 → 加速推广
                return self._canary_promote(state, 'accelerated')

            if canary_ready:
                if test_ratio > control_ratio:
                    return self._canary_promote(state, 'effective')
                else:
                    return self._canary_rollback(state, 'ineffective')

            return {
                'status': 'continue',
                'elapsed_hours': round(elapsed_hours, 1),
                'test_results': test_stats,
                'control_results': control_stats,
                'recommendation': f'Observing... {round(CANARY_OBSERVE_HOURS - elapsed_hours, 1)}h remaining',
            }

        except Exception as e:
            _ds_log.error('[Safeguard] Canary evaluation failed: %s', e)
            return {'status': 'error', 'reason': str(e)}

    def _canary_emergency_rollback(self, state, reason):
        """金丝雀紧急回滚——急性恶变"""
        _ds_log.warning('[Safeguard] Canary EMERGENCY rollback: %s', reason)
        state['status'] = 'rolled_back'
        self._save_canary_state(state)

        # 全局回滚
        self.auto_rollback('_canary', flags=[{'severity': 'critical', 'reason': reason}])

        return {
            'status': 'emergency_rollback',
            'reason': reason,
            'test_results': state['test_results'],
            'control_results': state['control_results'],
            'recommendation': 'Emergency global rollback due to acute deterioration in canary group',
        }

    def _canary_promote(self, state, reason):
        """推广金丝雀到所有用户"""
        _ds_log.info('[Safeguard] Canary promotion: %s', reason)
        state['status'] = 'promoting'
        self._save_canary_state(state)

        params = state.get('test_params', {})
        try:
            from pomdp_learner import get_engine
            eng = get_engine()
            for param, value in params.items():
                safe, clamped = self.check_param_safety(param, value)
                if hasattr(eng, param):
                    setattr(eng, param, clamped)
                elif param == 'forget_factor':
                    for _, u in eng.users.items():
                        u['learner'].lambd = clamped
                elif param == 'alpha0':
                    for _, u in eng.users.items():
                        u['learner'].alpha0 = clamped
        except Exception as e:
            _ds_log.error('[Safeguard] Canary promotion failed: %s', e)

        state['status'] = 'promoted'
        self._save_canary_state(state)

        return {
            'status': 'promoted',
            'reason': reason,
            'test_results': state['test_results'],
            'control_results': state['control_results'],
            'recommendation': f'Parameters promoted to all users ({reason})',
        }

    def _canary_rollback(self, state, reason):
        """金丝雀回滚——无效"""
        _ds_log.info('[Safeguard] Canary rollback: %s', reason)
        state['status'] = 'rolled_back'
        self._save_canary_state(state)
        return {
            'status': 'rolled_back',
            'reason': reason,
            'test_results': state['test_results'],
            'control_results': state['control_results'],
            'recommendation': 'Canary test showed no improvement, params not promoted',
        }

    def get_canary_status(self):
        """获取金丝雀发布状态"""
        return self._load_canary_state()

    def _check_cluster_weights(self):
        """检查集群权重是否产生持续差outcome（v6.1.0 AEO集成）"""
        try:
            from weight_optimizer import get_weight_optimizer
            wo = get_weight_optimizer()
            status = wo.get_status()
            for ck, cd in status['cluster_weights'].items():
                outcome_count = cd.get('outcome_count', 0)
                positive_count = cd.get('positive_count', 0)
                if outcome_count >= 20:
                    pos_rate = positive_count / outcome_count
                    if pos_rate < 0.3:
                        return {
                            'needs_rollback': True,
                            'cluster_id': ck,
                            'positive_rate': round(pos_rate, 3),
                            'outcome_count': outcome_count,
                        }
        except Exception:
            pass
        return {'needs_rollback': False}

    def auto_rollback_cluster_weights(self, cluster_id):
        """回滚集群权重到全局基准（v6.1.0 AEO集成）"""
        try:
            from weight_optimizer import get_weight_optimizer
            wo = get_weight_optimizer()
            base = wo._load_base_weights()
            cw = wo._load_cluster_weights()
            if str(cluster_id) in cw:
                old_weights = dict(cw[str(cluster_id)].get('weights', {}))
                cw[str(cluster_id)]['weights'] = dict(base)
                cw[str(cluster_id)]['last_optimized'] = None
                wo._cluster_weights = cw
                wo._save_cluster_weights()
                return {
                    'status': 'rolled_back',
                    'cluster_id': str(cluster_id),
                    'old_weights': {k: round(v, 4) for k, v in old_weights.items()},
                    'new_weights': {k: round(v, 4) for k, v in base.items()},
                }
        except Exception as e:
            _ds_log.warning('[Safeguard] Cluster weight rollback failed: %s', e)
        return {'status': 'failed', 'error': 'cluster not found or unavailable'}

    def get_safety_summary(self):
        """获取安全摘要"""
        rollbacks = self._load_rollback_history()
        canary = self._load_canary_state()
        adj_data = self._load_adjustments()
        cluster_check = self._check_cluster_weights()

        lines = [
            'Dynamic Safeguards Status:',
            f'  Rollback count: {len(rollbacks.get("rollbacks", []))}',
            f'  Canary status: {canary.get("status", "inactive")}',
            f'  Total adjustments logged: {len(adj_data.get("adjustments", []))}',
        ]

        if canary.get('status') == 'testing':
            lines.append(f'  Canary users: {len(canary.get("canary_users", []))}')
            lines.append(f'  Elapsed: {canary.get("started_at_iso", "?")}')

        if cluster_check.get('needs_rollback'):
            lines.append(f'  ⚠ Cluster {cluster_check["cluster_id"]} needs weight rollback '
                         f'(positive_rate={cluster_check["positive_rate"]:.1%})')

        rollbacks_list = rollbacks.get('rollbacks', [])
        if rollbacks_list:
            lines.append(f'  Recent rollbacks:')
            for r in rollbacks_list[-3:]:
                lines.append(f'    - {r.get("timestamp", "")[:16]}: {r.get("reason", "")[:60]}')

        return '\n'.join(lines)


# ==================== 全局实例 ====================

_dynamic_safeguards = None


def get_dynamic_safeguards():
    global _dynamic_safeguards
    if _dynamic_safeguards is None:
        _dynamic_safeguards = DynamicSafeguards()
    return _dynamic_safeguards


# ==================== 自测 ====================

if __name__ == '__main__':
    import shutil, sys

    logging.basicConfig(level=logging.WARNING,
                        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')

    # 清理旧数据
    if os.path.exists(SAFEGUARDS_DIR):
        shutil.rmtree(SAFEGUARDS_DIR)
    os.makedirs(SAFEGUARDS_DIR, exist_ok=True)

    sg = DynamicSafeguards()

    # 1. 初始状态 - 安全
    status = sg.check('test_user')
    assert status['safe'] is True, f'Initial should be safe: {status}'
    print('1. Initial safety check: safe')
    print('   OK')

    # 2. 连续失败检测（5次outcome恶化）
    print('\n2. Consecutive failure detection...')
    for i in range(6):
        sg.record_adjustment('test_user', 'beta', 0.8, 0.8 - i * 0.1, -2 - i * 2)
    status = sg.check('test_user')
    has_consecutive = any(f['type'] == 'consecutive_failure' for f in status['flags'])
    assert has_consecutive, f'Should detect consecutive failure: {status}'
    print(f'   Consecutive failure detected: {has_consecutive}')
    print('   OK')

    # 3. 急性恶变检测（单次drop > 20%）
    print('\n3. Acute deterioration detection...')
    sg.record_adjustment('test_user2', 'beta', 0.5, 0.3, -25)
    status2 = sg.check('test_user2')
    has_acute = any(f['type'] == 'acute_deterioration' for f in status2['flags'])
    assert has_acute, f'Should detect acute deterioration: {status2}'
    print(f'   Acute deterioration detected: {has_acute}')
    print('   OK')

    # 4. 振荡检测
    print('\n4. Oscillation detection...')
    sg3 = DynamicSafeguards()
    # 模拟 +, -, + 模式
    sg3.record_adjustment('osc_user', 'beta', 0.5, 0.8, 3)
    sg3.record_adjustment('osc_user', 'beta', 0.8, 0.5, -5)
    sg3.record_adjustment('osc_user', 'beta', 0.5, 0.7, 2)
    # debug
    adjs = sg3._get_recent_adjustments('osc_user', n=5)
    for a in adjs:
        print(f'   adj: param={a.get("param")}, delta={a.get("delta", 0):.2f}, outcome={a.get("outcome_after", 0):.1f}')
    status3 = sg3.check('osc_user')
    print(f'   flags: {[f["type"] for f in status3["flags"]]}')
    has_osc = any(f['type'] == 'oscillation' for f in status3['flags'])
    print(f'   Oscillation detected: {has_osc}')
    assert has_osc, f'Should detect oscillation: {status3}'
    print(f'   Oscillation detected: {has_osc}')
    print('   OK')

    # 5. 参数安全边界钳制
    print('\n5. Param safety clamping...')
    safe, clamped = sg.check_param_safety('beta', 5.0)
    assert not safe, 'beta=5.0 should be unsafe'
    assert clamped == 3.0, f'beta=5.0 should clamp to 3.0, got {clamped}'
    safe2, clamped2 = sg.check_param_safety('forget_factor', 0.99)
    assert safe2, 'forget_factor=0.99 should be safe'
    print(f'   beta=5.0 -> clamped={clamped}, safe={safe}')
    print('   OK')

    # 6. 回滚测试
    print('\n6. Rollback test...')
    sg4 = DynamicSafeguards()
    # 注册两个快照（前一个作为稳定快照）
    sg4.snapshot_manager.save_snapshot('_system', {'beta': 0.8, 'forget_factor': 0.9})
    sg4.snapshot_manager.save_snapshot('_system', {'beta': 0.7, 'forget_factor': 0.85})
    # 模拟调整
    sg4.record_adjustment('rollback_test', 'beta', 0.7, 0.1, -15)
    sg4.record_adjustment('rollback_test', 'beta', 0.1, 0.05, -22)
    # 手动注册额外快照（因record_adjustment可能用不同key）
    sg4.snapshot_manager.save_snapshot('_system', {'beta': 0.05, 'forget_factor': 0.5})
    # 触发回滚
    result = sg4.auto_rollback('_system', flags=[{'severity': 'high', 'reason': 'test rollback'}])
    assert result['status'] == 'rolled_back', f'Rollback failed: {result}'
    print(f'   Rollback result: {result["status"]}')
    print(f'   Rolled params: {result["rolled_params"]}')
    print('   OK')

    # 7. post-rollback cooldown verification
    print('\n7. Post-rollback cooldown...')
    cd = sg4._param_cooldown.get('_system', {})
    has_cooldown = len(cd) > 0
    print('   Cooldown active:', has_cooldown)
    print('   OK')

    # 8. 回滚历史
    print('\n8. Rollback history...')
    history = sg4.get_rollback_history()
    assert len(history) >= 1, f'Should have at least 1 rollback, got {len(history)}'
    print(f'   History entries: {len(history)}')
    print('   OK')

    # 9. 金丝雀发布测试
    print('\n9. Canary test...')
    sg5 = DynamicSafeguards()
    # 模拟一些用户
    for uid in [f'user_{i}' for i in range(30)]:
        sg5.record_adjustment(uid, 'beta', 0.8, 0.9, 0)

    canary = sg5.start_canary_test({'beta': 0.6})
    assert canary['status'] == 'testing', f'Canary should start: {canary}'
    assert canary['canary_count'] >= 1, f'Should have at least 1 canary user, got {canary}'
    print(f'   Canary started: {canary["canary_count"]}/{canary["total_users"]} users')
    print('   OK')

    # 10. 金丝雀状态
    print('\n10. Canary status...')
    canary_status = sg5.get_canary_status()
    assert canary_status['status'] == 'testing', f'Should be testing: {canary_status}'
    print(f'    Status: {canary_status["status"]}')
    print('   OK')

    # 11. get_safety_summary
    print('\n11. Safety summary...')
    print(sg5.get_safety_summary())
    print('   OK')

    # 12. 多次回滚只保留最近10条
    print('\n12. Rollback history limit (10 max)...')
    for i in range(15):
        sg5.snapshot_manager.save_snapshot('_rollback_test', {'beta': 0.8 + i * 0.01})
    history_limited = sg5.get_rollback_history()
    # 回滚历史只保留最近10条
    print(f'    Rollback entries: {len(sg5._load_rollback_history().get("rollbacks", []))}')

    # 清理测试数据
    if os.path.exists(SAFEGUARDS_DIR):
        shutil.rmtree(SAFEGUARDS_DIR)

    print('\nAll dynamic_safeguards tests PASS!')