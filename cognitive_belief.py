#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cognitive_belief.py — 认知信念模型 v1.0

不修改POMDP状态空间，作为独立附加上下文维护4维认知信念。
每次用户交互后更新，供决策引擎/世界模型消费。

信念维度：
  self_efficacy       自我效能感：相信自己能睡好 (0~1)
  catastrophic_expect 灾难化预期：默认"今晚又睡不着" (0~1)
  treatment_trust     治疗信赖度：对AI建议的信任 (0~1)
  sleep_effort        睡眠努力：越努力越睡不着(反向) (0~1)

更新规则：
  - 评分升高 → self_efficacy↑，catastrophic_expect↓
  - 正面反馈 → treatment_trust↑
  - 持续低分 → sleep_effort↑（过度努力）
"""

import os, json, math, time
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

BELIEF_DIR = os.path.join(PROJECT_ROOT, 'user_pomdp')

FIELDS = [
    'self_efficacy',
    'catastrophic_expect',
    'treatment_trust',
    'sleep_effort',
]

DEFAULT = {
    'self_efficacy': 0.50,
    'catastrophic_expect': 0.50,
    'treatment_trust': 0.50,
    'sleep_effort': 0.30,
}

# 更新速率（每次交互的变化幅度）
LR = 0.15


def load(openid):
    """加载认知信念，不存在则返回默认值"""
    try:
        path = os.path.join(BELIEF_DIR, f'{openid}_cognitive.json')
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
    except:
        pass
    return dict(DEFAULT)


def save(openid, beliefs):
    """持久化认知信念"""
    try:
        os.makedirs(BELIEF_DIR, exist_ok=True)
        path = os.path.join(BELIEF_DIR, f'{openid}_cognitive.json')
        with open(path, 'w') as f:
            json.dump(beliefs, f, indent=2)
    except:
        pass


def update(openid, score=None, mood=None, feedback=1, effect=None,
           score_change=0, follow_up=False):
    """根据一次交互更新认知信念

    Args:
        score: 本次睡眠评分 (0-100)
        mood: 情绪文本（包含'好'/'坏'/'放松'/'焦虑'等关键词）
        feedback: 用户反馈 (1=正面, 0=中性, -1=负面)
        effect: 干预效果 (0=无, 1=微弱, 2=明显)
        score_change: 评分变化量（相对上次）
        follow_up: 用户是否跟随了上次建议
    """
    bel = load(openid)
    now = time.time()

    # 1. 评分驱动的信念更新
    if score is not None:
        # 高分 → 增强自我效能，降低灾难化预期
        score_norm = score / 100.0
        # 以 0.5 为分界，高于则正向，低于则负向
        score_signal = score_norm - 0.5

        if score_signal > 0:
            # 好睡眠：自我效能↑，灾难化↓
            bel['self_efficacy'] = min(1.0, bel['self_efficacy'] + LR * score_signal)
            bel['catastrophic_expect'] = max(0.0, bel['catastrophic_expect'] - LR * score_signal * 0.7)
            # 分数正常时睡眠努力↓
            bel['sleep_effort'] = max(0.0, bel['sleep_effort'] - LR * 0.3)
        else:
            # 差睡眠：自我效能↓，灾难化↑
            bel['self_efficacy'] = max(0.0, bel['self_efficacy'] + LR * score_signal * 1.5)
            bel['catastrophic_expect'] = min(1.0, bel['catastrophic_expect'] - LR * score_signal * 2.0)
            # 持续差 → 睡眠努力↑（越努力越睡不着）
            if score_norm < 0.3:
                bel['sleep_effort'] = min(1.0, bel['sleep_effort'] + LR * 0.5)

    # 2. 评分变化 → 敏感检测
    if score_change != 0:
        # 大幅改善 → 治疗信赖↑
        if score_change > 15:
            bel['treatment_trust'] = min(1.0, bel['treatment_trust'] + LR * 0.5)
        # 大幅恶化 → 治疗信赖↓
        elif score_change < -15:
            bel['treatment_trust'] = max(0.0, bel['treatment_trust'] - LR * 0.3)

    # 3. 用户反馈驱动的信赖更新
    if feedback > 0:
        bel['treatment_trust'] = min(1.0, bel['treatment_trust'] + LR * 0.3)
    elif feedback < 0:
        bel['treatment_trust'] = max(0.0, bel['treatment_trust'] - LR * 0.5)
        # 负面反馈也轻微降低自我效能
        bel['self_efficacy'] = max(0.0, bel['self_efficacy'] - LR * 0.2)

    # 4. 干预效果
    if effect is not None and effect > 0:
        bel['treatment_trust'] = min(1.0, bel['treatment_trust'] + LR * 0.2 * effect)
        bel['sleep_effort'] = max(0.0, bel['sleep_effort'] - LR * 0.1 * effect)

    # 5. 随访行为
    if follow_up:
        bel['treatment_trust'] = min(1.0, bel['treatment_trust'] + LR * 0.1)

    # 6. 情绪关键词
    if mood:
        mood = str(mood).lower()
        positive_kw = ['好', '放松', '平静', 'ok', 'good', 'relax']
        negative_kw = ['焦虑', '紧张', '坏', '累', '烦', 'stress', 'anxious']
        if any(k in mood for k in positive_kw):
            bel['self_efficacy'] = min(1.0, bel['self_efficacy'] + LR * 0.2)
            bel['catastrophic_expect'] = max(0.0, bel['catastrophic_expect'] - LR * 0.2)
        elif any(k in mood for k in negative_kw):
            bel['self_efficacy'] = max(0.0, bel['self_efficacy'] - LR * 0.2)
            bel['catastrophic_expect'] = min(1.0, bel['catastrophic_expect'] + LR * 0.3)

    save(openid, bel)
    return dict(bel)


def summary_str(openid):
    """返回可读的认知信念摘要"""
    bel = load(openid)
    lines = [
        f'自我效能感: {bel["self_efficacy"]:.0%}',
        f'灾难化预期: {bel["catastrophic_expect"]:.0%}',
        f'治疗信赖度: {bel["treatment_trust"]:.0%}',
        f'睡眠努力度: {bel["sleep_effort"]:.0%}',
    ]
    return ' | '.join(lines)


def profile_summary(openid):
    """供 dp_router 调用的文本摘要（注入到AI prompt）"""
    bel = load(openid)
    parts = []
    if bel['self_efficacy'] < 0.3:
        parts.append('用户明显缺乏睡眠信心')
    elif bel['self_efficacy'] > 0.7:
        parts.append('用户对睡眠有较高自信')

    if bel['catastrophic_expect'] > 0.6:
        parts.append(f'存在灾难化预期倾向（{bel["catastrophic_expect"]:.0%}）')

    if bel['treatment_trust'] < 0.3:
        parts.append('用户对AI建议信任度偏低')
    elif bel['treatment_trust'] > 0.7:
        parts.append('用户对AI建议接受度良好')

    if bel['sleep_effort'] > 0.7:
        parts.append('用户存在过度努力睡眠的问题（越努力越睡不着）')

    if parts:
        return '认知信念: ' + '；'.join(parts)
    return ''


# ===== 自测 =====
if __name__ == '__main__':
    print('=== Cognitive Belief Self-Test ===')

    # 清理测试文件
    import os as _os
    _test_path = _os.path.join(BELIEF_DIR, 'test_cog_user_cognitive.json')
    if _os.path.exists(_test_path):
        _os.remove(_test_path)

    # 1. 新用户获取默认值
    bel = load('test_cog_user')
    print(f'1. Default beliefs: {bel}')
    assert all(k in bel for k in FIELDS), 'Missing fields'
    assert bel['self_efficacy'] == 0.50

    # 2. 高分更新
    update('test_cog_user', score=85, feedback=1)
    bel = load('test_cog_user')
    print(f'2. After good score (85): self_efficacy={bel["self_efficacy"]:.2f}')
    assert bel['self_efficacy'] > 0.50
    assert bel['catastrophic_expect'] < 0.50

    # 3. 连续低分
    update('test_cog_user', score=25, feedback=-1)
    update('test_cog_user', score=20, feedback=-1)
    bel = load('test_cog_user')
    print(f'3. After bad scores: sleep_effort={bel["sleep_effort"]:.2f}')
    assert bel['sleep_effort'] > 0.30

    # 4. 负面情绪
    update('test_cog_user', mood='焦虑紧张', feedback=-1)
    bel = load('test_cog_user')
    print(f'4. After anxiety: catastrophic_expect={bel["catastrophic_expect"]:.2f}')
    assert bel['catastrophic_expect'] > 0.3

    # 5. 正反馈恢复
    update('test_cog_user', score=75, feedback=1, follow_up=True)
    bel = load('test_cog_user')
    print(f'5. After recovery: treatment_trust={bel["treatment_trust"]:.2f}')
    assert bel['treatment_trust'] > 0.35

    print(f'\nSummary: {summary_str("test_cog_user")}')
    print(f'Profile: {profile_summary("test_cog_user")}')
    print('\nAll cognitive belief tests PASS!')
