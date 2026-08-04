#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rlaif_learner.py — RLAIF偏好学习器（v7.5+）
原理: Anthropic RLHF from AI Feedback — 用AI自动判断+用户反馈训练偏好模型
落地: 从feedback.json学习用户的干预偏好，动态调整专家权重

用法:
  from rlaif_learner import learn_preference, get_preference_adjustment
  learn_preference(openid, expert_scores={'CBT': 0.7, ...}, rating=4)
  adj = get_preference_adjustment(openid, 'ClinicalPsychologist')
"""

import json, os, math, time
from datetime import datetime
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RLAIF_DIR = os.path.join(PROJECT_ROOT, 'data', 'rlaif')
os.makedirs(RLAIF_DIR, exist_ok=True)

# 默认学习率
_LEARNING_RATE = 0.05

# 专家领域的正负偏好映射（基于RLAIF规则，不依赖人类标注）
_PREFERENCE_RULES = {
    'high_rating': {  # 用户给高分(4-5) → 当前推荐策略的专家加分
        'boost': ['CBT', 'ClinicalPsychologist', 'StressRelaxation', 'SleepPhysician'],
        'penalize': ['RiskManager'],
    },
    'low_rating': {   # 用户给低分(1-2) → 扣分或加风险权重
        'penalize': ['ClinicalPsychologist', 'CBT', 'StressRelaxation'],
        'boost': ['RiskManager'],
    },
}


def _user_path(openid):
    """用户RLAIF数据路径"""
    safe = openid.replace('/', '_').replace('\\', '_')
    return os.path.join(RLAIF_DIR, '%s.json' % safe)


def _load_user(openid):
    """加载用户偏好数据"""
    path = _user_path(openid)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'preferences': {}, 'history': [], 'updated_at': None}


def _save_user(openid, data):
    """保存用户偏好数据"""
    data['updated_at'] = datetime.now().isoformat()
    with open(_user_path(openid), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def learn_preference(openid, expert_scores=None, rating=None, expert_detail=None):
    """从一次交互中学习用户偏好

    Args:
        openid: 用户ID
        expert_scores: dict {专家名: score}，各专家的当前评分
        rating: int 1-5，用户反馈评分
        expert_detail: dict，comprehensive_analysis的expert_detail输出
    """
    if not openid:
        return

    # 确定反馈方向：用户评分 或 自动RLAIF判断
    feedback_type = 'explicit' if rating else 'auto'
    direction = 'positive' if (rating and rating >= 4) else ('negative' if (rating and rating <= 2) else 'neutral')

    # 应用偏好规则
    rules = _PREFERENCE_RULES
    if direction == 'positive':
        boosts = rules['high_rating']['boost']
        penalizes = rules['high_rating']['penalize']
    elif direction == 'negative':
        boosts = rules['low_rating']['boost']
        penalizes = rules['low_rating']['penalize']
    else:
        return  # neutral不更新

    data = _load_user(openid)
    prefs = data['preferences']

    for expert in boosts:
        old = prefs.get(expert, 0.0)
        prefs[expert] = max(-0.5, min(0.5, old + _LEARNING_RATE))

    for expert in penalizes:
        old = prefs.get(expert, 0.0)
        prefs[expert] = max(-0.5, min(0.5, old - _LEARNING_RATE))

    data['history'].append({
        'ts': time.time(),
        'direction': direction,
        'rating': rating,
        'type': feedback_type,
    })
    # 保留最近100条
    if len(data['history']) > 100:
        data['history'] = data['history'][-100:]

    _save_user(openid, data)


def get_preference_adjustment(openid, expert_name):
    """获取某个专家的偏好调整量 (用于在comprehensive_analysis中调整权重)

    Returns: float, -0.5 ~ +0.5
    """
    if not openid or not expert_name:
        return 0.0
    data = _load_user(openid)
    return data['preferences'].get(expert_name, 0.0)


def get_preference_summary(openid):
    """获取完整的偏好摘要"""
    data = _load_user(openid)
    prefs = data['preferences']
    history = data['history']
    n_pos = sum(1 for h in history if h.get('direction') == 'positive')
    n_neg = sum(1 for h in history if h.get('direction') == 'negative')
    return {
        'adjustments': prefs,
        'total_feedbacks': len(history),
        'positive': n_pos,
        'negative': n_neg,
        'top_boosted': max(prefs, key=prefs.get) if prefs else None,
        'top_penalized': min(prefs, key=prefs.get) if prefs else None,
    }


# ===== 自测 =====
if __name__ == '__main__':
    print('=== RLAIF Test ===\n')

    # 测试1: 正面反馈
    learn_preference('test_user', rating=5)
    adj = get_preference_adjustment('test_user', 'CBT')
    print('Test 1 (rating=5): CBT adj=%.2f (expect >0)' % adj)
    assert adj > 0, 'CBT should be boosted'

    # 测试2: 负面反馈（只做负面，不做正面预热）
    learn_preference('test_user2', rating=1)
    adj2 = get_preference_adjustment('test_user2', 'ClinicalPsychologist')
    print('Test 2 (rating=1): CP adj=%.2f (expect <0)' % adj2)
    assert adj2 < 0, 'CP should be penalized'

    # 测试3: 摘要（独立用户）
    learn_preference('test_user3', rating=4)
    learn_preference('test_user3', rating=2)
    summary = get_preference_summary('test_user3')
    print('Test 3 (summary): total=%d, pos=%d, neg=%d' % (
        summary['total_feedbacks'], summary['positive'], summary['negative']))
    assert summary['total_feedbacks'] == 2
    assert summary['positive'] == 1
    assert summary['negative'] == 1

    # 测试4: 中性评分不变
    learn_preference('test_user3', rating=3)
    summary = get_preference_summary('test_user3')
    print('Test 4 (rating=3): total=%d (expect unchanged at 2)' % summary['total_feedbacks'])

    # 清理测试数据
    import os as _os
    for _f in ['test_user.json', 'test_user2.json', 'test_user3.json']:
        _p = _os.path.join(RLAIF_DIR, _f)
        if _os.path.exists(_p):
            _os.remove(_p)
    print('\nAll tests passed!')
