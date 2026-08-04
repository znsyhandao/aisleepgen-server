#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ewc_memory.py — Elastic Weight Consolidation for AISleepGen
Sensory Neurons (DeepMind): 弹性权重巩固，防止模型遗忘早期用户数据

原理：
  EWC在贝叶斯框架下保护对旧任务重要的参数。
  Fisher信息矩阵对角线元素衡量每个参数对旧任务的重要性。
  新任务的损失函数加上 EWC 惩罚项防止关键参数漂移。

用法：
  from ewc_memory import EWCWrapper
  wrapper = EWCWrapper(initial_params)
  # 每次更新模型参数后：
  wrapper.consolidate(new_params, data_weight=1.0)
  # 在新任务中计算 loss 时：
  total_loss = task_loss + wrapper.ewc_penalty(current_params)
"""

import math, json, os
from datetime import datetime


# 默认 EWC 超参数
_DEFAULT_LAMBDA = 100.0  # EWC正则强度


class EWCWrapper:
    """EWC 包装器：保护用户早期学习到的参数不被遗忘"""

    def __init__(self, initial_params=None, ewc_lambda=_DEFAULT_LAMBDA):
        """
        Args:
            initial_params: dict {param_name: float} — 初始模型参数
            ewc_lambda: float — EWC正则强度
        """
        self.ewc_lambda = ewc_lambda
        self.params_star = {}        # 锚定参数（旧任务最优）
        self.fisher = {}             # Fisher信息矩阵对角线
        self._updates = 0            # consolidate调用次数

        if initial_params:
            self.params_star = dict(initial_params)
            # 初始 Fisher：所有参数等权重
            for k in initial_params:
                self.fisher[k] = 1.0

    def consolidate(self, new_params, data_weight=1.0):
        """在新数据上更新后，巩固 EWC 锚定参数

        使用滑动平均更新 Fisher 信息矩阵和参数锚点。

        Args:
            new_params: dict — 更新后的模型参数
            data_weight: float — 新数据的重要性权重
        """
        self._updates += 1
        # Fisher 用较慢的滑动平均，防止被单次更新冲淡
        fisher_alpha = 0.1
        param_alpha = 0.3

        if not self.params_star:
            self.params_star = dict(new_params)
            for k in new_params:
                self.fisher[k] = 1.0
            return

        # 1. 更新 Fisher 信息矩阵
        for k in new_params:
            old = self.params_star.get(k, 0.0)
            new = new_params[k]
            delta_sq = (new - old) ** 2
            self.fisher[k] = (1 - fisher_alpha) * self.fisher.get(k, 1.0) + fisher_alpha * delta_sq * data_weight

        # 2. 更新锚定参数（更慢的滑动平均，保护旧知识）
        for k in new_params:
            old_star = self.params_star.get(k, 0.0)
            self.params_star[k] = (1 - param_alpha) * old_star + param_alpha * new_params[k]

    def ewc_penalty(self, current_params):
        """计算 EWC 惩罚项

        Args:
            current_params: dict — 当前模型参数

        Returns:
            float — EWC 惩罚值
        """
        if not self.params_star:
            return 0.0
        penalty = 0.0
        for k in current_params:
            if k in self.params_star and k in self.fisher:
                diff = current_params[k] - self.params_star[k]
                penalty += 0.5 * self.fisher[k] * diff * diff
        return self.ewc_lambda * penalty

    def get_importance(self, param_name):
        """获取某个参数的重要性（Fisher值）"""
        return self.fisher.get(param_name, 0.0)

    def summary(self):
        """返回摘要"""
        if not self.params_star:
            return "EWC: no data"
        n_params = len(self.params_star)
        avg_fisher = sum(self.fisher.values()) / max(len(self.fisher), 1)
        return (f"EWC: {n_params} params, "
                f"avg_Fisher={avg_fisher:.4f}, "
                f"lambda={self.ewc_lambda}, "
                f"updates={self._updates}")

    def to_dict(self):
        """序列化"""
        return {
            'params_star': self.params_star,
            'fisher': self.fisher,
            'ewc_lambda': self.ewc_lambda,
            'updates': self._updates,
        }

    @classmethod
    def from_dict(cls, data):
        """反序列化"""
        wrapper = cls(ewc_lambda=data.get('ewc_lambda', _DEFAULT_LAMBDA))
        wrapper.params_star = data.get('params_star', {})
        wrapper.fisher = data.get('fisher', {})
        wrapper._updates = data.get('updates', 0)
        return wrapper


# ===== 分用户持久化的 EWC 管理器 =====
_EWC_REGISTRY = {}  # {openid: EWCWrapper}


def get_ewc(openid):
    """获取或创建用户的 EWC wrapper"""
    if openid not in _EWC_REGISTRY:
        _EWC_REGISTRY[openid] = EWCWrapper()
    return _EWC_REGISTRY[openid]


def consolidate_user(openid, new_params, data_weight=1.0):
    """便捷函数：巩固用户参数"""
    ewc = get_ewc(openid)
    ewc.consolidate(new_params, data_weight)
    return ewc


def ewc_penalty_for_user(openid, current_params):
    """便捷函数：计算用户的 EWC 惩罚"""
    ewc = get_ewc(openid)
    return ewc.ewc_penalty(current_params)


# ===== 自测 =====
if __name__ == '__main__':
    print('=== EWC Memory Test ===\n')

    # 测试1: 初始参数
    params1 = {'se': 0.5, 'duration': 0.3, 'latency': 0.2}
    w = EWCWrapper(params1)
    print('Init:', w.summary())

    # 测试2: 新数据（小变化）
    params2 = {'se': 0.55, 'duration': 0.32, 'latency': 0.18}
    w.consolidate(params2, data_weight=0.5)
    print('After 1 update:', w.summary())

    # 测试3: 重大变化（应产生高 penalty）
    params3 = {'se': 0.9, 'duration': 0.1, 'latency': 0.0}
    penalty = w.ewc_penalty(params3)
    print(f'Penalty for drastic change: {penalty:.4f}')
    assert penalty > 0.5, f'Penalty too low: {penalty}'

    # 测试4: 小变化（低 penalty）
    params4 = {'se': 0.54, 'duration': 0.31, 'latency': 0.19}
    penalty = w.ewc_penalty(params4)
    print(f'Penalty for small change: {penalty:.4f}')
    assert penalty < 0.5, f'Penalty too high: {penalty}'

    # 测试5: consolidate_user 便捷函数
    cu = consolidate_user('test_user', {'a': 1.0, 'b': 2.0})
    print(f'Registry: user EWC={cu.summary()}')

    print('\nAll tests passed!')
