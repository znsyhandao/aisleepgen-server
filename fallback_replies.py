#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fallback_replies.py — AISleepGen 本地降级回复引擎

当 DeepSeek API 不可用时，基于世界模型评分 + NLP 字段 + 情感分析
生成自然语言回复，用户完全无感知降级。

设计原则：
- 零外部依赖（只用标准库）
- 所有回复像真人写的，不暴露"我是机器人"
- 评分高/低/中有不同的情感和措辞
- 支持 4 种人设（restorative/coach/analyst/mentor）
"""

import random
import re
from datetime import datetime
from persona_profiles import PERSONAS, DEFAULT_PERSONA, detect_emotion_vector, get_dominant_emotion

# ===== 情感检测（简单关键词） =====
_POSITIVE_WORDS = {
    '很好', '不错', '还行', '好多了', '睡得香', '舒服', '安稳', 
    '没醒', '一觉', '天亮', '舒服多了', '有改善',
}
_NEGATIVE_WORDS = {
    '睡不着', '失眠', '难受', '焦虑', '压力大', '烦躁', '头疼',
    '噩梦', '惊醒', '心慌', '胸闷', '担心', '恐惧', '抑郁',
    '难受', '痛苦', '累', '困', '没精神', '不舒服',
}
_NEUTRAL_WORDS = {
    '一般', '差不多', '老样子', '还行吧', '凑合',
}

_WAKE_WORDS = {'醒', '夜醒', '醒了', '醒来', '睡不着', '起夜', '起来'}
_PAIN_WORDS = {'疼', '痛', '不舒服'}
_SNORING_WORDS = {'打鼾', '鼾声', '呼吸暂停', '憋气'}


def _detect_sentiment(text):
    """返回 'positive', 'negative', 'neutral'"""
    if not text:
        return 'neutral'
    t = text.lower()
    pos = sum(1 for w in _POSITIVE_WORDS if w in t)
    neg = sum(1 for w in _NEGATIVE_WORDS if w in t)
    if neg > pos:
        return 'negative'
    if pos > neg:
        return 'positive'
    return 'neutral'


# ===== 回复模板 =====

_TEMPLATES = {
    # ----- 低分 + 负面情绪 -----
    ('low', 'negative'): [
        "我理解您睡不好的困扰。从数据分析看，当前睡眠质量偏低，建议今晚尝试：1) 睡前1小时放下手机 2) 固定入睡时间。明早可以和我反馈效果。",
        "您的睡眠确实需要关注。我会建议先从作息规律入手——试着固定起床时间，即使周末也保持不变。这是调整生物钟最有效的方法。",
        "睡眠不好确实影响白天的状态。从数据看您的作息有一定波动，建议今晚固定23:00前上床，我会帮您跟踪效果。",
    ],
    # ----- 低分 + 中性 -----
    ('low', 'neutral'): [
        "从您的描述来看，睡眠质量有提升空间。我建议关注两点：睡前放松和作息规律。要不要试试今晚提前半小时放下手机？",
        "当前睡眠评分偏低。建议从最简单的做起：每天固定起床时间，不赖床。坚持3天应该能看到改善。",
        "看起来您最近睡眠不太稳定。建议先保持记录，连续3天后我就能给出更有针对性的建议了。",
    ],
    # ----- 中分 -----
    ('mid', 'negative'): [
        "您的情况不算差，但还有提升空间。夜醒问题可以通过睡前放松改善，建议试试腹式呼吸5分钟再入睡。",
        "睡眠质量一般般，但问题不大。从数据看您的入睡速度还可以，主要是睡眠连续性需要优化。",
        "能看到您正在努力改善睡眠，这是好事！当前评分处于中游，关键在于减少夜间觉醒。我有个小技巧要试试吗？",
    ],
    ('mid', 'neutral'): [
        "您的睡眠大致正常，有一些小波动。继续保持目前的作息规律，我建议适当增加白天的活动量来加深夜间睡眠。",
        "整体来看您的睡眠结构还算合理。如果想更进一步，可以试试睡前1小时做10分钟的轻度拉伸。",
        "当前状态平稳，有改善空间但不严重。注意避免晚间咖啡和酒精，它们会干扰深睡眠。",
    ],
    # ----- 高分 -----
    ('high', 'positive'): [
        "太好了，您的睡眠质量不错！继续保持目前的作息节奏，规律就是最好的睡眠药。",
        "今天的数据很好看！说明您最近的调整见效了。继续保持，规律作息比任何补品都有效。",
        "状态很棒！看得出您很重视睡眠质量且已取得成效。记住这种好的感受，它在提醒您规律作息的价值。",
    ],
    ('high', 'neutral'): [
        "睡眠质量良好，各项指标都在正常范围。继续保持即可，不需要额外干预。",
        "目前您的睡眠状态稳定且健康。建议每周保持同样节奏，身体会越来越适应。",
        "不错，您的睡眠评分处于健康水平。轻微波动是正常的，不用太在意单日数据。",
    ],
    # ----- 数据不足 -----
    'insufficient': [
        "您提供的信息还不够我做出完整分析。可以告诉我更多吗？比如昨晚几点睡、几点起、夜里醒了几次？",
        "要更准确地评估您的睡眠，我需要多一些信息。您方便告诉我入睡和起床时间吗？",
        "目前的记录还不足以给出分析。要不您先说说昨晚大概几点睡几点起？连续记录几天效果更好。",
    ],
    # ----- 异常字段（打鼾/疼痛/恶性情绪） -----
    'snoring': [
        "您提到有打鼾情况，这需要留意。如果鼾声很大且伴有呼吸中断，建议去呼吸科做一次睡眠监测。",
        "打鼾可能是睡眠呼吸暂停的征兆之一，如果白天经常犯困、睡醒后口干头痛，建议做专业的睡眠检查。",
    ],
    'pain': [
        "身体不舒服确实会打断睡眠。您提到肚子不舒服，消化问题在夜间容易加重，引起反复醒来。今晚可以试试喝杯温蜂蜜水暖胃，晚餐避免油腻和生冷。",
        "听到您身体不太舒服。消化不适会影响睡眠的连续性，一晚上醒好几次很正常。建议明晚吃清淡点，睡前两小时别吃东西，看看会不会好一些。",
    ],
    'anxiety': [
        "听起来您最近压力不小。焦虑情绪是失眠的常见诱因，我建议在睡前做5分钟深呼吸放松。",
        "压力大确实让人睡不好。记得不要在床上想烦心事——如果躺下20分钟睡不着，不如起来看看书，等有困意再躺下。",
    ],
}

_GREETING_TEMPLATES = {
    'morning': [
        "早上好！昨晚睡得怎么样？",
        "早安！来告诉我昨晚的睡眠情况吧。",
        "早晨好，昨晚休息得如何？",
    ],
    'evening': [
        "晚上好！今天想和我聊聊睡眠吗？",
        "晚安时间到，有什么想和我说的吗？",
        "夜幕降临，来聊聊今晚的睡眠准备吧？",
    ],
    'default': [
        "您好！想聊聊您的睡眠情况吗？",
        "欢迎回来！今天睡眠感觉怎么样？",
        "有什么想跟我聊的？关于睡眠的任何问题都可以问我。",
    ],
}


def _score_to_level(score):
    """0-100 分数映射到 low/mid/high"""
    if score is None or score == 0:
        return None  # 数据不足
    if score < 60:
        return 'low'
    if score < 80:
        return 'mid'
    return 'high'


def _get_time_greeting():
    h = datetime.now().hour
    if 5 <= h < 12:
        return 'morning'
    if 18 <= h < 23:
        return 'evening'
    return 'default'


def _pick(templates):
    """从模板列表中随机选一条"""
    if isinstance(templates, str):
        return templates
    if isinstance(templates, list) and templates:
        return random.choice(templates)
    return '感谢您的分享，多记录几天数据我就能给出更精准的建议了。'


def generate_fallback_reply(message, wm_result=None, fields=None, persona=DEFAULT_PERSONA):
    """
    主入口：生成降级回复

    参数:
        message: 用户消息
        wm_result: 世界模型结果 dict (含 total_score, quality, expert_debate 等)
        fields: NLP 提取的结构化字段
        persona: 人设类型 (restorative/coach/analyst/mentor)
    
    返回: 回复字符串
    """
    if not message:
        return _pick(_GREETING_TEMPLATES[_get_time_greeting()])

    # 用 5 维情绪向量增强检测
    emotion_vector = detect_emotion_vector(message)
    dominant_emo, intensity = get_dominant_emotion(emotion_vector)
    # 后向兼容：映射到 3 bucket
    if dominant_emo in ('angry', 'sad', 'anxious'):
        sentiment = 'negative'
    elif dominant_emo == 'positive':
        sentiment = 'positive'
    else:
        sentiment = _detect_sentiment(message)  # fallback to keyword

    score = None
    if wm_result:
        score = wm_result.get('total_score')
    level = _score_to_level(score)

    # 获取人设的回复前缀
    persona_config = PERSONAS.get(persona, PERSONAS[DEFAULT_PERSONA])
    persona_prefix = persona_config.get('fallback_prefix', '')

    # 1. 检查异常字段
    if fields:
        # ===== v7.3: 因果分析优先 =====
        # 当有 awake_cause/drink 提取字段时，直接生成因果回复
        causal_parts = []
        if fields.get('drink') == 'alcohol':
            causal_parts.append('酒精会刺激肠胃，影响深度睡眠')
        if fields.get('awake_cause'):
            cause = fields['awake_cause']
            if '消化' in cause or '胃' in cause or '肚' in cause:
                causal_parts.append('消化系统在夜间工作效率降低，肚子不舒服会导致反复醒来')
            elif '焦虑' in cause or '压力' in cause:
                causal_parts.append('焦虑情绪会提高大脑警觉度，浅睡增多深睡减少')
            else:
                causal_parts.append(f'{cause}会影响睡眠连续性')
        if fields.get('awake_times') and fields['awake_times'] > 1:
            causal_parts.append(f'昨晚醒了{fields["awake_times"]}次，睡眠碎片化比较严重')

        if len(causal_parts) >= 2:
            causal = '；'.join(causal_parts) + '。'
            advice_parts = []
            if fields.get('drink') == 'alcohol':
                advice_parts.append('睡前避免喝酒，温水代替')
            if fields.get('awake_cause') and ('消化' in fields.get('awake_cause', '') or '肚' in fields.get('awake_cause', '')):
                advice_parts.append('晚餐早点吃、清淡点')
            if fields.get('awake_times') and fields['awake_times'] > 2:
                advice_parts.append('睡前做5分钟腹式呼吸放松')
            advice = '；'.join(advice_parts) if advice_parts else ''
            causal_reply = persona_prefix + causal
            if advice:
                causal_reply += '\n\n可以试试：' + advice + '。'
            return causal_reply

        if fields.get('snore_related'):
            return persona_prefix + _pick(_TEMPLATES['snoring'])
        if fields.get('has_pain'):
            return persona_prefix + _pick(_TEMPLATES['pain'])
        if sentiment == 'negative' and score is None:
            return persona_prefix + _pick(_TEMPLATES['anxiety'])

    # 2. 数据不足
    if level is None:
        return persona_prefix + _pick(_TEMPLATES['insufficient'])

    # 3. 按分数+情绪选模板
    key = (level, sentiment)
    templates = _TEMPLATES.get(key)
    if templates is None:
        for k in _TEMPLATES:
            if isinstance(k, tuple) and k[0] == level:
                templates = _TEMPLATES[k]
                break
    if templates is None:
        templates = _TEMPLATES['insufficient']

    return persona_prefix + _pick(templates)


# ===== 人设回复前缀 =====
# 设置各人设的 fallback 前缀（简短一句话体现人设风格）
PERSONAS[DEFAULT_PERSONA]['fallback_prefix'] = ''
PERSONAS.get('coach')['fallback_prefix'] = '💪 '
PERSONAS.get('analyst')['fallback_prefix'] = '📊 '
PERSONAS.get('mentor')['fallback_prefix'] = '🎓 '


# ===== 快速测试 =====
if __name__ == '__main__':
    # 模拟各场景
    test_cases = [
        ("昨晚睡得很好，一觉到天亮", {'total_score': 85, 'quality': '优秀'}, {'total_duration': 480}),
        ("半夜醒了睡不着，压力很大", {'total_score': 45, 'quality': '较差'}, {'awake_times': 2}),
        ("一般般吧", {'total_score': 68, 'quality': '一般'}, {}),
        ("打鼾很严重", {'total_score': 70, 'quality': '一般'}, {'snore_related': True}),
        ("", None, None),  # 问候
        ("身体不舒服", None, {'has_pain': True}),  # 疼痛
        ("最近很焦虑", None, {}),  # 焦虑
    ]
    for msg, wm, fields in test_cases[:3]:
        print(f'msg={msg[:20]:>20} score={wm["total_score"] if wm else "N/A":>5} -> {generate_fallback_reply(msg, wm, fields)[:60]}')
        print()
