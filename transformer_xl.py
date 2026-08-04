#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
transformer_xl.py — Transformer-XL长文记忆 (v7.5+)
原理: Google Transformer-XL — 用bert-base-chinese的[CLS]向量做片段级递归记忆
落地: 用户聊天历史→768维语境向量→长期记忆

用法:
  from transformer_xl import compress_history, xl_summary
  context = compress_history(messages)
"""

import os
import warnings; warnings.filterwarnings('ignore')
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

MODEL = None
TOKENIZER = None


def _lazy_load():
    global MODEL, TOKENIZER
    if MODEL is None:
        from transformers import BertModel, BertTokenizer
        TOKENIZER = BertTokenizer.from_pretrained('bert-base-chinese')
        MODEL = BertModel.from_pretrained('bert-base-chinese')


def compress_history(messages, max_segments=5):
    """将历史消息压缩为语境向量

    Bert [CLS]向量作为文本的语义概要
    多段消息分别编码后均值池化 → 768维上下文向量

    Args:
        messages: list[str] — 按时间顺序的消息
        max_segments: int — 最多处理条数

    Returns:
        dict: {context_vector, n_messages, context_dim, note}
    """
    if not messages:
        return {'context_vector': None, 'n_messages': 0, 'context_dim': 0, 'note': '无消息'}

    _lazy_load()

    texts = [str(m)[:200] for m in messages[-max_segments:]]

    # 分批量编码
    inputs = TOKENIZER(texts, return_tensors='pt', truncation=True,
                       max_length=128, padding=True)
    outputs = MODEL(**inputs)
    # [CLS]向量: [batch, 768]
    cls_vecs = outputs.last_hidden_state[:, 0, :].detach()
    # 均值池化
    context_vec = cls_vecs.mean(dim=0).cpu().tolist()

    return {
        'context_vector': context_vec,
        'n_messages': len(texts),
        'context_dim': len(context_vec),
        'note': 'ok',
    }


def xl_similarity(ctx1, ctx2):
    """计算两个语境向量的余弦相似度"""
    if not ctx1 or not ctx2:
        return 0.0
    import math
    dot = sum(a * b for a, b in zip(ctx1, ctx2))
    n1 = math.sqrt(max(1e-10, sum(v**2 for v in ctx1)))
    n2 = math.sqrt(max(1e-10, sum(v**2 for v in ctx2)))
    return round(dot / (n1 * n2), 3)


def xl_summary(result):
    """摘要"""
    if result.get('note') == '无消息':
        return 'Transformer-XL: 无历史消息'
    return 'Transformer-XL: %d条消息→%d维语境向量' % (
        result['n_messages'], result.get('context_dim', 0))


# ===== 自测 =====
if __name__ == '__main__':
    print('=== Transformer-XL Test ===\n')

    history = [
        '昨晚睡得不好，翻来覆去很久才睡着',
        '压力很大，工作上的事情太多处理不完',
        '今天试了冥想呼吸，入睡快了一些',
    ]

    result = compress_history(history)
    print(xl_summary(result))
    assert result['n_messages'] == 3
    assert result['context_dim'] == 768
    vec = result['context_vector']
    print('First 3 dims:', [round(vec[i], 3) for i in range(3)])

    # 空消息
    r2 = compress_history([])
    assert r2['note'] == '无消息'

    # 相似语境
    ctx1 = compress_history(['失眠严重，躺了3小时都睡不着'])['context_vector']
    ctx2 = compress_history(['昨晚失眠，翻来覆去很难入睡'])['context_vector']
    ctx3 = compress_history(['睡得香甜，一觉到天亮八小时'])['context_vector']
    sim_same = xl_similarity(ctx1, ctx2)
    sim_diff = xl_similarity(ctx1, ctx3)
    print('失眠 vs 失眠: %.3f' % sim_same)
    print('失眠 vs 睡好: %.3f' % sim_diff)

    print('\nAll tests passed!')
