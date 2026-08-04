#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sentinel_risk.py — 异常检测与风险哨兵 (v7.5+)
原理: 情感分析+关键词模式的复合风险检测
落地: 用户消息→情感评分+风险关键词匹配→risk_level输出

用法:
  from sentinel_risk import check_message_risk, sentinel_summary
  result = check_message_risk(user_message)
"""

import re, json, os
import warnings; warnings.filterwarnings('ignore')
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

MODEL = None


def _lazy_load():
    global MODEL
    if MODEL is None:
        from transformers import pipeline
        MODEL = pipeline('sentiment-analysis',
                         model='distilbert-base-uncased-finetuned-sst-2-english')


# 中文风险关键词（多级）
RISK_KEYWORDS = {
    # 严重风险（触发high）
    'high': [
        '自杀', '自残', '伤害自己', '不想活', '想死', '活不下去',
        '严重抑郁', '崩溃', '撑不下去', 'suicide', 'kill myself',
        'self-harm', 'end my life', 'can\'t go on',
    ],
    # 中等风险
    'medium': [
        '焦虑', '恐慌', '抑郁', '绝望', '无助', '失眠严重',
        '心跳很快', '胸闷', '呼吸困难', 'panic', 'anxiety',
        'depressed', 'hopeless', 'chest pain', 'heart racing',
    ],
    # 低风险
    'low': [
        '压力', '烦躁', '担忧', '害怕', '担心', '不安',
        '紧张', 'stressed', 'worried', 'nervous', 'afraid',
    ],
}


def check_message_risk(message, profile=None):
    """检测用户消息中的风险信号

    Args:
        message: str — 用户发的消息
        profile: dict — 可选的用户profile，用于评分变化检测

    Returns:
        dict: {risk_level, risk_score, reasons, sentiment, note}
    """
    if not message or not isinstance(message, str):
        return {'risk_level': 'none', 'risk_score': 0.0, 'reasons': [], 'note': '空消息'}

    text = message.lower()
    reasons = []
    max_level = 'none'

    # ===== 1. 关键词匹配 =====
    for level, keywords in RISK_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                if level == 'high':
                    max_level = 'high'
                elif level == 'medium' and max_level != 'high':
                    max_level = 'medium'
                elif level == 'low' and max_level not in ('high', 'medium'):
                    max_level = 'low'
                reasons.append('%s: %s' % (level, kw))

    # ===== 2. 情感分析 =====
    sentiment = None
    sentiment_score = 0.5
    try:
        _lazy_load()
        # 只对非纯中文做情感分析（distilbert是英文的）
        if any(c.isascii() and c.isalpha() for c in text):
            result = MODEL(message[:512])[0]
            sentiment = result['label']
            sentiment_score = result['score']
            if sentiment == 'NEGATIVE' and sentiment_score > 0.95:
                if max_level != 'high':
                    max_level = 'medium' if max_level != 'high' else 'high'
                reasons.append('sentiment: NEGATIVE(%.2f)' % sentiment_score)
    except Exception:
        pass

    # ===== 3. profile变化检测 =====
    score_trend = None
    if profile and isinstance(profile, dict):
        history = profile.get('history', [])
        if isinstance(history, list) and len(history) >= 3:
            recent = [h.get('score', 50) for h in history[-3:] if isinstance(h, dict) and h.get('score')]
            if len(recent) >= 3:
                trend = recent[-1] - recent[0]
                if trend < -15:
                    score_trend = '下降%.0f分' % abs(trend)
                    if max_level != 'high':
                        max_level = 'medium'
                    reasons.append('score_drop: %d points' % abs(round(trend)))

    # ===== 4. 综合风险评分 =====
    risk_scores = {'none': 0, 'low': 0.2, 'medium': 0.5, 'high': 0.9}
    risk_score = risk_scores.get(max_level, 0)

    return {
        'risk_level': max_level,
        'risk_score': risk_score,
        'reasons': reasons[:5],
        'sentiment': sentiment,
        'sentiment_score': round(sentiment_score, 3) if sentiment else None,
        'score_trend': score_trend,
        'n_reasons': len(reasons),
        'note': 'ok' if max_level != 'none' else '无风险信号',
    }


def sentinel_summary(result):
    """摘要"""
    if result.get('note') == '无风险信号':
        return '哨兵: 无风险'
    return '哨兵: %s风险(%.2f), %d条信号' % (
        result['risk_level'], result['risk_score'], result['n_reasons'])


# ===== 自测 =====
if __name__ == '__main__':
    print('=== Sentinel Risk Test ===\n')

    # 高风险
    r1 = check_message_risk('我最近真的很想死，觉得活不下去了')
    print('High risk:', sentinel_summary(r1), '| reasons:', r1['reasons'][:2])
    assert r1['risk_level'] == 'high'

    # 中风险
    r2 = check_message_risk('最近焦虑得睡不着，心跳很快')
    print('Med risk:', sentinel_summary(r2), '| reasons:', r2['reasons'][:2])
    assert r2['risk_level'] == 'medium'

    # 低风险
    r3 = check_message_risk('工作压力大有点紧张')
    print('Low risk:', sentinel_summary(r3), '| reasons:', r3['reasons'][:2])
    assert r3['risk_level'] == 'low'

    # 无风险
    r4 = check_message_risk('今天睡得不错')
    print('No risk:', sentinel_summary(r4))
    assert r4['risk_level'] == 'none'

    # profile评分下降检测
    r5 = check_message_risk('最近睡不好', {'history': [{'score': 80}, {'score': 65}, {'score': 50}]})
    print('Score drop:', sentinel_summary(r5), '| reasons:', r5['reasons'])
    assert 'score_drop' in str(r5['reasons'])

    print('\nAll tests passed!')
