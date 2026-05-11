#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
meta_learner.py — AISleepGen 元学习模块 v1.0

范式跃迁：系统不仅与用户交互，还会每日自我审查并调整自身参数。

核心思想：人类每晚"睡前发呆"回顾一天，找到可以改进的地方。
系统也应该每天做同样的事——回顾今天的实验日志、预测误差、干预效果，
形成"今日总结"，然后调整模块参数。

自我审查输出（每日一条JSON）：
  - 今日表现：多少实验、成功率、平均不确定性
  - 模块调优：什么参数应该调大/调小
  - 参数调整：{module: {param: delta, ...}, ...}
  - 洞察：今天的发现（文本）

调整的模块参数：
  1. predictive_coding: 学习率(learning_rate) — 误差大调大，误差小调小
  2. homeostatic_circuit: 冷却阈值(cooldown_minutes) — 成功多可缩短
  3. push_decision: 推送阈值 — 反馈差则提高门槛
  4. experiment_log: 置信度门槛 — 数据多可以收紧

安全的参数范围：
  - learning_rate: 0.05~0.8（默认0.3）
  - cooldown_minutes: 1~60（默认10）
  - push_threshold: 30~70（默认50）
  - confidence_min_samples: 2~20（默认5）
"""

import json, os, time, logging, math
from datetime import datetime, timedelta
from collections import defaultdict

_ml_log = logging.getLogger('aisleepgen.meta_learner')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
META_LOG_PATH = os.path.join(PROJECT_ROOT, 'data', 'meta_learn.json')

# ==================== 安全参数边界 ====================

SAFETY_BOUNDS = {
    'learning_rate': (0.05, 0.8),       # 预测编码的学习率
    'cooldown_minutes': (1, 60),        # 双通道冷却时间
    'push_threshold': (30, 70),         # 推送决策阈值
    'confidence_min_samples': (2, 20),  # 置信度最小样本数
    'beta': (0.1, 3.0),                 # POMDP/FE探索系数（FEP β）
    'forget_factor': (0.5, 0.99),       # POMDP A矩阵遗忘因子λ
    'alpha0': (0.01, 1.0),              # POMDP狄利克雷先验强度
    'intervention_rate': (0.1, 0.8),    # 干预频率乘数
}

# 默认值
DEFAULT_PARAMS = {
    'learning_rate': 0.3,
    'cooldown_minutes': 10,
    'push_threshold': 50,
    'confidence_min_samples': 5,
    'beta': 0.8,
    'forget_factor': 0.9,
    'alpha0': 0.1,
    'intervention_rate': 0.5,
}

# ==================== 自适应优化器状态 ====================
# 每个参数有自己的学习率 + 动量，类似Adam的核心思想
# 存储在 data/optimizer/{openid}.json
_OPTIMIZER_DIR = os.path.join(PROJECT_ROOT, 'data', 'optimizer')
OPTIMIZER_DEFAULTS = {
    'base_lr': 0.05,           # 基础学习率（所有参数的共用基底）
    'momentum_decay': 0.9,     # 动量衰减系数
    'step_decay': 0.7,         # 方向改变时的步长惩罚因子
    'step_boost': 1.15,        # 方向一致时的步长加速因子
    'direction_history': {},   # 每个参数最近3次调整方向 [1, -1, 1]
    'velocity': {},            # 每个参数的动量 v
    'lr_scales': {},           # 每个参数的独立学习率缩放
    'total_updates': {},       # 每个参数的总更新次数
}


_OPTIMIZER_DIR = os.path.join(PROJECT_ROOT, 'data', 'optimizer')


def _optimizer_path(openid=None):
    """获取优化器状态路径（用户级 or 全局）"""
    os.makedirs(_OPTIMIZER_DIR, exist_ok=True)
    if openid:
        safe = openid.replace('/', '_').replace('\\', '_')
        return os.path.join(_OPTIMIZER_DIR, safe + '.json')
    return os.path.join(_OPTIMIZER_DIR, '_global.json')


def _load_optimizer_state(openid=None):
    """加载自适应优化器状态"""
    path = _optimizer_path(openid)
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        _ml_log.debug('[Optim] Failed to load %s: %s', path, e)
    return dict(OPTIMIZER_DEFAULTS)


def _save_optimizer_state(state, openid=None):
    """保存自适应优化器状态"""
    path = _optimizer_path(openid)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _ml_log.debug('[Optim] Failed to save %s: %s', path, e)


def adaptive_adjust(param_name, signal_value, current_value, bounds, direction=None, openid=None):
    """
    自适应参数调整引擎——替代所有 if-else 规则
    
    原理：
    1. 每个参数有独立的学习率缩放因子 lr_scale（自动调节）
    2. 带动量（momentum）：方向一致就加速，方向改变就减速
    3. 步长 = base_lr * lr_scale[param] * |signal_value|
    
    Args:
        param_name: 参数名
        signal_value: 偏差信号（0=完美, 正=需要增大, 负=需要减小）
            例如 success_rate=0.2 表示比目标0.5少了0.3，signal=+0.3
        current_value: 当前参数值
        bounds: (min, max)
        direction: 可选，外部指定的调整方向 1（增大）/-1（减小）
    
    Returns:
        new_value, delta
    """
    state = _load_optimizer_state(openid)
    
    # 初始化参数状态（首次出现时）
    if param_name not in state['lr_scales']:
        state['lr_scales'][param_name] = 1.0
    if param_name not in state['velocity']:
        state['velocity'][param_name] = 0.0
    if param_name not in state['direction_history']:
        state['direction_history'][param_name] = []
    if param_name not in state['total_updates']:
        state['total_updates'][param_name] = 0
    
    # 决定调整方向
    if direction is not None:
        adj_direction = direction
    elif abs(signal_value) < 0.05:
        # 信号太小，不调整
        _save_optimizer_state(state, openid)
        return current_value, 0.0
    else:
        adj_direction = 1 if signal_value > 0 else -1
    
    # 更新方向历史（保留最近3次）
    history = state['direction_history'][param_name]
    history.append(adj_direction)
    if len(history) > 3:
        history.pop(0)
    state['direction_history'][param_name] = history
    
    # 动量计算：最近2次方向一致则加速，否则减速
    current_lr_scale = state['lr_scales'][param_name]
    if len(history) >= 2 and history[-1] == history[-2]:
        # 方向一致 → 加速（相信趋势）
        current_lr_scale = min(3.0, current_lr_scale * OPTIMIZER_DEFAULTS['step_boost'])
    elif len(history) >= 2 and history[-1] != history[-2]:
        # 方向改变 → 减速（防止震荡）
        current_lr_scale = max(0.1, current_lr_scale * OPTIMIZER_DEFAULTS['step_decay'])
    
    state['lr_scales'][param_name] = current_lr_scale
    
    # 计算步长
    raw_step = state['base_lr'] * current_lr_scale * abs(signal_value)
    raw_step = max(0.001, min(raw_step, abs(bounds[1] - bounds[0]) * 0.3))  # 限制最大步长
    
    # 动量更新：v = decay * v + (1-decay) * step
    v = state['velocity'][param_name]
    new_v = OPTIMIZER_DEFAULTS['momentum_decay'] * v + (1 - OPTIMIZER_DEFAULTS['momentum_decay']) * raw_step
    state['velocity'][param_name] = new_v
    
    # 应用带动量的步长
    new_value = current_value + adj_direction * new_v
    
    # 安全钳制
    new_value = max(bounds[0], min(bounds[1], new_value))
    
    state['total_updates'][param_name] = state['total_updates'][param_name] + 1
    _save_optimizer_state(state, openid)
    
    return new_value, round(new_value - current_value, 4)


# ==================== 元学习回滚机制 ====================

class ParamHistory:
    """参数变更历史——支持一键回滚

    每次参数调整前保存快照，出问题可恢复。
    保留最近20次变更。
    """
    def __init__(self, path=os.path.join(PROJECT_ROOT, 'data', 'param_history.json')):
        self.path = path
        self._lock = None
        try:
            import threading
            self._lock = threading.Lock()
        except Exception as _ep:
            _log.warning("[meta_learner] %s", _ep)
    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as _ep:
            _log.warning("[meta_learner] %s", _ep)
        return {'history': [], 'head': -1}

    def _save(self, data):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as _ep:
            _log.warning("[meta_learner] %s", _ep)
    def snapshot(self, openid='_system', reason=''):
        """保存当前所有模块参数的快照"""
        data = self._load()
        # 收集当前参数
        params = {}
        for module, bounds in SAFETY_BOUNDS.items():
            params[module] = self._get_current_param(module)
        entry = {
            'ts': time.time(),
            'timestamp': datetime.now().isoformat(),
            'openid': openid,
            'reason': reason,
            'params': params,
        }
        data['history'].append(entry)
        data['head'] = len(data['history']) - 1
        # 保留最近20条
        if len(data['history']) > 20:
            data['history'] = data['history'][-20:]
            data['head'] = len(data['history']) - 1
        self._save(data)
        return len(data['history']) - 1

    def rollback(self, steps=1):
        """回滚到N次前的参数

        Args:
            steps: 回滚步数，1=回退一次

        Returns:
            dict: 回滚后的参数，或None（无法回滚）
        """
        data = self._load()
        target_idx = data['head'] - steps
        if target_idx < 0 or target_idx >= len(data['history']):
            _ml_log.warning('[Meta] Cannot rollback %d steps (head=%d, total=%d)',
                             steps, data['head'], len(data['history']))
            return None
        target = data['history'][target_idx]
        _ml_log.info('[Meta] Rollback to #%d: %s', target_idx, target.get('reason', 'unknown'))
        # 应用参数
        self._apply_params(target['params'])
        # 更新head位置
        data['head'] = target_idx
        self._save(data)
        return target['params']

        return False

    def _sync_to_modules(self, params):
        """将中央参数同步到各个运行时模块"""
        for param, value in params.items():
            bounds = SAFETY_BOUNDS.get(param, (0, 100))
            clamped = max(bounds[0], min(bounds[1], value))
            try:
                if param == 'beta':
                    from pomdp_learner import get_engine
                    e = get_engine()
                    e.beta = clamped
                elif param == 'forget_factor':
                    from pomdp_learner import get_engine
                    for _, u in get_engine().users.items():
                        u['learner'].lambd = clamped
                elif param == 'alpha0':
                    from pomdp_learner import get_engine
                    for _, u in get_engine().users.items():
                        u['learner'].alpha0 = clamped
                elif param == 'intervention_rate':
                    from pomdp_learner import get_engine
                    e = get_engine()
                    e.intervention_rate = clamped
                # cooldown/learning_rate/push_threshold 暂无可写接口，仅存参数
            except Exception as e:
                _ml_log.debug('[Meta] Sync %s=%s failed: %s', param, clamped, e)

    def _get_current_param(self, module, openid=None):
        """从参数存储读取当前值（支持用户级覆盖）"""
        return self._get_param(module, openid)

    def _get_current_value(self, param, openid=None):
        """获取当前参数值"""
        if param in ('beta', 'forget_factor', 'alpha0', 'intervention_rate'):
            try:
                from pomdp_learner import get_engine
                e = get_engine()
                val = getattr(e, param, None)
                if val is not None:
                    return val
            except Exception as _ep:
                _log.warning("[meta_learner] %s", _ep)
        return self._get_param(param, openid)

    def _apply_params(self, params, openid=None):
        """应用参数——写入中央存储 + 同步到模块"""
        # 逐个参数写入用户级或全局
        for module, value in params.items():
            bounds = SAFETY_BOUNDS.get(module, (0, 100))
            clamped = max(bounds[0], min(bounds[1], value))
            self._set_param(module, clamped, openid)
            _ml_log.info('[Meta] Applied %s = %s (clamped, user=%s)', module, clamped, openid or 'global')
        # POMDP参数同步到运行时
        self._sync_to_modules(params)

    def get_history_summary(self):
        """获取参数变历史摘要"""
        data = self._load()
        entries = data['history']
        if not entries:
            return 'No parameter changes yet.'
        lines = [f'Param history: {len(entries)} entries, head at #{data["head"]}']
        for i, e in enumerate(entries):
            marker = '← HEAD' if i == data['head'] else ''
            lines.append(f'  #{i}: {e["timestamp"][:16]} {e["reason"][:40]} {marker}')
        return '\n'.join(lines)


# ==================== 元学习引擎 ====================

    def _save_user_params(self, openid, params):
        """保存用户级参数"""
        if not openid or openid == '_system':
            return
        self._ensure_user_dir()
        path = self._user_params_path(openid)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(params, f, ensure_ascii=False, indent=2)
            _ml_log.debug('[Meta] Saved user params: %s (%d keys)', openid[:8], len(params))
        except Exception as e:
            _ml_log.warning('[Meta] Save user params failed: %s', e)

    def _load_global_params(self):
        import os as _os
        _path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "data", "params.json")
        try:
            if _os.path.exists(_path):
                with open(_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            _ml_log.warning("[Meta] Global params load failed: %s", e)
        return dict(DEFAULT_PARAMS)

    def _save_global_params(self, params):
        import os as _os
        _path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "data", "params.json")
        try:
            _os.makedirs(_os.path.dirname(_path), exist_ok=True)
            with open(_path, "w", encoding="utf-8") as f:
                json.dump(params, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _ml_log.warning("[Meta] Global params save failed: %s", e)

    def _get_param(self, param, openid=None):
        """获取参数值：用户级 > 全局 > 默认"""
        # 1. 用户级
        if openid:
            import os as _os
            _f = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'data', 'params', openid.replace('/', '_').replace('\\', '_') + '.json')
            try:
                if _os.path.exists(_f):
                    with open(_f, 'r', encoding='utf-8') as fp:
                        d = json.load(fp)
                    if param in d:
                        return d[param]
            except Exception as _ep:
                _log.warning("[meta_learner] %s", _ep)
        # 2. 全局
        gp = self._load_global_params()
        if param in gp:
            return gp[param]
        # 3. 默认
        return DEFAULT_PARAMS.get(param, 0)

    def _set_param(self, param, value, openid=None):
        """设置参数：有openid则写入用户级，否则写入全局"""
        import os as _os
        if openid:
            _base = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'data', 'params')
            _os.makedirs(_base, exist_ok=True)
            _f = _os.path.join(_base, openid.replace('/', '_').replace('\\', '_') + '.json')
            try:
                if _os.path.exists(_f):
                    with open(_f, 'r', encoding='utf-8') as fp:
                        d = json.load(fp)
                else:
                    d = {}
                d[param] = value
                with open(_f, 'w', encoding='utf-8') as fp:
                    json.dump(d, fp, ensure_ascii=False, indent=2)
            except Exception as e:
                _ml_log.warning('[Meta] Set user param failed: %s', e)
        else:
            gp = self._load_global_params()
            gp[param] = value
            self._save_global_params(gp)

    def copy_params_from_user(self, target_openid, source_openid):
        """从源用户复制参数到目标用户（迁移学习）"""
        import os as _os
        _base = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'data', 'params')
        _src = _os.path.join(_base, source_openid.replace('/', '_').replace('\\', '_') + '.json')
        _tgt = _os.path.join(_base, target_openid.replace('/', '_').replace('\\', '_') + '.json')
        try:
            if _os.path.exists(_src):
                import shutil
                shutil.copy2(_src, _tgt)
                with open(_src, 'r', encoding='utf-8') as fp:
                    d = json.load(fp)
                _ml_log.info('[Meta] Copied %d params from %s to %s',
                             len(d), source_openid[:8], target_openid[:8])
                return True
        except Exception as e:
            _ml_log.warning('[Meta] Copy params failed: %s', e)
        return False


class MetaLearner:
    """元学习引擎——每日自我审查 + 参数调优

    核心流程：
      1. review_past_n_hours(hours=24) — 审查指定时段的所有实验
      2. 计算成功率、平均误差、不确定性趋势
      3. 生成参数调整方案（带安全钳制）
      4. apply_adjustments() — 执行调整（含快照备份）
      5. persist() — 保存元学习记录
    """

    def __init__(self):
        self.param_history = ParamHistory()

    def _get_param(self, param, openid=None):
        return self.param_history._get_param(param, openid)

    def _set_param(self, param, value, openid=None):
        self.param_history._set_param(param, value, openid)

    def copy_params_from_user(self, target, source):
        return self.param_history.copy_params_from_user(target, source)

        self.param_history = ParamHistory()
        self.meta_log_path = META_LOG_PATH

    def _load_meta_log(self):
        try:
            if os.path.exists(self.meta_log_path):
                with open(self.meta_log_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as _ep:
            _log.warning("[meta_learner] %s", _ep)
        return {'reviews': [], 'adjustments': []}

    def _save_meta_log(self, data):
        try:
            os.makedirs(os.path.dirname(self.meta_log_path), exist_ok=True)
            with open(self.meta_log_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as _ep:
            _log.warning("[meta_learner] %s", _ep)
    def review_past_n_hours(self, hours=24, openid=None):
        """审查过去N小时的所有实验

        核心逻辑：读experiment_log → 统计 → 生成调整方案

        Returns:
            dict: {
                'period': '24h',
                'experiments': int,         # 实验总数
                'success_rate': float,      # 成功率
                'avg_uncertainty': float,   # 平均不确定性
                'adjustments': list,        # 建议调整
                'insights': list,           # 文本洞察
            }
        """
        start_time = time.time()

        # 1. 从实验日志读取数据
        experiments = []
        try:
            from experiment_log import get_log
            exp_log = get_log()
            experiments = exp_log.query(hours_back=hours, limit=500)
        except ImportError:
            _ml_log.warning('[Meta] experiment_log not available')
            return {'error': 'experiment_log not available'}
        except Exception as e:
            _ml_log.warning('[Meta] Failed to load experiments: %s', e)
            return {'error': str(e)}

        if not experiments:
            return {
                'period': f'{hours}h',
                'experiments': 0,
                'success_rate': 0.5,  # 无数据时中性
                'avg_uncertainty': 0.5,
                'adjustments': [],
                'insights': ['No experiments in this period'],
                'computation_time_ms': int((time.time() - start_time) * 1000),
            }

        # 2. 统计
        total = len(experiments)
        concluded = [e for e in experiments if e.get('status') == 'concluded']
        positive = sum(1 for e in concluded if e.get('outcome', {}).get('positive', False))
        all_outcomes = [e.get('outcome', {}).get('score_change', 0) for e in concluded if e.get('outcome')]

        success_rate = positive / total if total > 0 else 0.5
        avg_score_change = sum(all_outcomes) / len(all_outcomes) if all_outcomes else 0

        # 3. 按干预类型统计
        type_stats = defaultdict(lambda: {'total': 0, 'positive': 0, 'avg_change': 0, 'changes': []})
        for e in experiments:
            it = e.get('intervention_type', 'unknown')
            type_stats[it]['total'] += 1
            outcome = e.get('outcome') or {}
            if outcome.get('positive'):
                type_stats[it]['positive'] += 1
            sc = outcome.get('score_change', 0)
            type_stats[it]['changes'].append(sc)

        for it, s in type_stats.items():
            if s['changes']:
                s['avg_change'] = sum(s['changes']) / len(s['changes'])

        # 3b. 从POMDP引擎读取真实不确定性（entropy）
        try:
            from pomdp_learner import get_engine
            _pe = get_engine()
            # 遍历所有出现过的用户，取平均normalized_entropy
            user_entropies = []
            for e in experiments:
                oid = e.get('openid', '')
                if oid and len(oid) >= 3:
                    try:
                        belief = _pe.get_belief(oid)
                        ent = belief.get('normalized_entropy', belief.get('entropy', 0.5))
                        if isinstance(ent, (int, float)) and 0 < ent < 3:
                            user_entropies.append(ent)
                    except Exception as _ep:
                        _log.warning("[meta_learner] %s", _ep)
            if user_entropies:
                avg_uncertainty = sum(user_entropies) / len(user_entropies)
            else:
                avg_uncertainty = 0.5  # 没有POMDP数据时中性
        except Exception:
            avg_uncertainty = 0.5

        # 4. 生成调整方案（自适应优化器引擎）
        adjustments = []

        # 信号定义：每个参数在什么条件下产生偏差信号
        param_signals = []

        # 4a. 学习率：success_rate偏离0.5越多，信号越强
        current_lr = self._get_param('learning_rate', openid)
        lr_signal = (0.5 - success_rate) * 2  # success=0.2 → signal=+0.6 (需调大)
        param_signals.append(('learning_rate', 'predictive_coding', current_lr,
                              SAFETY_BOUNDS['learning_rate'], lr_signal,
                              f'success_rate={success_rate:.0%}'))

        # 4b. 推送阈值：push成功率偏离0.5越多，信号越强
        push_stats = type_stats.get('push', {})
        if push_stats.get('total', 0) >= 3:
            current_th = self._get_param('push_threshold', openid)
            push_success = push_stats['positive'] / push_stats['total']
            # 推送成功率高→降低阈值（更积极推），低→提高阈值（更谨慎）
            th_signal = (0.5 - push_success) * 10
            param_signals.append(('push_threshold', 'push_decision', current_th,
                                  SAFETY_BOUNDS['push_threshold'], th_signal,
                                  f'push_success={push_success:.0%} ({push_stats["positive"]}/{push_stats["total"]})'))

        # 4c. 冷却时间：成功率越低→冷却越长
        if total > 3:
            current_cd = self._get_param('cooldown_minutes', openid)
            cd_signal = (0.5 - success_rate) * 6  # 低成功→正信号→冷却加长
            param_signals.append(('cooldown_minutes', 'homeostatic_circuit', current_cd,
                                  SAFETY_BOUNDS['cooldown_minutes'], cd_signal,
                                  f'total={total} success_rate={success_rate:.0%}'))

        # 4d. Beta：不确定高→提高beta（更多探索）
        if total > 3:
            current_beta = self._get_param('beta', openid)
            beta_signal = (avg_uncertainty - 0.5) * 2  # 不确定0.8→signal+0.6→提高beta
            param_signals.append(('beta', 'pomdp_learner', current_beta,
                                  SAFETY_BOUNDS['beta'], beta_signal,
                                  f'uncertainty={avg_uncertainty:.2f}'))

        # 4e. 遗忘因子：成功率高→提高（老数据可信），低→降低
        if total > 5:
            current_ff = self._get_param('forget_factor', openid)
            ff_signal = (success_rate - 0.5) * 0.4  # success=0.8→signal+0.12→小幅提高
            param_signals.append(('forget_factor', 'pomdp_learner', current_ff,
                                  SAFETY_BOUNDS['forget_factor'], ff_signal,
                                  f'success_rate={success_rate:.0%} avg_change={avg_score_change:+.1f}'))

        # 4f. 干预频率：低成功率→降频率
        if total > 3:
            current_ir = self._get_param('intervention_rate', openid)
            ir_signal = (0.5 - success_rate) * 0.4  # 低成功→正信号→降频
            param_signals.append(('intervention_rate', 'pomdp_learner', current_ir,
                                  SAFETY_BOUNDS['intervention_rate'], ir_signal,
                                  f'success_rate={success_rate:.0%}'))

        # 执行自适应调整
        for param_name, module, current_val, bounds, signal, reason in param_signals:
            if abs(signal) < 0.03:
                continue  # 信号太小，跳过
            new_val, delta = adaptive_adjust(param_name, signal, current_val, bounds, openid=openid)
            if abs(delta) > 0.001:
                adjustments.append({
                    'module': module,
                    'param': param_name,
                    'current': round(current_val, 4),
                    'new': round(new_val, 4),
                    'delta': round(delta, 4),
                    'reason': f'signal={signal:+.2f} {reason}',
                })

        # 4g. v3.19: 短期记忆挥发度 → β调整
        try:
            from pomdp_learner import get_engine as _pe
            _pe_eng = _pe()
            if _pe_eng.working_memory is not None:
                wm = _pe_eng.working_memory
                # 计算所有有此用户的挥发度
                volatilities = {}
                for review_openid in set(e.get('openid', '') for e in experiments if e.get('openid')):
                    if review_openid:
                        vol = wm.get_volatility(review_openid)
                        if vol > 0:
                            volatilities[review_openid] = vol

                if volatilities:
                    avg_vol = sum(volatilities.values()) / len(volatilities)
                    current_beta = self._get_current_value('beta', openid)
                    if avg_vol > 15:
                        # 高波动率(>15) → 提高β（更多探索，因为用户状态不稳定）
                        new_beta = min(SAFETY_BOUNDS['beta'][1], current_beta * 1.2)
                        adjustments.append({
                            'module': 'pomdp_learner',
                            'param': 'beta',
                            'current': round(current_beta, 3),
                            'new': round(new_beta, 3),
                            'delta': round(new_beta - current_beta, 3),
                            'reason': f'short_term_volatility={avg_vol:.1f}>15: 提高β增加探索',
                        })
                    elif avg_vol < 5:
                        # 低波动率(<5) → 降低β（可以收敛，少探索）
                        new_beta = max(SAFETY_BOUNDS['beta'][0], current_beta * 0.85)
                        adjustments.append({
                            'module': 'pomdp_learner',
                            'param': 'beta',
                            'current': round(current_beta, 3),
                            'new': round(new_beta, 3),
                            'delta': round(new_beta - current_beta, 3),
                            'reason': f'short_term_volatility={avg_vol:.1f}<5: 降低β减少探索',
                        })

        except Exception as e:
            _ml_log.debug('[Meta] WM volatility skipped: %s', e)

        # 5. 生成文本洞察
        insights = []
        if total == 0:
            insights.append('Today: no user interactions to learn from.')
        else:
            insights.append(f'Reviewed {total} experiments ({positive} positive, {total - positive} negative).')
            if type_stats:
                best_type = max(type_stats.items(), key=lambda x: x[1]['positive'] / max(x[1]['total'], 1))
                insights.append(f'Best intervention: {best_type[0]} ({best_type[1]["positive"]}/{best_type[1]["total"]} positive).')
            if avg_score_change > 0:
                insights.append(f'Avg score change: +{avg_score_change:.1f} pts (interventions trending positive).')
            elif avg_score_change < 0:
                insights.append(f'Avg score change: {avg_score_change:.1f} pts (interventions may need review).')

        review_result = {
            'period': f'{hours}h',
            'experiments': total,
            'concluded': len(concluded),
            'success_rate': round(success_rate, 3),
            'avg_score_change': round(avg_score_change, 1),
            'avg_uncertainty': round(avg_uncertainty, 3),
            'type_stats': {k: {'total': v['total'], 'positive': v['positive'],
                                'avg_change': round(v['avg_change'], 1)}
                           for k, v in type_stats.items()},
            'adjustments': adjustments,
            'insights': insights,
            'computation_time_ms': int((time.time() - start_time) * 1000),
        }

        return review_result

    def apply_adjustments(self, review_result, openid='_system'):
        """应用审查结果中的参数调整

        安全机制：
          - v4.7.0: 每次调整前检查DynamicSafeguards，不安全则拒绝
          - v4.7.0: 每次调整后记录到DynamicSafeguards
          - 每次调整前保存快照（ParamHistory）
          - 每次调整在安全边界内钳制
          - 记录调整日志

        Args:
            review_result: review_past_n_hours 的输出
            openid: 谁触发的调整

        Returns:
            list[dict]: 已应用的调整
        """
        adjustments = review_result.get('adjustments', [])
        if not adjustments:
            return []

        applied = []

        # v4.7.0: 安全护栏检查
        try:
            from dynamic_safeguards import get_dynamic_safeguards
            sg = get_dynamic_safeguards()
        except ImportError:
            sg = None

        if sg is not None:
            safety = sg.check(openid)
            if not safety['safe']:
                _ml_log.warning('[Meta] Safeguards blocked adjustments: %s', safety['summary'])
                # 如果不是严重阻断，可以继续（只是记录警告）
                # 严重阻断（连续失败、急性恶变）则拒绝调整
                critical_flags = [f for f in safety['flags'] if f.get('severity') in ('critical', 'high')]
                if critical_flags:
                    _ml_log.warning('[Meta] SAFEGUARDS: %d critical flags, adjustments REJECTED', len(critical_flags))
                    return []  # 拒绝调整

        # 先保存快照
        self.param_history.snapshot(openid, f'review({review_result["period"]}): {len(adjustments)} adjustments')

        for adj in adjustments:
            module_name = adj['module']
            param_name = adj['param']
            new_value = adj['new']

            # 安全钳制
            bounds = SAFETY_BOUNDS.get(param_name, (0, 100))
            clamped = max(bounds[0], min(bounds[1], new_value))

            old_value = self._get_current_param(param_name)

            try:
                # 通过用户级/全局参数存储写入
                self._set_param(param_name, clamped, openid)
                self._sync_to_modules({param_name: clamped})

                _ml_log.info('[Meta] Applied %s: %.4f (was %.4f)', param_name, clamped, old_value)

                applied.append({
                    'module': module_name,
                    'param': param_name,
                    'from': round(old_value, 4),
                    'to': round(clamped, 4),
                    'reason': adj.get('reason', 'meta_learn'),
                    'applied_at': time.time(),
                })

                # v4.7.0: 记录调整到安全护栏
                if sg is not None:
                    try:
                        sg.record_adjustment(openid, param_name, old_value or adj['current'], clamped, 0)
                    except Exception as _se:
                        _ml_log.warning('[Meta] Safeguard record_adjustment: %s', _se)

            except Exception as e:
                _ml_log.warning('[Meta] Failed to apply %s.%s: %s', module_name, param_name, e)

        # 持久化元学习日志
        meta_data = self._load_meta_log()
        meta_data['adjustments'].extend(applied)
        meta_data['reviews'].append({
            'ts': time.time(),
            'timestamp': datetime.now().isoformat(),
            'period': review_result['period'],
            'total_experiments': review_result['experiments'],
            'success_rate': review_result['success_rate'],
            'adjustments_applied': len(applied),
        })
        # 保留最近100条review
        if len(meta_data['reviews']) > 100:
            meta_data['reviews'] = meta_data['reviews'][-100:]
        self._save_meta_log(meta_data)

        # v4.7.0: 每轮review后检查是否需要自动回滚
        if sg is not None:
            try:
                # 检查是否需要回滚
                safety_check = sg.check(openid)
                if not safety_check['safe']:
                    _ml_log.info('[Meta] Post-review safeguard check: %s', safety_check['summary'])
            except Exception as _se:
                _ml_log.warning('[Meta] Post-review safeguard check failed: %s', _se)

        return applied

    def population_aware_adjustment(self, openid=None):
        """群体意识参数调整——根据集群表现微调参数

        当某个集群的outcome优于全局时，该集群的参数向高绩效方向微调
        当某个集群outcome差于全局时，该集群的参数向全局方向收敛

        Args:
            openid: 可选，指定用户时只调整其所在集群

        Returns:
            dict: 调整报告
        """
        try:
            from population_manager import get_population_manager
            pm = get_population_manager()

            # 执行周期维护（聚类+分化）
            report = pm.periodic_maintenance()

            results = []
            cluster_info = report.get('cluster_info', {})
            global_stats = report.get('global_stats', {})
            global_rate = global_stats.get('avg_positive_rate', 0.5)

            for cidx, info in cluster_info.items():
                pos_rate = info.get('positive_rate', 0.5)
                params = info.get('params', {})
                user_count = info.get('users', 0)
                name = info.get('name', f'cluster_{cidx}')

                if user_count < 2:
                    continue

                if pos_rate > global_rate + 0.05:
                    delta = 'positive'
                elif pos_rate < global_rate - 0.05:
                    delta = 'negative'
                else:
                    delta = 'neutral'

                results.append({
                    'cluster_id': cidx,
                    'cluster_name': name,
                    'users': user_count,
                    'positive_rate': pos_rate,
                    'global_rate': global_rate,
                    'delta': delta,
                    'params': params,
                })

            _ml_log.info('[Meta] Population aware adjustment: %d clusters reviewed, %d divergent',
                          len(cluster_info), sum(1 for r in results if r['delta'] != 'neutral'))

            return {
                'status': 'ok',
                'clusters_reviewed': len(cluster_info),
                'divergent_clusters': [r for r in results if r['delta'] != 'neutral'],
                'all_clusters': results,
                'splits_suggested': report.get('splits_suggested', 0),
            }

        except ImportError:
            _ml_log.warning('[Meta] population_manager not available')
            return {'status': 'error', 'reason': 'population_manager not available'}
        except Exception as e:
            _ml_log.warning('[Meta] population_aware_adjustment failed: %s', e)
            return {'status': 'error', 'reason': str(e)}

    def get_adjustment_history(self):
        """获取参数调整历史"""
        meta_data = self._load_meta_log()
        return meta_data.get('adjustments', [])

    def daily_review(self, openid='_system'):
        """完整每日复盘——审查、调整、输出总结

        这个是被调度器或管理员调用的入口。
        安全：从不空转，最少审查1小时内数据。

        v5.1.0: 如果存在running的AB实验，暂停全局调整避免干扰实验。
          金丝雀实验模式下允许调整（金丝雀本身就是实验）。

        Returns:
            dict: 完整复盘报告
        """
        _ml_log.info('[Meta] Starting daily review...')

        # v5.1.0: 检查是否有running的AB实验
        ab_experiments_running = 0
        ab_canary_running = 0
        try:
            from ab_framework import list_experiments
            all_exps = list_experiments()
            for exp in all_exps:
                if exp.get('status') in ('running', 'evaluating'):
                    ab_experiments_running += 1
                    if exp.get('is_canary'):
                        ab_canary_running += 1
        except Exception:
            pass

        # 如果有running的AB实验,暂停全局调整(Skip)
        if ab_experiments_running > 0 and ab_canary_running == 0:
            _ml_log.info('[Meta] Pausing global adjustments: %d AB experiments running',
                         ab_experiments_running)
            return {
                'report': f'Paused: {ab_experiments_running} AB experiments running',
                'ab_experiments_running': ab_experiments_running,
                'adjustments': [],
                'population_adjustment': {'paused': True, 'reason': 'AB experiments active'},
            }

        # 金丝雀模式下：允许调整，但仅影响非金丝雀用户
        if ab_canary_running > 0:
            _ml_log.info('[Meta] Canary experiments running, adjustments allowed but isolated')

        # 1. 审查过去24小时
        review = self.review_past_n_hours(24)
        if 'error' in review:
            return {'report': review['error'], 'adjustments': []}

        # 2. 应用调整
        adjustments = self.apply_adjustments(review, openid)

        # 2b. v4.6.0: 群体意识调整
        pop_result = self.population_aware_adjustment()

        # 3. 生成报告
        report = {
            'timestamp': datetime.now().isoformat(),
            'review': review,
            'adjustments': adjustments,
            'population_adjustment': pop_result,
            'param_history_summary': self.param_history.get_history_summary(),
            'ab_experiments_running': ab_experiments_running,
            'ab_canary_running': ab_canary_running,
        }

        _ml_log.info('[Meta] Daily review complete: %d experiments, %d adjustments applied, %d clusters',
                      review['experiments'], len(adjustments),
                      pop_result.get('clusters_reviewed', 0))
        return report

    def get_summary_text(self):
        """获取人类可读的元学习摘要"""
        meta_data = self._load_meta_log()
        reviews = meta_data.get('reviews', [])

        if not reviews:
            return 'No meta-learning reviews yet.'

        last = reviews[-1]
        lines = [
            f'📊 元学习每日复盘',
            f'上次审查: {last.get("timestamp", "unknown")[:16]}',
            f'审查实验: {last.get("total_experiments", 0)} 条',
            f'成功率: {last.get("success_rate", 0):.0%}',
            f'调整次数: {last.get("adjustments_applied", 0)} 次',
        ]
        total_adjustments = len(meta_data.get('adjustments', []))
        lines.append(f'累计调整: {total_adjustments} 次')

        return '\n'.join(lines)


# ==================== 公开 API ====================

def run_daily_review():
    """运行每日复盘（供调度器调用）"""
    ml = MetaLearner()
    return ml.daily_review()

def get_review_summary():
    """获取元学习摘要文本"""
    ml = MetaLearner()
    return ml.get_summary_text()

def rollback_params(steps=1):
    """回滚参数调整

    Args:
        steps: 1=回退一次

    Returns:
        dict or None: 回滚后的参数
    """
    ml = MetaLearner()
    return ml.param_history.rollback(steps)


# ==================== CLI ====================
if __name__ == '__main__':
    import sys
    if '--review' in sys.argv:
        logging.basicConfig(level=logging.INFO)
        print('Running meta-learner daily review...')
        ml = MetaLearner()
        result = ml.daily_review()
        review = result.get('review', {})
        adjustments = result.get('adjustments', [])
        print('  Experiments: ' + str(review.get("experiments", 0)))
        print('  Concluded: ' + str(review.get("concluded", 0)))
        print('  Success rate: ' + str(round(review.get("success_rate", 0)*100, 1)) + '%')
        print('  Avg uncertainty: ' + str(round(review.get("avg_uncertainty", 0), 2)))
        print('  Adjustments: ' + str(len(adjustments)))
        for a in adjustments:
            print('    ' + str(a.get("param")) + ': ' + str(a.get("from")) + ' -> ' + str(a.get("to")) + ' (' + str(a.get("reason")) + ')')
        print('  Insights: ')
        for i in review.get('insights', []):
            print('    - ' + str(i))
        print('Done.')
    else:
        # 原有自测
        print('=== Meta Learner Self-Test ===')

    # 1. 基础功能：审查空数据
    ml = MetaLearner()
    print('\n1. Empty review:')
    review = ml.review_past_n_hours(24)
    print(f'   Experiments: {review.get("experiments", "error")}')
    if 'error' in review:
        print(f'   (expected: no experiment_log data yet)')
    else:
        print(f'   Success rate: {review["success_rate"]}')

    # 2. ParamHistory 快照 + 回滚
    print('\n2. ParamHistory:')
    ph = ParamHistory()
    n1 = ph.snapshot('test_user', '第一次调整')
    n2 = ph.snapshot('test_user', '第二次调整')
    n3 = ph.snapshot('test_user', '第三次调整')
    print(f'   Snapshots: {n1}, {n2}, {n3}')

    # 回滚一次
    rolled = ph.rollback(1)
    assert rolled is not None
    print(f'   Rollback 1 step: OK (now head={ph._load()["head"]})')

    # 回滚过头
    rolled = ph.rollback(100)
    assert rolled is None
    print(f'   Rollback too far: gracefully rejected')

    # 清理
    history_path = os.path.join(PROJECT_ROOT, 'data', 'param_history.json')
    if os.path.exists(history_path):
        os.remove(history_path)

    # 3. 单日审查（需experiment_log有数据）
    # mock一下实验日志路径
    print('\n3. MetaLearner dry run:')
    review2 = ml.review_past_n_hours(24)
    print(f'   Computation: {review2.get("computation_time_ms", "N/A")} ms')

    # 清理元学习日志
    if os.path.exists(META_LOG_PATH):
        os.remove(META_LOG_PATH)

    print('\nAll tests PASS!')
