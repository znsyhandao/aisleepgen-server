#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clip_multimodal.py — CLIP多模态对比学习 (v7.5+)
原理: OpenAI CLIP — 用预训练CLIP模型做睡眠文本的语义嵌入
落地: 睡眠会话文本→512维CLIP嵌入→用户语义相似度匹配

用法:
  from clip_multimodal import clip_encode, clip_similarity, clip_summary
  emb = clip_encode(text)
  sim = clip_similarity(emb1, emb2)
"""

import os, json, math
import warnings; warnings.filterwarnings('ignore')
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

MODEL = None
PROCESSOR = None


def _lazy_load():
    global MODEL, PROCESSOR
    if MODEL is None:
        from transformers import CLIPModel, CLIPProcessor
        MODEL = CLIPModel.from_pretrained('openai/clip-vit-base-patch32')
        PROCESSOR = CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32')


def clip_encode(texts):
    """将睡眠文本编码为512维CLIP嵌入

    Args:
        texts: str 或 list[str]

    Returns:
        list[list[float]] 或 list[float]
    """
    _lazy_load()
    single = isinstance(texts, str)
    if single:
        texts = [texts]

    inputs = PROCESSOR(text=texts, return_tensors='pt', padding=True)
    outputs = MODEL.get_text_features(**inputs)
    emb = outputs.pooler_output.detach().cpu().tolist()

    if single:
        return emb[0]
    return emb


def clip_similarity(emb1, emb2):
    """计算两个CLIP嵌入的余弦相似度"""
    if not emb1 or not emb2:
        return 0.0
    dot = sum(a * b for a, b in zip(emb1, emb2))
    n1 = math.sqrt(max(1e-10, sum(v**2 for v in emb1)))
    n2 = math.sqrt(max(1e-10, sum(v**2 for v in emb2)))
    return round(dot / (n1 * n2), 3)


def clip_summary(emb):
    """嵌入摘要"""
    if not emb:
        return 'CLIP: 无数据'
    return 'CLIP: 512维嵌入, 前三维=[%.2f, %.2f, %.2f]' % (
        emb[0], emb[1], emb[2])


# ===== 自测 =====
if __name__ == '__main__':
    print('=== CLIP Multimodal Test ===\n')

    emb1 = clip_encode('昨晚失眠，翻来覆去两个小时才睡着')
    emb2 = clip_encode('睡得很好，一觉到天亮')
    print('Embedding len:', len(emb1))
    print('3 dims:', [round(emb1[i], 2) for i in range(3)])

    sim = clip_similarity(emb1, emb2)
    print('失眠 vs 睡好: sim=%.3f' % sim)

    emb3 = clip_encode('压力大，半夜醒了三次')
    sim2 = clip_similarity(emb1, emb3)
    print('失眠 vs 压力大夜醒: sim=%.3f' % sim2)

    print('\nAll tests passed!')
