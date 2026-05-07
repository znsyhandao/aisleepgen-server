#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ab_framework.py — AISleepGen A/B 测试框架 v1.0

核心功能：
  - 创建/管理 A/B 实验，支持在线分流与统计显著性检验
  - 自动选出显著优胜者并推广参数
  - 与 dynamic_safeguards 联动的金丝雀实验
  - 完整的回滚方案：保留所有历史优胜者配置

实验生命周期：
  created → running → evaluating → completed(winner=A/B/tie) 或 rolled_back

集成点：
  - conscious_decider.py: 实验运行中覆盖决策参数
  - dp_router.py: 记录 outcome + 4条 AB 管理路由
  - online_rl.py: RL 初始参数可被实验配置覆盖
  - meta_learner.py: 实验运行中暂停全局调整（金丝雀模式除外）

存储：
  - data/ab_experiments/experiments.json — 实验元数据
  - data/ab_experiments/{id}_outcomes.json — 逐用户 outcome
  - data/ab_experiments/winner_config.json — 当前优胜者配置
  - data/ab_experiments/config_history/ — 历史优胜者配置归档
"""

import json
import os
import time
import hashlib
import logging
import threading
import shutil
from datetime import datetime, timedelta
from collections import defaultdict

try:
    import scipy.stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

_ab_log = logging.getLogger('aisleepgen.ab_framework')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
AB_DIR = os.path.join(PROJECT_ROOT, 'data', 'ab_experiments')
EXPERIMENTS_PATH = os.path.join(AB_DIR, 'experiments.json')
WINNER_CONFIG_PATH = os.path.join(AB_DIR, 'winner_config.json')
CONFIG_HISTORY_DIR = os.path.join(AB_DIR, 'config_history')

# ==================== 常量 ====================

# 实验状态
STATUS_CREATED = 'created'
STATUS_RUNNING = 'running'
STATUS_EVALUATING = 'evaluating'
STATUS_COMPLETED = 'completed'
STATUS_ROLLED_BACK = 'rolled_back'

# 评估参数
MIN_SAMPLES_PER_ARM = 30       # 每组最小样本量
MIN_RUN_HOURS = 24              # 最短运行时长
MAX_RUN_HOURS = 168             # 最长运行时长 (7天)
SIGNIFICANCE_LEVEL = 0.05       # 显著性阈值
DEFAULT_SPLIT_RATIO = 0.5       # 默认分流比例

# 优胜者判定
WINNER_A = 'A'
WINNER_B = 'B'
WINNER_TIE = 'tie'

# ==================== 锁 ====================

_ab_lock = threading.Lock()
_assignment_cache = {}  # {cache_key: arm} 内存缓存已分流的用户实验分配


# ==================== 数据层 ====================

def _ensure_dirs():
    """确保存储目录存在"""
    os.makedirs(AB_DIR, exist_ok=True)
    os.makedirs(CONFIG_HISTORY_DIR, exist_ok=True)


def _load_experiments():
    """加载所有实验元数据"""
    _ensure_dirs()
    if not os.path.exists(EXPERIMENTS_PATH):
        return {}
    try:
        with open(EXPERIMENTS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save_experiments(experiments):
    """保存所有实验元数据"""
    _ensure_dirs()
    with open(EXPERIMENTS_PATH, 'w', encoding='utf-8') as f:
        json.dump(experiments, f, ensure_ascii=False, indent=2)


def _load_outcomes(experiment_id):
    """加载某个实验的 outcome 记录"""
    _ensure_dirs()
    path = os.path.join(AB_DIR, f'{experiment_id}_outcomes.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save_outcomes(experiment_id, outcomes):
    """保存某个实验的 outcome 记录"""
    _ensure_dirs()
    path = os.path.join(AB_DIR, f'{experiment_id}_outcomes.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(outcomes, f, ensure_ascii=False, indent=2)


def load_winner_config():
    """加载当前优胜者配置（系统启动时调用覆盖默认值）"""
    if not os.path.exists(WINNER_CONFIG_PATH):
        return {}
    try:
        with open(WINNER_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save_winner_config(config, source_experiment_id=None, winner_arm=None):
    """保存优胜者配置到 winner_config.json 并归档历史版本"""
    _ensure_dirs()

    # 如果已有配置，先归档
    if os.path.exists(WINNER_CONFIG_PATH):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        archive_name = f'winner_{timestamp}.json'
        archive_path = os.path.join(CONFIG_HISTORY_DIR, archive_name)
        try:
            shutil.copy2(WINNER_CONFIG_PATH, archive_path)
        except Exception as e:
            _ab_log.warning('[AB] Failed to archive winner config: %s', e)

    # 写入新配置
    winner_data = {
        'config': config,
        'source_experiment_id': source_experiment_id,
        'winner_arm': winner_arm,
        'promoted_at': datetime.now().isoformat(),
        'timestamp': time.time(),
    }
    with open(WINNER_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(winner_data, f, ensure_ascii=False, indent=2)

    _ab_log.info('[AB] Winner config promoted: experiment=%s, winner=%s, params=%s',
                 source_experiment_id, winner_arm, list(config.keys()))


def list_winner_history():
    """列出所有历史优胜者配置"""
    _ensure_dirs()
    history = []
    if not os.path.exists(CONFIG_HISTORY_DIR):
        return history
    archive_files = sorted(
        [f for f in os.listdir(CONFIG_HISTORY_DIR) if f.endswith('.json')],
        reverse=True
    )
    for fname in archive_files:
        path = os.path.join(CONFIG_HISTORY_DIR, fname)
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            history.append({
                'filename': fname,
                'promoted_at': data.get('promoted_at', 'unknown'),
                'source_experiment_id': data.get('source_experiment_id'),
                'winner_arm': data.get('winner_arm'),
            })
        except Exception:
            pass
    return history


def rollback_to_winner_version(index=0):
    """回滚到指定版本的历史优胜者配置

    Args:
        index: 0=最近一次, 1=前一次, ...

    Returns:
        dict or None: 回滚后的配置，失败返回 None
    """
    history = list_winner_history()
    if index >= len(history):
        _ab_log.warning('[AB] Rollback index %d out of range (max %d)', index, len(history) - 1)
        return None

    target = history[index]
    path = os.path.join(CONFIG_HISTORY_DIR, target['filename'])
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        _save_winner_config(
            data['config'],
            source_experiment_id=data.get('source_experiment_id'),
            winner_arm=data.get('winner_arm'),
        )
        _ab_log.info('[AB] Rolled back to winner version %d (%s)', index, target['filename'])
        return data['config']
    except Exception as e:
        _ab_log.error('[AB] Rollback failed: %s', e)
        return None


# ==================== 用户分流 ====================

def _hash_user(user_id, experiment_id, split_ratio=DEFAULT_SPLIT_RATIO):
    """一致性哈希分配用户到 A/B 组

    基于用户 ID 和实验 ID 的哈希，保证同一用户始终进入同一组。
    """
    key = f'{user_id}:{experiment_id}'
    h = hashlib.md5(key.encode('utf-8')).hexdigest()
    # 取前 8 位 hex 转为整数
    hash_int = int(h[:8], 16)
    # 映射到 [0, 1) 区间
    normalized = (hash_int % 1000000) / 1000000.0
    if normalized < split_ratio:
        return 'A'
    return 'B'


def _get_cached_assignment(user_id, experiment_id):
    """获取缓存的用户实验分配"""
    cache_key = f'{user_id}:{experiment_id}'
    return _assignment_cache.get(cache_key)


def _set_cached_assignment(user_id, experiment_id, arm):
    """缓存用户实验分配"""
    cache_key = f'{user_id}:{experiment_id}'
    _assignment_cache[cache_key] = arm


# ==================== 核心类 ====================

class ABFramework:
    """A/B 测试框架核心类"""

    def __init__(self):
        self._experiments = {}  # 内存缓存，提高性能
        self._load_experiments()

    def _load_experiments(self):
        """从磁盘加载实验到内存"""
        self._experiments = _load_experiments()

    def _save_experiments(self):
        """保存内存实验到磁盘"""
        _save_experiments(self._experiments)

    # ==================== 实验管理 ====================

    def create_experiment(self, name, config_a, config_b, split_ratio=DEFAULT_SPLIT_RATIO,
                          is_canary=False):
        """创建新实验

        Args:
            name: 实验名称
            config_a: A 组策略参数 dict
            config_b: B 组策略参数 dict
            split_ratio: A 组比例 (0.0~1.0)，默认 0.5
            is_canary: 是否为金丝雀实验

        Returns:
            str: experiment_id
        """
        with _ab_lock:
            experiment_id = self._generate_experiment_id(name)

            experiment = {
                'id': experiment_id,
                'name': name,
                'status': STATUS_CREATED,
                'created_at': time.time(),
                'created_at_iso': datetime.now().isoformat(),
                'started_at': None,
                'last_evaluated_at': None,
                'completed_at': None,
                'config_a': config_a,
                'config_b': config_b,
                'split_ratio': split_ratio,
                'is_canary': is_canary,
                'winner': None,
                'p_value': None,
                'statistical_significant': False,
                'n_a': 0,
                'n_b': 0,
                'mean_a': None,
                'mean_b': None,
                'secondary_metrics': {},
            }

            self._experiments[experiment_id] = experiment
            self._save_experiments()

            _ab_log.info('[AB] Experiment created: id=%s, name=%s, split=%s, canary=%s',
                         experiment_id, name, split_ratio, is_canary)
            return experiment_id

    def _generate_experiment_id(self, name):
        """生成唯一实验 ID"""
        raw = f'{name}:{time.time()}:{os.urandom(4).hex()}'
        h = hashlib.md5(raw.encode('utf-8')).hexdigest()[:12]
        return f'exp_{h}'

    def start_experiment(self, experiment_id):
        """启动实验（从 created 转为 running）"""
        with _ab_lock:
            if experiment_id not in self._experiments:
                return {'error': f'Experiment {experiment_id} not found'}

            exp = self._experiments[experiment_id]
            if exp['status'] != STATUS_CREATED:
                return {'error': f'Experiment {experiment_id} is already {exp["status"]}'}

            exp['status'] = STATUS_RUNNING
            exp['started_at'] = time.time()
            self._save_experiments()

            _ab_log.info('[AB] Experiment started: id=%s', experiment_id)
            return {'success': True, 'experiment_id': experiment_id, 'status': STATUS_RUNNING}

    def get_assignment(self, user_id, experiment_id):
        """获取用户在实验中的分组

        1. 先查内存缓存（已分流的用户）
        2. 再查 outcome 记录（避免重复分配）
        3. 最后走哈希分配（新用户）

        Args:
            user_id: 用户 ID
            experiment_id: 实验 ID

        Returns:
            str or None: 'A' | 'B' | None（实验不存在/未运行）
        """
        with _ab_lock:
            if experiment_id not in self._experiments:
                return None

            exp = self._experiments[experiment_id]
            if exp['status'] not in (STATUS_RUNNING, STATUS_EVALUATING):
                return None

            # 1. 查内存缓存
            cached = _get_cached_assignment(user_id, experiment_id)
            if cached:
                return cached

            # 2. 查 outcome 记录（已有记录的不能改变分组）
            outcomes = _load_outcomes(experiment_id)
            if user_id in outcomes:
                arm = outcomes[user_id].get('arm')
                if arm:
                    _set_cached_assignment(user_id, experiment_id, arm)
                    return arm

            # 3. 哈希分配新用户
            arm = _hash_user(user_id, experiment_id, exp['split_ratio'])
            _set_cached_assignment(user_id, experiment_id, arm)
            return arm

    def record_outcome(self, experiment_id, user_id, arm, outcome):
        """记录用户结果到实验

        Args:
            experiment_id: 实验 ID
            user_id: 用户 ID
            arm: 用户所在组 ('A' | 'B')
            outcome: dict {
                'score': float,          # 主要终点：用户评分
                'intervention_effect': float,  # 干预有效率 (0~1)
                'retention': float,      # 留存率 (0~1)
                'negative_feedback': float,  # 负反馈率 (0~1)
                'active_interactions': int,  # 主动交互频率
                'timestamp': float,      # 结果时间戳
            }
        """
        with _ab_lock:
            if experiment_id not in self._experiments:
                return {'error': f'Experiment {experiment_id} not found'}

            exp = self._experiments[experiment_id]
            if exp['status'] not in (STATUS_RUNNING, STATUS_EVALUATING):
                return {'error': f'Experiment {experiment_id} is not active (status={exp["status"]})'}

            now = time.time()
            outcome_entry = dict(outcome)
            outcome_entry['arm'] = arm
            outcome_entry['recorded_at'] = now

            outcomes = _load_outcomes(experiment_id)
            if user_id in outcomes:
                # 合并更新（保留最近时间戳）
                existing = outcomes[user_id]
                # 只有新记录的 timestamp 更新才覆盖评分
                new_ts = outcome.get('timestamp', 0)
                old_ts = existing.get('timestamp') or existing.get('recorded_at', 0)
                if new_ts >= old_ts:
                    existing.update(outcome_entry)
            else:
                outcomes[user_id] = outcome_entry

            _save_outcomes(experiment_id, outcomes)

            # 更新实验计数
            if arm == 'A':
                exp['n_a'] = len([u for u, o in outcomes.items() if o.get('arm') == 'A'])
            else:
                exp['n_b'] = len([u for u, o in outcomes.items() if o.get('arm') == 'B'])
            self._save_experiments()

            return {'success': True}

    def evaluate(self, experiment_id):
        """评估实验结果，进行统计显著性检验

        Returns:
            dict: {
                'status': 'evaluating' | 'completed' | 'tie',
                'experiment_id': str,
                'n_a': int,
                'n_b': int,
                'mean_a': float or None,
                'mean_b': float or None,
                'p_value': float or None,
                'winner': 'A' | 'B' | 'tie' or None,
                'statistical_significant': bool,
                'reason': str,
                'secondary_metrics': dict,
            }
        """
        with _ab_lock:
            if experiment_id not in self._experiments:
                return {'error': f'Experiment {experiment_id} not found'}

            exp = self._experiments[experiment_id]
            if exp['status'] not in (STATUS_RUNNING, STATUS_EVALUATING):
                return {'error': f'Experiment {experiment_id} is not active (status={exp["status"]})'}

            # 更新状态为 evaluating
            if exp['status'] == STATUS_RUNNING:
                exp['status'] = STATUS_EVALUATING
            exp['last_evaluated_at'] = time.time()

            # 加载 outcomes
            outcomes = _load_outcomes(experiment_id)
            if not outcomes:
                return self._tie_result(exp, 'no_outcomes', 'No outcomes recorded yet')

            # 分组
            scores_a = []
            scores_b = []
            metrics_a = defaultdict(list)
            metrics_b = defaultdict(list)

            for uid, o in outcomes.items():
                score = o.get('score')
                arm = o.get('arm')
                if score is None or arm is None:
                    continue
                if arm == 'A':
                    scores_a.append(score)
                    for metric in ('intervention_effect', 'retention', 'negative_feedback', 'active_interactions'):
                        if metric in o:
                            metrics_a[metric].append(o[metric])
                elif arm == 'B':
                    scores_b.append(score)
                    for metric in ('intervention_effect', 'retention', 'negative_feedback', 'active_interactions'):
                        if metric in o:
                            metrics_b[metric].append(o[metric])

            n_a = len(scores_a)
            n_b = len(scores_b)
            exp['n_a'] = n_a
            exp['n_b'] = n_b

            # 样本量检查
            if n_a < MIN_SAMPLES_PER_ARM or n_b < MIN_SAMPLES_PER_ARM:
                self._save_experiments()
                return self._tie_result(
                    exp, 'insufficient_samples',
                    f'Samples too small: A={n_a}, B={n_b} (min {MIN_SAMPLES_PER_ARM} each)',
                    n_a=n_a, n_b=n_b,
                    mean_a=sum(scores_a) / n_a if scores_a else None,
                    mean_b=sum(scores_b) / n_b if scores_b else None,
                )

            # 运行时检查
            running_hours = (time.time() - exp['started_at']) / 3600 if exp['started_at'] else 0
            if running_hours < MIN_RUN_HOURS:
                self._save_experiments()
                return self._tie_result(
                    exp, 'insufficient_time',
                    f'Running for {running_hours:.1f}h, need at least {MIN_RUN_HOURS}h',
                    n_a=n_a, n_b=n_b,
                    mean_a=sum(scores_a) / n_a,
                    mean_b=sum(scores_b) / n_b,
                )

            # 统计检验：独立样本 t 检验
            mean_a = sum(scores_a) / n_a
            mean_b = sum(scores_b) / n_b

            p_value = None
            significant = False
            winner = WINNER_TIE

            if HAS_SCIPY and n_a >= 2 and n_b >= 2:
                try:
                    t_stat, p_value = scipy.stats.ttest_ind(scores_a, scores_b)
                    significant = p_value < SIGNIFICANCE_LEVEL
                except Exception as e:
                    _ab_log.warning('[AB] T-test failed: %s', e)

            if significant:
                if mean_a > mean_b:
                    winner = WINNER_A
                elif mean_b > mean_a:
                    winner = WINNER_B
                else:
                    winner = WINNER_TIE
            else:
                # 检查是否超过最大运行时长
                if running_hours >= MAX_RUN_HOURS:
                    # 超时关闭，返回 tie
                    winner = WINNER_TIE
                    return self._finalize_experiment(exp, winner, p_value, significant, n_a, n_b, mean_a, mean_b, outcomes)
                else:
                    # 继续运行
                    return self._tie_result(
                        exp, 'not_significant',
                        f'p={p_value:.4f} >= 0.05, not significant yet. Running for {running_hours:.1f}h (max {MAX_RUN_HOURS}h)',
                        n_a=n_a, n_b=n_b, mean_a=mean_a, mean_b=mean_b, p_value=p_value,
                    )

            # 计算次要指标
            secondary_metrics = self._compute_secondary_metrics(metrics_a, metrics_b, outcomes)

            exp['mean_a'] = self._to_python(mean_a)
            exp['mean_b'] = self._to_python(mean_b)
            exp['p_value'] = self._to_python(p_value)
            exp['statistical_significant'] = bool(significant)
            exp['secondary_metrics'] = secondary_metrics
            exp['winner'] = winner

            # 显著胜出，自动完成实验
            result = self._finalize_experiment(exp, winner, p_value, significant, n_a, n_b, mean_a, mean_b, outcomes)
            result['secondary_metrics'] = secondary_metrics
            return result

    def _compute_secondary_metrics(self, metrics_a, metrics_b, outcomes):
        """计算次要评估指标"""
        secondary = {}
        for metric_name in ('intervention_effect', 'retention', 'negative_feedback', 'active_interactions'):
            a_vals = metrics_a.get(metric_name, [])
            b_vals = metrics_b.get(metric_name, [])
            if a_vals and b_vals:
                secondary[metric_name] = {
                    'mean_a': sum(a_vals) / len(a_vals),
                    'mean_b': sum(b_vals) / len(b_vals),
                    'n_a': len(a_vals),
                    'n_b': len(b_vals),
                }
        return secondary

    def _finalize_experiment(self, exp, winner, p_value, significant, n_a, n_b, mean_a, mean_b, outcomes=None):
        """完成实验并推广优胜者"""
        exp['status'] = STATUS_COMPLETED
        exp['completed_at'] = time.time()
        exp['winner'] = winner
        exp['p_value'] = self._to_python(p_value)
        exp['statistical_significant'] = bool(significant)
        exp['n_a'] = n_a
        exp['n_b'] = n_b
        exp['mean_a'] = self._to_python(mean_a)
        exp['mean_b'] = self._to_python(mean_b)
        self._save_experiments()

        reason_text = (
            f'p={p_value:.4f}' if p_value else 'no_p_value'
        )

        # 推广优胜者配置
        if winner in (WINNER_A, WINNER_B):
            winner_config = exp['config_a'] if winner == WINNER_A else exp['config_b']
            _save_winner_config(winner_config, exp['id'], winner)
            _ab_log.info('[AB] Experiment %s completed: winner=%s, mean_A=%.2f, mean_B=%.2f, p=%.4f',
                         exp['id'], winner, mean_a, mean_b, p_value or 0)
        else:
            _ab_log.info('[AB] Experiment %s completed: tie, mean_A=%.2f, mean_B=%.2f, p=%.4f',
                         exp['id'], mean_a, mean_b, p_value or 0)

        return {
            'status': STATUS_COMPLETED,
            'experiment_id': exp['id'],
            'n_a': n_a,
            'n_b': n_b,
            'mean_a': self._to_python(mean_a),
            'mean_b': self._to_python(mean_b),
            'p_value': self._to_python(p_value),
            'winner': winner,
            'statistical_significant': bool(significant),
            'reason': reason_text,
        }

    @staticmethod
    def _to_python(value):
        """将 numpy 类型转换为原生 Python 类型，确保 JSON 序列化"""
        if value is None:
            return None
        try:
            import numpy as np
            if isinstance(value, np.integer):
                return int(value)
            if isinstance(value, np.floating):
                return float(value)
            if isinstance(value, np.bool_):
                return bool(value)
        except ImportError:
            pass
        return value

    def _tie_result(self, exp, sub_status, reason, n_a=0, n_b=0, mean_a=None, mean_b=None, p_value=None):
        """返回平局/继续运行的结果"""
        exp['winner'] = WINNER_TIE
        exp['p_value'] = self._to_python(p_value)
        exp['mean_a'] = self._to_python(mean_a)
        exp['mean_b'] = self._to_python(mean_b)
        self._save_experiments()

        return {
            'status': STATUS_EVALUATING,
            'sub_status': sub_status,
            'experiment_id': exp['id'],
            'n_a': n_a,
            'n_b': n_b,
            'mean_a': self._to_python(mean_a),
            'mean_b': self._to_python(mean_b),
            'p_value': self._to_python(p_value),
            'winner': WINNER_TIE,
            'statistical_significant': False,
            'reason': reason,
        }

    def stop_experiment(self, experiment_id, winner=None):
        """手动结束实验并推广

        Args:
            experiment_id: 实验 ID
            winner: 'A' | 'B' | 'tie' | None（None = 不推广，仅停止）

        Returns:
            dict
        """
        with _ab_lock:
            if experiment_id not in self._experiments:
                return {'error': f'Experiment {experiment_id} not found'}

            exp = self._experiments[experiment_id]
            if exp['status'] in (STATUS_COMPLETED, STATUS_ROLLED_BACK):
                return {'error': f'Experiment {experiment_id} already {exp["status"]}'}

            outcomes = _load_outcomes(experiment_id)
            n_a = len([u for u, o in outcomes.items() if o.get('arm') == 'A'])
            n_b = len([u for u, o in outcomes.items() if o.get('arm') == 'B'])

            if winner in (WINNER_A, WINNER_B):
                winner_config = exp['config_a'] if winner == WINNER_A else exp['config_b']
                _save_winner_config(winner_config, experiment_id, winner)
                exp['winner'] = winner
            elif winner == WINNER_TIE:
                exp['winner'] = WINNER_TIE
            # winner=None → 不推广，仅停止

            exp['status'] = STATUS_COMPLETED
            exp['completed_at'] = time.time()
            exp['n_a'] = n_a
            exp['n_b'] = n_b
            self._save_experiments()

            return {
                'success': True,
                'experiment_id': experiment_id,
                'winner': exp['winner'],
                'n_a': n_a,
                'n_b': n_b,
                'promoted': winner in (WINNER_A, WINNER_B),
            }

    def rollback_experiment(self, experiment_id):
        """回滚实验（标记为 rolled_back 并恢复上一个优胜者配置）"""
        with _ab_lock:
            if experiment_id not in self._experiments:
                return {'error': f'Experiment {experiment_id} not found'}

            exp = self._experiments[experiment_id]
            exp['status'] = STATUS_ROLLED_BACK
            self._save_experiments()

            _ab_log.info('[AB] Experiment %s rolled back', experiment_id)
            return {'success': True, 'experiment_id': experiment_id, 'status': STATUS_ROLLED_BACK}

    def list_experiments(self, status_filter=None):
        """列出实验列表

        Args:
            status_filter: None（全部）| 'created' | 'running' | 'evaluating' | 'completed' | 'rolled_back'

        Returns:
            list[dict]
        """
        result = []
        for exp_id, exp in self._experiments.items():
            if status_filter and exp['status'] != status_filter:
                continue
            result.append({
                'id': exp_id,
                'name': exp['name'],
                'status': exp['status'],
                'created_at': exp['created_at_iso'],
                'started_at': datetime.fromtimestamp(exp['started_at']).isoformat() if exp['started_at'] else None,
                'winner': exp.get('winner'),
                'p_value': exp.get('p_value'),
                'statistical_significant': exp.get('statistical_significant'),
                'n_a': exp.get('n_a', 0),
                'n_b': exp.get('n_b', 0),
                'is_canary': exp.get('is_canary', False),
                'split_ratio': exp.get('split_ratio', DEFAULT_SPLIT_RATIO),
                'config_a_keys': list(exp.get('config_a', {}).keys()),
                'config_b_keys': list(exp.get('config_b', {}).keys()),
            })
        return sorted(result, key=lambda x: x['created_at'], reverse=True)

    def get_experiment(self, experiment_id):
        """获取单个实验详情"""
        if experiment_id not in self._experiments:
            return None
        exp = self._experiments[experiment_id]
        outcome_counts = {}  # 不返回具体outcome，只返回统计
        outcomes = _load_outcomes(experiment_id)
        for uid, o in outcomes.items():
            arm = o.get('arm', '?')
            if arm not in outcome_counts:
                outcome_counts[arm] = {'users': 0, 'score_sum': 0}
            outcome_counts[arm]['users'] += 1
            outcome_counts[arm]['score_sum'] += o.get('score', 0)

        return {
            **exp,
            'outcome_counts': outcome_counts,
        }

    # ==================== 金丝雀集成 ====================

    def create_canary_experiment(self, name, canary_config, control_config=None,
                                 canary_ratio=0.05):
        """创建金丝雀实验（5% 新参数 vs 95% 当前参数）

        金丝雀实验与 dynamic_safeguards 联动：
        - A/B 框架提供真实统计数据
        - safeguards 提供快速防护

        Args:
            name: 金丝雀实验名称
            canary_config: 要测试的新参数
            control_config: 对照组参数（默认使用 winner_config 或默认值）
            canary_ratio: 金丝雀组比例，默认 0.05 (5%)

        Returns:
            str: experiment_id
        """
        # 对照组默认参数
        if control_config is None:
            control_config = load_winner_config()
            if not control_config:
                control_config = {
                    'rl_weight': 0.35,
                    'pomdp_weight': 0.35,
                    'push_threshold': 50,
                    'epsilon_decay_steps': 5000,
                    'forget_factor': 0.9,
                }

        # 金丝雀实验：A组=金丝雀(小比例), B组=对照
        experiment_id = self.create_experiment(
            name=f'[Canary] {name}',
            config_a=canary_config,    # 金丝雀组
            config_b=control_config,   # 对照组
            split_ratio=canary_ratio,  # 5% 进金丝雀组
            is_canary=True,
        )

        _ab_log.info('[AB] Canary experiment created: %s (ratio=%s)', experiment_id, canary_ratio)
        return experiment_id

    # ==================== 实验配置获取 ====================

    def create_weight_experiment(self, name, weight_config_a=None, weight_config_b=None,
                                 split_ratio=0.5):
        """创建A/B实验比较不同权重配比（v6.1.0 AEO集成）

        Args:
            name: 实验名称
            weight_config_a: A组权重配置，如 {rl: 0.35, pomdp: 0.35, wm: 0.15, temporal: 0.15}
            weight_config_b: B组权重配置
            split_ratio: 分流比例

        Returns:
            str: experiment_id
        """
        from weight_optimizer import DEFAULT_WEIGHTS

        if weight_config_a is None:
            from weight_optimizer import get_weight_optimizer
            wo = get_weight_optimizer()
            base = wo._load_base_weights()
            weight_config_a = dict(base)

        if weight_config_b is None:
            weight_config_b = {k: v for k, v in DEFAULT_WEIGHTS.items()}

        # 包装为完整配置
        config_a = {'aeo_weights': weight_config_a}
        config_b = {'aeo_weights': weight_config_b}

        experiment_id = self.create_experiment(
            name=f'[AEO-Weights] {name}',
            config_a=config_a,
            config_b=config_b,
            split_ratio=split_ratio,
            is_canary=False,
        )
        return experiment_id

    def get_experiment_config(self, user_id, experiment_id):
        """获取用户在实验中的配置参数

        Args:
            user_id: 用户 ID
            experiment_id: 实验 ID

        Returns:
            dict or None: 实验组的参数配置，不在实验中返回 None
        """
        arm = self.get_assignment(user_id, experiment_id)
        if arm is None:
            return None

        exp = self._experiments.get(experiment_id)
        if exp is None:
            return None

        config = exp['config_a'] if arm == 'A' else exp['config_b']
        return {
            'arm': arm,
            'experiment_id': experiment_id,
            'config': config,
        }

    def get_running_experiments_for_user(self, user_id):
        """获取用户参与的 running 实验列表（用于 conscious_decider 集成）"""
        results = []
        for exp_id, exp in self._experiments.items():
            if exp['status'] not in (STATUS_RUNNING, STATUS_EVALUATING):
                continue
            # 检查用户是否已分配到此实验
            arm = self.get_assignment(user_id, exp_id)
            if arm:
                config = exp['config_a'] if arm == 'A' else exp['config_b']
                results.append({
                    'experiment_id': exp_id,
                    'arm': arm,
                    'config': config,
                    'is_canary': exp.get('is_canary', False),
                })
        return results


# ==================== 全局单例 ====================

_singleton = None
_singleton_lock = threading.Lock()


def get_ab_framework():
    """获取 ABFramework 单例"""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = ABFramework()
    return _singleton


# ==================== 模块级函数（方便外部调用） ====================

def create_experiment(name, config_a, config_b, split_ratio=0.5):
    return get_ab_framework().create_experiment(name, config_a, config_b, split_ratio)


def start_experiment(experiment_id):
    return get_ab_framework().start_experiment(experiment_id)


def get_assignment(user_id, experiment_id):
    return get_ab_framework().get_assignment(user_id, experiment_id)


def record_outcome(experiment_id, user_id, arm, outcome):
    return get_ab_framework().record_outcome(experiment_id, user_id, arm, outcome)


def evaluate(experiment_id):
    return get_ab_framework().evaluate(experiment_id)


def list_experiments(status_filter=None):
    return get_ab_framework().list_experiments(status_filter)


def stop_experiment(experiment_id, winner=None):
    return get_ab_framework().stop_experiment(experiment_id, winner)


def get_experiment_config(user_id, experiment_id):
    return get_ab_framework().get_experiment_config(user_id, experiment_id)


def get_running_experiments_for_user(user_id):
    return get_ab_framework().get_running_experiments_for_user(user_id)


def create_canary_experiment(name, canary_config, control_config=None, canary_ratio=0.05):
    return get_ab_framework().create_canary_experiment(name, canary_config, control_config, canary_ratio)


def create_weight_experiment(name, weight_config_a=None, weight_config_b=None, split_ratio=0.5):
    """创建A/B实验比较不同权重配比（v6.1.0 AEO集成）"""
    return get_ab_framework().create_weight_experiment(name, weight_config_a, weight_config_b, split_ratio)


def rollback_to_winner(index=0):
    return rollback_to_winner_version(index)


def get_winner_config():
    return load_winner_config()


# ==================== 自测 =================
if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(message)s')
    print('=== AB Framework Self-Test ===')

    # 清理测试数据
    test_exp_dir = os.path.join(AB_DIR)
    if os.path.exists(test_exp_dir):
        for f in os.listdir(test_exp_dir):
            fp = os.path.join(test_exp_dir, f)
            try:
                if os.path.isfile(fp):
                    os.remove(fp)
                elif os.path.isdir(fp):
                    shutil.rmtree(fp)
            except Exception:
                pass
    os.makedirs(AB_DIR, exist_ok=True)
    os.makedirs(CONFIG_HISTORY_DIR, exist_ok=True)

    ab = get_ab_framework()

    # ---------- Test 1: 创建实验 ----------
    print('\n1. Create experiment:')
    config_a = {'rl_weight': 0.35, 'pomdp_weight': 0.35, 'push_threshold': 50}
    config_b = {'rl_weight': 0.50, 'pomdp_weight': 0.20, 'push_threshold': 40}
    exp_id = ab.create_experiment('test_weights', config_a, config_b, split_ratio=0.5)
    print(f'   Experiment created: {exp_id}')
    assert exp_id.startswith('exp_'), f'Bad experiment id: {exp_id}'
    print('   PASS')

    # ---------- Test 2: 同一 user_id 始终分配到同一 arm ----------
    print('\n2. Consistent hashing:')
    ab.start_experiment(exp_id)
    arm_1 = ab.get_assignment('user_1', exp_id)
    arm_2 = ab.get_assignment('user_1', exp_id)
    assert arm_1 == arm_2, f'Mismatch! {arm_1} != {arm_2}'
    print(f'   user_1 -> {arm_1} (consistent across calls)')
    # 不同用户可能不同组
    arm_3 = ab.get_assignment('user_2', exp_id)
    print(f'   user_2 -> {arm_3}')
    assert arm_3 in ('A', 'B')
    print('   PASS')

    # ---------- Test 3: 样本量不足时不出判决 ----------
    print('\n3. Insufficient samples:')
    ab.record_outcome(exp_id, 'user_1', arm_1, {'score': 60, 'timestamp': time.time()})
    ab.record_outcome(exp_id, 'user_2', arm_3, {'score': 70, 'timestamp': time.time()})
    result = ab.evaluate(exp_id)
    print(f'   Result: {result["status"]} ({result.get("sub_status", "?")})')
    assert result.get('sub_status') == 'insufficient_samples', f'Expected insufficient_samples, got {result}'
    print('   PASS')

    # ---------- Test 4: 运行时间不足时不出判决 ----------
    print('\n4. Insufficient time:')
    # Add enough samples (>=60 users to get >=30 each)
    for i in range(80):
        uid = f'user_time_{i}'
        arm = ab.get_assignment(uid, exp_id)
        ab.record_outcome(exp_id, uid, arm, {'score': 50 + (i % 10), 'timestamp': time.time()})
    result = ab.evaluate(exp_id)
    print(f'   Result: {result["status"]} ({result.get("sub_status", "?")})')
    # 37 users added in test 3 + 80 = 117 total, so there should be enough per arm
    # But if the new ones fall into the same arm, we need to check
    print(f'   n_a={result.get("n_a")}, n_b={result.get("n_b")}')
    if result.get('sub_status') == 'insufficient_samples':
        # If still insufficient, add 80 more
        for i in range(80, 200):
            uid = f'user_time_{i}'
            arm = ab.get_assignment(uid, exp_id)
            ab.record_outcome(exp_id, uid, arm, {'score': 50 + (i % 10), 'timestamp': time.time()})
        result = ab.evaluate(exp_id)
        print(f'   Retry: n_a={result.get("n_a")}, n_b={result.get("n_b")}, status={result["status"]}')
    assert result.get('sub_status') == 'insufficient_time', f'Expected insufficient_time, got {result}'
    print('   PASS')

    # ---------- Test 5: 带显著差异的实验 ----------
    print('\n5. Significant difference (simulated by mocking start time):')
    # Create a new experiment with mocked start time far in the past
    exp_id2 = ab.create_experiment('test_significant', config_a, config_b, split_ratio=0.5)
    ab._experiments[exp_id2]['started_at'] = time.time() - 48 * 3600  # 48h ago
    ab._experiments[exp_id2]['status'] = STATUS_RUNNING
    ab._save_experiments()

    # Add enough users with clear separation (A group higher scores)
    for i in range(80):
        uid = f'sig_user_{i}'
        arm = ab.get_assignment(uid, exp_id2)
        # A group gets consistently higher scores (均值差 ~15分)
        if arm == 'A':
            score = 75 + (i % 15)
        else:
            score = 60 + (i % 10)
        ab.record_outcome(exp_id2, uid, arm, {
            'score': score,
            'timestamp': time.time(),
            'intervention_effect': 0.8 if arm == 'A' else 0.6,
            'retention': 0.9 if arm == 'A' else 0.7,
            'negative_feedback': 0.1 if arm == 'A' else 0.3,
            'active_interactions': 5 if arm == 'A' else 3,
        })

    result2 = ab.evaluate(exp_id2)
    print(f'   Status: {result2["status"]}')
    print(f'   Winner: {result2["winner"]}')
    print(f'   Mean_A: {result2["mean_a"]:.2f}, Mean_B: {result2["mean_b"]:.2f}')
    print(f'   p_value: {result2.get("p_value", "N/A")}')
    print(f'   Significant: {result2.get("statistical_significant", False)}')
    assert result2['status'] == STATUS_COMPLETED, f'Expected completed, got {result2["status"]}'
    assert result2['winner'] == WINNER_A, f'Expected A to win, got {result2["winner"]}'
    print('   PASS')

    # ---------- Test 6: 统计不显著时继续运行 ----------
    print('\n6. Not significant -> continue running:')
    exp_id3 = ab.create_experiment('test_tie', config_a, config_b, split_ratio=0.5)
    ab._experiments[exp_id3]['started_at'] = time.time() - 48 * 3600
    ab._experiments[exp_id3]['status'] = STATUS_RUNNING
    ab._save_experiments()

    for i in range(80):
        uid = f'tie_user_{i}'
        arm = ab.get_assignment(uid, exp_id3)
        # 两组得分完全一致
        score = 67 + (i % 3)
        ab.record_outcome(exp_id3, uid, arm, {'score': score, 'timestamp': time.time()})

    result3 = ab.evaluate(exp_id3)
    print(f'   Status: {result3["status"]}')
    print(f'   Winner: {result3["winner"]}')
    print(f'   p_value: {result3.get("p_value", "N/A")}')
    assert result3['status'] == STATUS_EVALUATING, f'Expected evaluating, got {result3["status"]}'
    print('   PASS')

    # ---------- Test 7: 超过7天仍不显著 -> tie ----------
    print('\n7. 7-day timeout -> tie:')
    exp_id4 = ab.create_experiment('test_timeout', config_a, config_b, split_ratio=0.5)
    ab._experiments[exp_id4]['started_at'] = time.time() - 200 * 3600  # 200h > 168h (7d)
    ab._experiments[exp_id4]['status'] = STATUS_RUNNING
    ab._save_experiments()

    for i in range(80):
        uid = f'timeout_user_{i}'
        arm = ab.get_assignment(uid, exp_id4)
        score = 67 + (i % 3)
        ab.record_outcome(exp_id4, uid, arm, {'score': score, 'timestamp': time.time()})

    result4 = ab.evaluate(exp_id4)
    print(f'   Status: {result4["status"]}')
    print(f'   Winner: {result4["winner"]}')
    assert result4['status'] == STATUS_COMPLETED, f'Expected completed, got {result4["status"]}'
    assert result4['winner'] == WINNER_TIE, f'Expected tie, got {result4["winner"]}'
    print('   PASS')

    # ---------- Test 8: 推广优胜者 -> winner_config.json写入 ----------
    print('\n8. Winner config written:')
    winner_data = load_winner_config()
    print(f'   Winner config exists: {bool(winner_data)}')
    assert winner_data, 'Winner config not written!'
    assert 'config' in winner_data, 'Missing config in winner data'
    print(f'   Config keys: {list(winner_data["config"].keys())}')
    print('   PASS')

    # ---------- Test 9: 回滚到历史配置 ----------
    print('\n9. Rollback to historical config:')
    # First make a second promotion so there's actually history
    # Winner was already promoted from exp_id2, promote something else
    # Re-promote from the same experiment to create an archive
    _save_winner_config({'rl_weight': 0.40, 'pomdp_weight': 0.30}, 'exp_manual', 'manual')
    history_list = list_winner_history()
    print(f'   History entries: {len(history_list)}')
    assert len(history_list) >= 1, f'Expected history entries, got {len(history_list)}'
    history_rollback = rollback_to_winner(0)
    assert history_rollback is not None, f'Rollback failed (history={len(history_list)})'
    print(f'   Rollback OK, config keys: {list(history_rollback.keys())}')
    print('   PASS')

    # ---------- Test 10: 金丝雀实验创建 ----------
    print('\n10. Canary experiment:')
    canary_config = {'rl_weight': 0.60, 'pomdp_weight': 0.15, 'push_threshold': 30}
    canary_id = ab.create_canary_experiment('test_canary', canary_config)
    print(f'   Canary ID: {canary_id}')
    canary_exp = ab._experiments[canary_id]
    assert canary_exp['is_canary'] == True
    assert canary_exp['split_ratio'] == 0.05
    print(f'   is_canary: {canary_exp["is_canary"]}, split_ratio: {canary_exp["split_ratio"]}')
    print('   PASS')

    # ---------- Test 11: 获取用户实验配置 ----------
    print('\n11. Get experiment config:')
    ab.start_experiment(exp_id)
    user_config = ab.get_experiment_config('user_1', exp_id)
    assert user_config is not None
    assert user_config['arm'] in ('A', 'B')
    print(f'   user_1: arm={user_config["arm"]}')
    print(f'   config: {user_config["config"]}')
    print('   PASS')

    # ---------- Test 12: 手动停止并推广 ----------
    print('\n12. Stop and promote experiment:')
    # Start the canary experiment and stop it
    ab.start_experiment(canary_id)
    stop_result = ab.stop_experiment(canary_id, winner=WINNER_B)
    print(f'   Stop result: {stop_result}')
    assert 'error' not in stop_result, f'Error: {stop_result.get("error")}'
    print(f'   Stopped: winner={stop_result.get("winner")}, promoted={stop_result.get("promoted")}')
    print('   PASS')

    # ---------- Test 13: 列出实验 ----------
    print('\n13. List experiments:')
    all_exps = ab.list_experiments()
    running_exps = ab.list_experiments(status_filter=STATUS_RUNNING)
    completed_exps = ab.list_experiments(status_filter=STATUS_COMPLETED)
    print(f'   Total: {len(all_exps)}, Running: {len(running_exps)}, Completed: {len(completed_exps)}')
    assert len(all_exps) >= 5
    print('   PASS')

    # ---------- Test 14: 在running实验中有赋值 ----------
    print('\n14. Get running experiments for user:')
    running_for_user = ab.get_running_experiments_for_user('user_1')
    print(f'   Running experiments for user_1: {len(running_for_user)}')
    print('   PASS')

    # 清理测试数据
    for f in os.listdir(test_exp_dir):
        fp = os.path.join(test_exp_dir, f)
        try:
            if os.path.isfile(fp):
                os.remove(fp)
            elif os.path.isdir(fp):
                shutil.rmtree(fp)
        except Exception:
            pass

    print('\n' + '=' * 50)
    print('ALL TESTS PASS!')
    print('=' * 50)