#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
self_eval.py — 回复质量自评估 (v7.5+)
原理: Anthropic监督评估 — 用多语言嵌入评估回复的语义对齐与一致性
落地: chat回复后自动评分(0~1), 跟踪质量趋势

用法:
  from self_eval import evaluate_reply, eval_summary
  result = evaluate_reply(question, reply)
"""

import math, os, json
import warnings; warnings.filterwarnings('ignore')
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

MODEL = None
TOKENIZER = None


def _lazy_load():
    global MODEL, TOKENIZER
    if MODEL is None:
        from transformers import AutoModel, AutoTokenizer
        TOKENIZER = AutoTokenizer.from_pretrained(
            'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        MODEL = AutoModel.from_pretrained(
            'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')


def _mean_pool(emb, mask):
    mask = mask.unsqueeze(-1).float()
    return (emb * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)


def _encode(text):
    _lazy_load()
    max_len = 128
    inputs = TOKENIZER(text, return_tensors='pt', truncation=True,
                       max_length=max_len, padding=True)
    outputs = MODEL(**inputs)
    vec = _mean_pool(outputs.last_hidden_state, inputs['attention_mask'])
    norm = vec.norm(dim=1, keepdim=True).clamp(min=1e-10)
    return (vec / norm).detach().squeeze(0).tolist()


def _cosine(v1, v2):
    if not v1 or not v2:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(max(1e-10, sum(a**2 for a in v1)))
    n2 = math.sqrt(max(1e-10, sum(b**2 for b in v2)))
    return dot / (n1 * n2)


def evaluate_reply(question, reply):
    """评估回复质量：三重检查

    1. 语义对齐 (0~0.4): 回复与问题的余弦相似度
    2. 长度充足 (0~0.2): 回复包含足够信息
    3. 冗余检测 (0~0.4): 回复内句间多样性

    Args:
        question: str — 用户问题
        reply: str — AI回复

    Returns:
        dict: {score, components, breakdown, note}
    """
    if not question or not reply:
        return {'score': 0, 'components': {}, 'note': '输入为空'}

    score = 0.0
    q = str(question)[:500]
    r = str(reply)[:2000]

    components = {}

    # ===== 1. 语义对齐 (0~0.4) =====
    try:
        q_vec = _encode(q)
        r_vec = _encode(r)
        alignment = max(0, min(1, _cosine(q_vec, r_vec)))
        # 对齐度越高越好
        alignment_score = alignment * 0.4
        score += alignment_score
        components['alignment'] = round(alignment_score, 3)
        components['alignment_raw'] = round(alignment, 3)
    except Exception:
        components['alignment'] = 0.2  # 默认
        score += 0.2

    # ===== 2. 长度充足 (0~0.2) =====
    r_len = len(r)
    if r_len < 20:
        len_score = 0.0
    elif r_len < 80:
        len_score = 0.05
    elif r_len < 150:
        len_score = 0.12
    elif r_len < 300:
        len_score = 0.17
    else:
        len_score = 0.2
    score += len_score
    components['length'] = round(len_score, 3)
    components['reply_len'] = r_len

    # ===== 3. 冗余检测 (0~0.4) =====
    # 用句子间多样性评估: 分句编码看差异
    try:
        import re as _re
        sentences = _re.split(r'[。！？.!?\n]', r)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
        if len(sentences) >= 2:
            sent_vecs = [_encode(s) for s in sentences[:5]]
            similarities = []
            for i in range(len(sent_vecs)):
                for j in range(i + 1, len(sent_vecs)):
                    similarities.append(_cosine(sent_vecs[i], sent_vecs[j]))
            if similarities:
                avg_sim = sum(similarities) / len(similarities)
                # 相似度越低→多样性越高→分数越高
                diversity = max(0, min(1, 1 - avg_sim))
                diversity_score = diversity * 0.4
                score += diversity_score
                components['diversity'] = round(diversity_score, 3)
                components['diversity_raw'] = round(1 - diversity, 3)
            else:
                score += 0.2
                components['diversity'] = 0.2
        else:
            score += 0.2
            components['diversity'] = 0.2
    except Exception:
        score += 0.2
        components['diversity'] = 0.2

    return {
        'score': round(min(1.0, score), 3),
        'components': components,
        'breakdown': '语义对齐=%.1f%% + 长度=%.1f%% + 多样性=%.1f%%' % (
            components.get('alignment', 0) * 100,
            components.get('length', 0) * 100,
            components.get('diversity', 0) * 100,
        ),
        'note': 'ok' if score >= 0.5 else 'low_quality',
    }


def eval_summary(result):
    """摘要"""
    if result.get('note') == '输入为空':
        return '自评估: 无输入'
    return '自评估: %.2f, %s' % (result['score'], result.get('breakdown', ''))


# ===== 自测 =====
if __name__ == '__main__':
    print('=== Self-Eval Test ===\n')

    q1 = '我最近失眠很严重，怎么办？'
    r1 = '建议您尝试以下方法改善睡眠：1) 保持规律作息，每天固定时间上床和起床；2) 睡前1小时避免使用电子设备；3) 可以尝试渐进式肌肉放松或4-7-8呼吸法；4) 如果连续失眠超过两周，建议咨询专业医生。'

    result1 = evaluate_reply(q1, r1)
    print('Q1:', eval_summary(result1))
    assert result1['score'] >= 0.5

    # 低质量回复
    q2 = '我压力很大睡不着'
    r2 = '好的加油'  # 太短
    result2 = evaluate_reply(q2, r2)
    print('Q2:', eval_summary(result2))
    assert result2['score'] < 0.5

    # 空输入
    result3 = evaluate_reply('', '')
    assert result3['note'] == '输入为空'

    print('\nAll tests passed!')
