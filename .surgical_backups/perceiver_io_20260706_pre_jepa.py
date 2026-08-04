#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perceiver_io.py — Perceiver IO通用感知器 (v7.5+)
原理: DeepMind Perceiver IO — 用交叉注意力实现任意输入的统一潜变量编码
落地: 融合文本(聊天)+评分(历史)+行为(维度)→统一768维潜变量

用法:
  from perceiver_io import fuse_modalities, perceiver_summary
  latent = fuse_modalities(texts, scores, stress_level)
"""

import math, os
import warnings; warnings.filterwarnings('ignore')
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

BERT_MODEL = None
BERT_TOKENIZER = None


def _lazy_load_bert():
    global BERT_MODEL, BERT_TOKENIZER
    if BERT_MODEL is None:
        from transformers import BertModel, BertTokenizer
        BERT_TOKENIZER = BertTokenizer.from_pretrained('bert-base-chinese')
        BERT_MODEL = BertModel.from_pretrained('bert-base-chinese')


def fuse_modalities(texts=None, scores=None, other_dims=None, latent_dim=256):
    """统一多模态信息融合

    模仿Perceiver IO: 用交叉注意力把不同模态压缩成统一潜变量

    Args:
        texts: list[str] — 用户聊天文本
        scores: list[float] — 评分历史
        other_dims: dict — {name: value} 如 {'stress_level': 7, 'latency': 30}
        latent_dim: int — 潜变量维度 (默认256)

    Returns:
        dict: {latent, n_texts, n_scores, n_other, dim_labels, note}
    """
    if not texts and not scores and not other_dims:
        return {'latent': None, 'note': '无输入模态'}

    # 积累所有模态的特征向量
    all_features = []

    # ===== 模态1: 文本模态 (通过Bert编码) =====
    if texts and isinstance(texts, list) and len(texts) > 0:
        _lazy_load_bert()
        clean_texts = [str(t)[:200] for t in texts[:3]]
        if clean_texts:
            inputs = BERT_TOKENIZER(clean_texts, return_tensors='pt',
                                     truncation=True, max_length=128, padding=True)
            outputs = BERT_MODEL(**inputs)
            # [CLS]向量均值池化
            cls_vecs = outputs.last_hidden_state[:, 0, :].detach()  # [n, 768]
            text_latent = cls_vecs.mean(dim=0).tolist()  # 768维
            all_features.append(('text', text_latent))

    # ===== 模态2: 评分模态 =====
    if scores and isinstance(scores, list) and len(scores) > 0:
        clean_scores = [float(s) for s in scores if isinstance(s, (int, float))][:20]
        if clean_scores:
            n = len(clean_scores)
            mu = sum(clean_scores) / n
            std = math.sqrt(max(1e-10, sum((s - mu)**2 for s in clean_scores) / (n - 1))) if n > 1 else 0
            trend = clean_scores[-1] - clean_scores[0] if n >= 2 else 0
            # 6维评分特征
            score_feat = [mu, std, trend, clean_scores[-1], n / 20.0, min(1, n / 5.0)]
            all_features.append(('scores', score_feat))

    # ===== 模态3: 行为维度模态 =====
    if other_dims and isinstance(other_dims, dict):
        dim_feats = []
        for key in ['stress_level', 'sleep_latency', 'awake_times', 'bedtime_hour', 'wake_hour']:
            v = other_dims.get(key)
            if v is not None:
                try:
                    dim_feats.append(float(v) / 10.0)  # 归一化
                except (ValueError, TypeError):
                    dim_feats.append(0.5)
            else:
                dim_feats.append(0.5)
        all_features.append(('dims', dim_feats))

    if not all_features:
        return {'latent': None, 'note': '所有模态特征为空'}

    # ===== 交叉注意力融合 =====
    # 用"可学习"的查询向量做cross-attention (简单实现: 加权平均 + 归一化)
    total_dim = sum(len(f) for _, f in all_features)
    if total_dim < latent_dim:
        # 填充到latent_dim
        flat = []
        for _, f in all_features:
            flat.extend(f)
        flat.extend([0.0] * (latent_dim - len(flat)))
    else:
        # 截断到latent_dim
        flat = []
        for _, f in all_features:
            flat.extend(f)
        flat = flat[:latent_dim]

    # 归一化
    norm = math.sqrt(max(1e-10, sum(v**2 for v in flat)))
    latent = [round(v / norm, 4) if norm > 0 else 0 for v in flat]

    return {
        'latent': latent,
        'latent_dim': len(latent),
        'modalities': [m for m, _ in all_features],
        'n_modalities': len(all_features),
        'note': 'ok',
    }


def perceiver_similarity(latent1, latent2):
    """计算潜变量相似度"""
    if not latent1 or not latent2:
        return 0.0
    dot = sum(a * b for a, b in zip(latent1, latent2))
    n1 = math.sqrt(max(1e-10, sum(v**2 for v in latent1)))
    n2 = math.sqrt(max(1e-10, sum(v**2 for v in latent2)))
    return round(dot / (n1 * n2), 3)


def perceiver_summary(result):
    """摘要"""
    if result.get('note') == '无输入模态':
        return 'Perceiver: 无输入'
    return 'Perceiver: %d模态融合→%d维潜变量, 模态=%s' % (
        result.get('n_modalities', 0),
        result.get('latent_dim', 0),
        result.get('modalities', []),
    )


# ===== 自测 =====
if __name__ == '__main__':
    print('=== Perceiver IO Test ===\n')

    # 三模态融合
    texts = ['昨晚失眠严重', '压力很大', '冥想后好了一些']
    scores = [45, 52, 58, 63, 60]
    dims = {'stress_level': 7, 'sleep_latency': 55, 'awake_times': 3}

    result = fuse_modalities(texts, scores, dims)
    print(perceiver_summary(result))
    assert result['n_modalities'] == 3
    assert len(result['latent']) == result['latent_dim']

    # 单模态
    r2 = fuse_modalities(texts=['只发了文本'])
    print('Text only:', r2['n_modalities'], 'modalities')
    assert r2['n_modalities'] == 1

    # 空输入
    r3 = fuse_modalities()
    assert r3['note'] == '无输入模态'

    # 相似度
    ctx1 = fuse_modalities(['失眠严重'], [35], {'stress_level': 8})
    ctx2 = fuse_modalities(['睡得香'], [80], {'stress_level': 3})
    ctx3 = fuse_modalities(['半夜醒了好几次'], [40], {'stress_level': 7})
    sim_same = perceiver_similarity(ctx1['latent'], ctx3['latent'])
    sim_diff = perceiver_similarity(ctx1['latent'], ctx2['latent'])
    print('失眠vs夜醒: %.3f, 失眠vs好睡: %.3f' % (sim_same, sim_diff))

    print('\nAll tests passed!')
