#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
baowang_emulator.py — 至尊宝行为模型 v1

"学会跟唯一重要的那个人对话。"

设计原则：
  1. 不是读心术，是行为倾向预测
  2. 内建反信息茧房（每5次输出1次随机偏离）
  3. 输出是加权信号不是唯一指令
  4. 记录反悔率——至尊宝可以今天说大明天说小

信号维度:
  - scale_preference: 0~1 (0=小修小补, 1=大规模改动)
  - risk_tolerance: 0~1 (0=保守, 1=激进)
  - detail_level: 0~1 (0=只看结论, 1=看全部技术细节)
  - creativity_bias: 0~1 (0=标准实践, 1=肆意创造)
  - patience: 0~1 (0=快出结论, 1=可以慢慢想)

反信息茧房机制:
  - 探索率: 20%的概率输出与预测相反的方向
  - 反悔追踪: 如果连续2次预测被打脸→自动降低该维度权重
  - 多假设: 同时维护3个不同版本的"至尊宝画像"，投票输出
"""

import json, os, re, time, sys, math, random
from collections import deque, defaultdict

sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\AISleepGen_Optimized'
DATA_DIR = os.path.join(BASE, 'data')
MODEL_PATH = os.path.join(DATA_DIR, 'baowang_model.json')
EMOTION_PATH = os.path.join(DATA_DIR, 'implicit_signals.json')
LOG_PATH = os.path.join(BASE, 'logs', 'baowang.log')

# ═══ 初始画像（无数据时的假设） ═══
INITIAL_PROFILES = {
    # 画像A: 大胆革新派
    'bold': {
        'scale_preference': 0.8,
        'risk_tolerance': 0.7,
        'detail_level': 0.4,
        'creativity_bias': 0.8,
        'patience': 0.6,
        'weight': 1.0,
    },
    # 画像B: 务实标准派
    'pragmatic': {
        'scale_preference': 0.4,
        'risk_tolerance': 0.3,
        'detail_level': 0.7,
        'creativity_bias': 0.3,
        'patience': 0.4,
        'weight': 1.0,
    },
    # 画像C: 挑剔完美派
    'perfectionist': {
        'scale_preference': 0.6,
        'risk_tolerance': 0.5,
        'detail_level': 0.9,
        'creativity_bias': 0.5,
        'patience': 0.8,
        'weight': 1.0,
    },
}


def _log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(f'[{ts}] {msg}\n')
    # 打印也用安全方式
    safe = msg.encode('utf-8', errors='replace').decode('utf-8')
    print(f'  [{ts}] {safe}')


class BaowangModel:
    """
    至尊宝行为模型
    
    使用方式：
        bm = BaowangModel()
        advice = bm.advise()  # 获取行为建议
        bm.record_response('大')  # 记录至尊宝的反馈
    """
    
    def __init__(self):
        self.profiles = self._load()
        self._history = deque(maxlen=100)
        self._reversals = deque(maxlen=20)  # 反悔记录
        self._last_advice = None
        
        # 反信息茧房
        self._exploration_rate = 0.2
        self._consecutive_hits = 0
        self._exploration_count = 0
        
        self._load_signals()
    
    def _load(self):
        if os.path.exists(MODEL_PATH):
            try:
                with open(MODEL_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return dict(INITIAL_PROFILES)
    
    def _save(self):
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        # 序列化前清理
        save = {}
        for k, v in self.profiles.items():
            save[k] = {kk: vv for kk, vv in v.items() if isinstance(vv, (int, float, str))}
        with open(MODEL_PATH, 'w', encoding='utf-8') as f:
            json.dump(save, f, ensure_ascii=False, indent=2)
    
    def _load_signals(self):
        """加载隐性反馈信号"""
        try:
            if os.path.exists(EMOTION_PATH):
                with open(EMOTION_PATH, 'r', encoding='utf-8') as f:
                    sig = json.load(f)
                self._current_mode = sig.get('current_mode', 'converge')
                self._challenge = sig.get('challenge_level', 0.0)
                self._creativity = sig.get('creativity_pull', 0.3)
            else:
                self._current_mode = 'converge'
                self._challenge = 0.0
                self._creativity = 0.3
        except:
            self._current_mode = 'converge'
            self._challenge = 0.0
            self._creativity = 0.3
    
    def _weigh_profiles(self):
        """
        加权投票：根据信号调整各画像权重
        
        信号→权重调整：
          - challenge高 → perfectionist权重上升
          - creativity高 → bold权重上升
          - mode=converge → pragmatic权重上升
        """
        weights = {}
        
        for name in self.profiles:
            base = self.profiles[name].get('weight', 1.0)
            
            # 调整因子
            if name == 'bold':
                weight = base * (1 + self._creativity * 0.5) * (1 + self._challenge * 0.3)
            elif name == 'pragmatic':
                conv = 1.0 if self._current_mode == 'converge' else 0.5
                weight = base * conv
            elif name == 'perfectionist':
                weight = base * (1 + self._challenge * 0.5)
            else:
                weight = base
            
            weights[name] = max(0.1, weight)
        
        # 归一化
        total = sum(weights.values())
        if total > 0:
            for name in weights:
                weights[name] /= total
        
        return weights
    
    def _ensemble_output(self, weights):
        """
        多画像加权投票输出
        
        反信息茧房：20%概率故意偏离预测
        """
        dims = ['scale_preference', 'risk_tolerance', 'detail_level', 'creativity_bias', 'patience']
        output = {}
        
        for dim in dims:
            # 加权平均
            value = sum(
                self.profiles[p].get(dim, 0.5) * weights.get(p, 0)
                for p in self.profiles
            )
            
            # 反信息茧房: 20%概率输出反方向
            if random.random() < self._exploration_rate:
                self._exploration_count += 1
                # 输出相反方向（偏离均值到另一侧）
                deviation = 0.3
                if value > 0.5:
                    value = max(0.1, value - deviation - random.random() * 0.2)
                else:
                    value = min(0.9, value + deviation + random.random() * 0.2)
                _log(f'[Anti-Bubble] 探索偏离: {dim}={value:.2f} (原均值≈{sum(self.profiles[p].get(dim,0.5)*weights.get(p,0) for p in self.profiles)})')
            
            output[dim] = round(max(0.05, min(0.95, value)), 2)
        
        return output
    
    def _generate_advice_text(self, output):
        """基于输出生成行为建议"""
        scale = output['scale_preference']
        risk = output['risk_tolerance']
        creativity = output['creativity_bias']
        detail = output['detail_level']
        patience = output['patience']
        
        if scale > 0.7 and risk > 0.6:
            action = '大规模架构级改动'
        elif scale > 0.5:
            action = '中等规模模块改造'
        elif scale > 0.3:
            action = '针对性补丁'
        else:
            action = '维持现有结构，微调参数'
        
        if creativity > 0.6:
            style = '自由创造，不设边界'
        else:
            style = '按最佳实践标准推进'
        
        if detail > 0.6:
            report = '详细技术文档'
        else:
            report = '结论摘要'
        
        return {
            'recommended_action': action,
            'recommended_style': style,
            'recommended_report': report,
            'detail': {
                'scale_preference': scale,
                'risk_tolerance': risk,
                'creativity_bias': creativity,
                'detail_level': detail,
                'patience': patience,
            }
        }
    
    def advise(self):
        """
        主接口：获取基于至尊宝行为模型的行为建议
        
        返回: dict 包含行为建议
        """
        self._load_signals()
        weights = self._weigh_profiles()
        output = self._ensemble_output(weights)
        advice = self._generate_advice_text(output)
        
        self._last_advice = advice
        
        # 记录
        self._history.append({
            'ts': time.time(),
            'weights': {k: round(v, 2) for k, v in weights.items()},
            'output': output,
            'advice': advice,
        })
        
        _log(f'画像权重: {weights}')
        _log(f'行为输出: scale={output["scale_preference"]} risk={output["risk_tolerance"]} '
             f'creativity={output["creativity_bias"]} detail={output["detail_level"]} patience={output["patience"]}')
        _log(f'建议: {advice["recommended_action"]} / {advice["recommended_style"]}')
        
        return advice
    
    def record_feedback(self, feedback_text):
        """
        记录至尊宝对产出的反馈（用于模型修正）
        
        feedback_text: str — 至尊宝说的任何话
        """
        if not self._last_advice:
            return
        
        # 分析反馈是"认可"还是"纠正"
        approval_signals = ['好', '对', '可以', '继续', '不错', '干', '就是', 'yes', 'YES']
        correction_signals = ['不是', '不够', '太小', '太大', '不行', '错', 'no', 'NO', '就这么点']
        
        approval_count = sum(1 for s in approval_signals if s in feedback_text)
        correction_count = sum(1 for s in correction_signals if s in feedback_text)
        
        if correction_count > approval_count:
            # 被纠正了 → 调整权重
            _log(f'至尊宝反馈: 纠正 ({feedback_text[:40]})')
            
            # 判断纠正方向
            if any(s in feedback_text for s in ['大', '更多', '更强', '顶尖']):
                # 至尊宝觉得不够大 → 上调bold权重
                for name in self.profiles:
                    if name == 'bold':
                        self.profiles[name]['weight'] = self.profiles[name].get('weight', 1.0) * 1.3
                    elif name == 'pragmatic':
                        self.profiles[name]['weight'] = self.profiles[name].get('weight', 1.0) * 0.85
            
            elif any(s in feedback_text for s in ['小', '收敛', '标准', '最佳实践']):
                # 至尊宝觉得不够稳 → 上调pragmatic
                for name in self.profiles:
                    if name == 'pragmatic':
                        self.profiles[name]['weight'] = self.profiles[name].get('weight', 1.0) * 1.3
                    elif name == 'bold':
                        self.profiles[name]['weight'] = self.profiles[name].get('weight', 1.0) * 0.85
            
            # 反悔追踪
            self._reversals.append({
                'ts': time.time(),
                'before_advice': self._last_advice,
                'feedback': feedback_text[:50],
            })
            
            # 如果连续反悔 → 降低反信息茧房探索率
            if len(self._reversals) >= 3:
                recent = list(self._reversals)[-3:]
                # 看最近3次有没有相似的反悔模式
                patterns = [r['feedback'] for r in recent]
                if any('大' in p for p in patterns) and any('小' in p for p in patterns):
                    # 至尊宝在大小之间反复 → 降低探索率（我更应该听直觉）
                    self._exploration_rate = max(0.05, self._exploration_rate * 0.8)
                    _log(f'检测到反悔模式: 降低探索率至{self._exploration_rate}')
        
        elif approval_count > 0:
            _log(f'至尊宝反馈: 认可')
            self._consecutive_hits += 1
            # 连续命中 → 该画像的权重稳定可加固
            if self._consecutive_hits >= 3:
                for name in self.profiles:
                    w = self.profiles[name].get('weight', 1.0)
                    self.profiles[name]['weight'] = min(3.0, w * 1.05)
                self._consecutive_hits = 0
        
        self._save()
    
    def get_state(self):
        """获取当前模型状态"""
        weights = self._weigh_profiles()
        return {
            'profiles': {k: {kk: round(vv, 2) for kk, vv in v.items() if isinstance(vv, (int, float))} 
                        for k, v in self.profiles.items()},
            'active_weights': {k: round(v, 2) for k, v in weights.items()},
            'exploration_rate': round(self._exploration_rate, 3),
            'total_reversals': len(self._reversals),
            'history_size': len(self._history),
        }


def decode():
    """心跳调用接口"""
    bm = BaowangModel()
    advice = bm.advise()
    return advice


if __name__ == '__main__':
    print('至尊宝行为模型 v1')
    print('=' * 40)
    
    bm = BaowangModel()
    
    # 模拟：至尊宝连续说"就这么点改变"（纠正→太小）
    bm.record_feedback('就这么点改变？你就做了这么点东西？')
    bm.advise()
    
    bm.record_feedback('不够大')
    bm.advise()
    
    # 看画像变化
    state = bm.get_state()
    print(f'\n模型状态:')
    print(f'  画像权重: {state["active_weights"]}')
    print(f'  探索率: {state["exploration_rate"]}')
    print(f'  反悔次数: {state["total_reversals"]}')
    
    # 看最新建议
    advice = bm.advise()
    print(f'\n当前建议:')
    print(f'  动作: {advice["recommended_action"]}')
    print(f'  风格: {advice["recommended_style"]}')
    print(f'  汇报: {advice["recommended_report"]}')
    print(f'  细节: {advice["detail"]}')
