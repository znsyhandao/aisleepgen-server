#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
experiment_log.py — AISleepGen 主动推理实验日志 v1.0

范式跃迁：每次交互都是一次实验。

核心思想（自由能原理 → 主动推理）：
  系统不被动等用户输入，而是主动设计"实验"来验证预测。
  每次聊天/推送/探测都是一个实验，有假设、有干预、有观测结果。
  系统通过回顾实验日志，发现"什么条件下什么干预有效"。

核心数据结构：Experiment
  - hypothesis: 系统在做什么假设 (e.g. "用户今晚会晚睡")
  - intervention: 系统做了什么 (e.g. "发了探测消息")
  - observation: 用户如何反应 (e.g. "回了消息, 说睡不着")
  - outcome: 这件事对睡眠的影响 (e.g. "评分比预测低5分")
  - conclusion: 系统学到的东西 (e.g. "发探测消息对这个用户有效")

使用方式：
  1. 系统做任何决策前 → log_experiment_design(假设+干预)
  2. 用户响应后 → log_experiment_outcome(观察+结果)
  3. 下次同类决策 → query_similar_experiments(找到历史最佳)

这就是"给系统装上实验日志"——自我审计层。
"""

import json, os, time, logging, math
from datetime import datetime, timedelta
from collections import defaultdict

_el_log = logging.getLogger('aisleepgen.experiment_log')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
EXPERIMENT_LOG_PATH = os.path.join(PROJECT_ROOT, 'data', 'experiment_log.json')

# ==================== 实验记录 ====================

class Experiment:
    """一次完整的实验记录

    生命周期:
      1. designed — 做出假设、设计干预
      2. deployed — 干预已发送
      3. observed — 收到用户响应
      4. concluded — 得出学习结论
    """
    def __init__(self, openid, intervention_type, hypothesis, intervention_data=None):
        now = time.time()
        self.experiment_id = f'{openid}_{intervention_type}_{int(now)}_{int(now * 1000) % 1000}'
        self.openid = openid
        self.status = 'designed'
        self.created_at = now
        self.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 实验条件
        self.intervention_type = intervention_type  # 'chat' | 'push' | 'companion' | 'probe' | 'coach'
        self.hypothesis = hypothesis  # 系统假设的文本描述
        self.context = {
            'hour': datetime.now().hour,
            'day_of_week': datetime.now().weekday(),
            'timezone': 'Asia/Shanghai',
        }

        # 干预内容
        self.intervention = {
            'type': intervention_type,
            'data': intervention_data or {},
        }

        # 观测结果（在 deploy/observe/conclude 阶段填充）
        self.deployed_at = None
        self.observed_at = None
        self.concluded_at = None
        self.observation = None
        self.outcome = None
        self.conclusion = None

    def to_dict(self):
        return {
            'experiment_id': self.experiment_id,
            'openid': self.openid,
            'status': self.status,
            'created_at': self.created_at,
            'timestamp': self.timestamp,
            'intervention_type': self.intervention_type,
            'hypothesis': self.hypothesis,
            'context': self.context,
            'intervention': self.intervention,
            'deployed_at': self.deployed_at,
            'observed_at': self.observed_at,
            'concluded_at': self.concluded_at,
            'observation': self.observation,
            'outcome': self.outcome,
            'conclusion': self.conclusion,
        }


# ==================== 实验日志存储 ====================

class ExperimentLog:
    """实验日志——存储和查询所有实验记录

    核心能力：
      - log: 记录实验全过程
      - query: 按条件查询历史实验
      - get_effectiveness: 某类型干预在某条件下的有效性统计
      - get_best: 找到历史最佳干预方案
    """

    def __init__(self, path=EXPERIMENT_LOG_PATH):
        self.path = path
        self._lock = None
        try:
            import threading
            self._lock = threading.Lock()
        except Exception:
            pass

    def _load(self):
        """加载所有实验记录"""
        try:
            if os.path.exists(self.path):
                with open(self.path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            _el_log.warning('[ExpLog] Load failed: %s', e)
        return {'experiments': [], 'meta': {'total': 0, 'last_update': ''}}

    def _save(self, data):
        """保存实验记录"""
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _el_log.warning('[ExpLog] Save failed: %s', e)

    def log(self, experiment):
        """记录一个实验

        Args:
            experiment: Experiment 实例
        """
        data = self._load()
        data['experiments'].append(experiment.to_dict())
        # 只保留最近2000条
        if len(data['experiments']) > 2000:
            data['experiments'] = data['experiments'][-2000:]
        data['meta']['total'] = len(data['experiments'])
        data['meta']['last_update'] = datetime.now().isoformat()
        self._save(data)
        _el_log.debug('[ExpLog] Logged %s: %s', experiment.experiment_id[:20], experiment.hypothesis[:40])

    def query(self, openid=None, intervention_type=None, hours_back=72, limit=50):
        """查询历史实验

        Args:
            openid: 用户ID (可选)
            intervention_type: 干预类型 (可选)
            hours_back: 回溯小时数
            limit: 最大返回条数

        Returns:
            list[dict]: 匹配的实验记录
        """
        data = self._load()
        cutoff = time.time() - hours_back * 3600
        results = []

        for exp in data.get('experiments', [])[::-1]:  # 最新在前
            if openid and exp.get('openid') != openid:
                continue
            if intervention_type and exp.get('intervention_type') != intervention_type:
                continue
            if exp.get('created_at', 0) < cutoff:
                continue

            results.append(exp)
            if len(results) >= limit:
                break

        return results

    def get_effectiveness(self, openid=None, intervention_type=None, context_filter=None):
        """统计某操作在某种条件下的有效性

        Args:
            openid: 用户ID
            intervention_type: 干预类型
            context_filter: dict of context条件的精确匹配

        Returns:
            dict: {count, positive_count, effectiveness_ratio, avg_outcome}
                或 None (数据不足)
        """
        data = self._load()
        matching = []

        for exp in data.get('experiments', []):
            if openid and exp.get('openid') != openid:
                continue
            if intervention_type and exp.get('intervention_type') != intervention_type:
                continue
            if exp.get('status') != 'concluded':
                continue
            if exp.get('outcome') is None:
                continue

            # 上下文过滤
            if context_filter:
                exp_ctx = exp.get('context', {})
                match = True
                for k, v in context_filter.items():
                    if exp_ctx.get(k) != v:
                        match = False
                        break
                if not match:
                    continue

            matching.append(exp)

        if not matching:
            return None

        # 统计分析
        total = len(matching)
        positive = sum(1 for e in matching if e.get('outcome', {}).get('positive', False))
        outcomes = [e.get('outcome', {}).get('score_change', 0) for e in matching]
        avg_outcome = sum(outcomes) / len(outcomes) if outcomes else 0

        return {
            'total': total,
            'positive_count': positive,
            'effectiveness_ratio': positive / total if total > 0 else 0,
            'avg_outcome': round(avg_outcome, 2),
            'confidence': 'high' if total >= 5 else ('medium' if total >= 3 else 'low'),
        }

    def get_best_intervention(self, openid, context=None):
        """找到对某用户最有效的干预方式

        主动推理核心：回顾历史 → 选择成功率最高的方案

        Args:
            openid: 用户ID
            context: 当前上下文（小时/星期几）

        Returns:
            dict: {intervention_type, effectiveness_ratio, avg_outcome} 或 None
        """
        data = self._load()
        user_exps = [e for e in data.get('experiments', [])
                     if e.get('openid') == openid and e.get('status') == 'concluded']

        if not user_exps:
            return None

        # 按干预类型分组统计
        type_stats = defaultdict(lambda: {'count': 0, 'positive': 0, 'scores': []})
        for exp in user_exps:
            it = exp.get('intervention_type', 'unknown')
            type_stats[it]['count'] += 1
            if exp.get('outcome', {}).get('positive'):
                type_stats[it]['positive'] += 1
            sc = exp.get('outcome', {}).get('score_change', 0)
            type_stats[it]['scores'].append(sc)

        # 计算每种干预的效果
        results = {}
        for it, stats in type_stats.items():
            if stats['count'] < 2:
                continue  # 数据太少忽略
            avg_score = sum(stats['scores']) / len(stats['scores'])
            ratio = stats['positive'] / stats['count']
            results[it] = {
                'effectiveness_ratio': ratio,
                'avg_outcome': round(avg_score, 2),
                'total': stats['count'],
            }

        if not results:
            return None

        # 按有效性排序
        sorted_results = sorted(results.items(), key=lambda x: x[1]['effectiveness_ratio'], reverse=True)
        return {'best_type': sorted_results[0][0], **sorted_results[0][1]}

    def record_designed(self, experiment):
        """记录实验设计阶段"""
        experiment.status = 'designed'
        self.log(experiment)
        return experiment.experiment_id

    def record_deployed(self, experiment_id):
        """记录实验已执行"""
        data = self._load()
        for exp in data['experiments']:
            if exp.get('experiment_id') == experiment_id:
                exp['status'] = 'deployed'
                exp['deployed_at'] = time.time()
                break
        self._save(data)

    def record_observed(self, experiment_id, observation):
        """记录实验观察结果

        Args:
            experiment_id: 实验ID
            observation: 观测数据 dict (用户说了什么、做了什么)
        """
        data = self._load()
        for exp in data['experiments']:
            if exp.get('experiment_id') == experiment_id:
                exp['status'] = 'observed'
                exp['observed_at'] = time.time()
                exp['observation'] = observation
                break
        self._save(data)

    def record_concluded(self, experiment_id, outcome, conclusion):
        """记录实验结论

        Args:
            experiment_id: 实验ID
            outcome: dict {positive: bool, score_change: float, detail: str}
            conclusion: str 系统学到的内容
        """
        data = self._load()
        for exp in data['experiments']:
            if exp.get('experiment_id') == experiment_id:
                exp['status'] = 'concluded'
                exp['concluded_at'] = time.time()
                exp['outcome'] = outcome
                exp['conclusion'] = conclusion
                break
        self._save(data)


# ==================== 全局实例 ====================

_experiment_log = None

def get_log():
    """获取全局实验日志实例"""
    global _experiment_log
    if _experiment_log is None:
        _experiment_log = ExperimentLog()
    return _experiment_log


# ==================== 主动推理决策集成 ====================

def decide_with_history(openid, current_context, options):
    """主动推理决策：参考历史实验数据决定最佳的干预方式

    替代旧逻辑"score<50→push"：
    查历史中在类似条件下什么最有效，再决定。

    Args:
        openid: 用户ID
        current_context: 当前上下文 dict
        options: list of (干预类型, 干预数据, 假设)

    Returns:
        (best_type, best_data, hypothesis, evidence)
        或 (None, None, None, None) 无有效选项
    """
    log = get_log()

    # 查用户历史的最佳干预方式
    best = log.get_best_intervention(
        openid,
        context={'hour': current_context.get('hour'), 'day_of_week': current_context.get('day_of_week')}
    )

    if best:
        # 匹配选项中的最佳类型
        for opt_type, opt_data, opt_hypothesis in options:
            if opt_type == best['best_type']:
                return opt_type, opt_data, opt_hypothesis, {
                    'evidence': 'experiment_log',
                    'effectiveness_ratio': best['effectiveness_ratio'],
                    'avg_outcome': best['avg_outcome'],
                    'total_samples': best['total'],
                }

    # 无历史或无可选 → 保守：选最简单的
    if options:
        return options[0][0], options[0][1], options[0][2], {'evidence': 'default_fallback'}

    return None, None, None, None


# ==================== 自测 ====================
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    log = get_log()

    # 模拟实验流程
    print('=== Experiment life cycle ===')

    # 设计实验
    exp1 = Experiment(
        openid='test_user',
        intervention_type='push',
        hypothesis='低评分用户收到推送会改善睡眠',
        intervention_data={'score': 45, 'strategy': 'bedtime_early'}
    )
    eid1 = log.record_designed(exp1)
    print(f'  Designed: {eid1[:30]}')

    # 部署
    log.record_deployed(eid1)
    print(f'  Deployed')

    # 观测结果
    log.record_observed(eid1, {'user_replied': True, 'message':'好的我试试'})
    print(f'  Observed: positive reply')

    # 得出结论
    log.record_concluded(eid1, {
        'positive': True,
        'score_change': 5,
        'detail': '用户接受了建议，次日评分提升5分'
    }, '低评分时发固定作息建议有效')
    print(f'  Concluded: positive')

    # 再做几个实验
    for i, (score, positive) in enumerate([(42, True), (38, False), (50, True), (55, True), (48, False)]):
        exp = Experiment('test_user', 'push', '测试', {'score': score})
        eid = log.record_designed(exp)
        log.record_deployed(eid)
        log.record_observed(eid, {'user_replied': positive})
        log.record_concluded(eid, {'positive': positive, 'score_change': 3 if positive else -5},
                             f'实验{i}的结论')
    print(f'  Logged {6} experiments total')

    # 查询
    print('\n=== Query: recent 3 experiments ===')
    results = log.query(openid='test_user', limit=3)
    print(f'  Found {len(results)} results')

    # 有效性统计
    print('\n=== Effectiveness ===')
    eff = log.get_effectiveness(openid='test_user', intervention_type='push')
    if eff:
        print(f'  Push effectiveness: {eff["effectiveness_ratio"]:.0%} ({eff["positive_count"]}/{eff["total"]})')
        print(f'  Avg outcome: {eff["avg_outcome"]:+.1f} pts')
        assert eff['total'] >= 5

    # 最佳干预
    print('\n=== Best intervention ===')
    best = log.get_best_intervention('test_user')
    if best:
        print(f'  Best type: {best["best_type"]} (ratio={best["effectiveness_ratio"]:.0%})')
        assert best['best_type'] == 'push'

    # 主动推理决策
    print('\n=== Active inference decision ===')
    opt_type, opt_data, hyp, evidence = decide_with_history(
        'test_user',
        {'hour': 22, 'day_of_week': 2},
        [('push', {'text': '早睡建议'}, '低评分推早睡有效'),
         ('chat', {'text': '在吗'}, '晚睡时间聊聊天')]
    )
    print(f'  Decided: {opt_type} (evidence: {evidence["evidence"]})')
    assert opt_type == 'push'  # 历史显示push更有效

    # 不同用户无历史数据
    print('\n=== New user (no history) ===')
    opt_type2, _, _, ev2 = decide_with_history(
        'new_user',
        {'hour': 22, 'day_of_week': 2},
        [('chat', {'text': '在吗'}, '新用户先聊聊天')]
    )
    print(f'  Decided: {opt_type2} (evidence: {ev2["evidence"]})')
    assert ev2['evidence'] == 'default_fallback'

    # 清理测试数据
    import os
    if os.path.exists(EXPERIMENT_LOG_PATH):
        os.remove(EXPERIMENT_LOG_PATH)
    print('\nCleanup: test data removed')

    print('\nAll tests PASS!')
