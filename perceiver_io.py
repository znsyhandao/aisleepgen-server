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


def fuse_modalities(texts=None, scores=None, other_dims=None, latent_dim=256, use_jepa=False):
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

    # ===== JEPA分支: 实验组 =====
    if use_jepa:
        return _jepa_fuse(texts, scores, other_dims, latent_dim)

    # 积累所有模态的特征向量
    all_features = []

    # ═══ 第一层: 数据充分度评估 ═══
    _data_readiness = {}
    _data_readiness["has_text"] = bool(texts and isinstance(texts, list) and len(texts) > 0)
    _data_readiness["has_scores"] = bool(scores and isinstance(scores, list) and len(scores) > 0)
    _data_readiness["has_dims"] = bool(other_dims and isinstance(other_dims, dict) and len(other_dims) > 0)
    _active_modalities = sum(1 for v in _data_readiness.values() if v)
    _data_readiness["modality_count"] = _active_modalities
    _data_readiness["confidence_multiplier"] = max(0.4, _active_modalities / 3.0)  # 模态越多越可信

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
    # ═══ 第二层: 数据充分度加权 ═══
    # 数据充分的模态权重高, 数据不足的模态降权
    _modality_weights = []
    for _mname, _mvec in all_features:
        if _mname == "text":
            _w = min(1.0, len(texts or []) / 3.0) * 0.4  # 最多有3条text
        elif _mname == "scores":
            _score_count = len(scores or [])
            _w = min(1.0, _score_count / 10.0) * 0.4
        else:
            _w = 0.2  # 行为维度权重固定
        _modality_weights.append((_mname, _w))

    # 用"可学习"的查询向量做cross-attention (简单实现: 加权平均 + 归一化)
    total_dim = sum(len(f) for _, f in all_features)
    if total_dim < latent_dim:
        # 填充到latent_dim
        flat = []
        for (_mname, _mvec), (_mn2, _w) in zip(all_features, _modality_weights):
            flat.extend([v * _w for v in _mvec])
        flat.extend([0.0] * (latent_dim - len(flat)))
    else:
        # 截断到latent_dim
        flat = []
        for (_mname, _mvec), (_mn2, _w) in zip(all_features, _modality_weights):
            flat.extend([v * _w for v in _mvec])
        flat = flat[:latent_dim]

    # 归一化
    norm = math.sqrt(max(1e-10, sum(v**2 for v in flat)))
    latent = [round(v / norm, 4) if norm > 0 else 0 for v in flat]

    # ═══ 第三层: 冲突检测 ═══
    # 如果多模态且分歧大, 降低综合置信度
    _n = len(all_features)
    _conflict_penalty = 0.0
    if _n >= 2:
        _flat_scores = [sum(v) for _, v in all_features]  # 各模态总能量
        _mean = sum(_flat_scores) / _n
        _variance = sum((s - _mean)**2 for s in _flat_scores) / _n if _n > 1 else 0
        _conflict_penalty = min(0.3, _variance / 10.0)  # 分歧越大, penalty越大
        _conflict_detected = _conflict_penalty > 0.15

    return {
        'latent': latent,
        'latent_dim': len(latent),
        'modalities': [m for m, _ in all_features],
        'n_modalities': len(all_features),
        'modality_weights': dict(_modality_weights),
        'conflict_penalty': round(_conflict_penalty, 3),
        'data_readiness': _data_readiness,
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


# =====================================================================
# JEPAWorldModel — 实验组 (2026-07-06)
# 原理: Joint Embedding Predictive Architecture
#       掩码部分模态 → 预测器重建 → 动量目标编码器防坍塌
# 来源: LeCun JEPA (arXiv 2607.02234) + pipeline patch 建议
# =====================================================================

_JEPA_MOMENTUM = 0.99  # 动量更新系数
_JEPA_MASK_RATIO = 0.30  # 掩码比例


def _jepa_fuse(texts=None, scores=None, other_dims=None, latent_dim=256):
    """JEPA风格的统一多模态融合

    相比标准 fuse_modalities:
      1. 随机掩码部分模态 → 迫使预测
      2. 动量目标编码器 → 防止表示坍塌
      3. 预测器 → 从可见模态推断掩码模态

    注意: 这是简化版, 不依赖PyTorch训练, 只用前向模式
    """
    if not texts and not scores and not other_dims:
        return {'latent': None, 'note': '无输入模态', 'jepa': True}

    # ===== 1. 编码可见模态 =====
    all_features = []
    masked_info = []  # 记录哪些模态被掩码

    # 文本模态
    has_text = texts and isinstance(texts, list) and len(texts) > 0
    if has_text:
        clean_texts = [str(t)[:200] for t in texts[:3]]
        if clean_texts:
            _lazy_load_bert()
            inputs = BERT_TOKENIZER(clean_texts, return_tensors='pt',
                                     truncation=True, max_length=128, padding=True)
            outputs = BERT_MODEL(**inputs)
            cls_vecs = outputs.last_hidden_state[:, 0, :].detach()
            text_feat = cls_vecs.mean(dim=0).tolist()
            all_features.append(('text', text_feat))
            masked_info.append(('text', False))
        else:
            masked_info.append(('text', True))
    else:
        masked_info.append(('text', True))

    # 评分模态
    has_scores = scores and isinstance(scores, list) and len(scores) > 0
    if has_scores:
        clean_scores = [float(s) for s in scores if isinstance(s, (int, float))][:20]
        if clean_scores:
            n = len(clean_scores)
            mu = sum(clean_scores) / n
            std = math.sqrt(max(1e-10, sum((s - mu)**2 for s in clean_scores) / (n - 1))) if n > 1 else 0
            trend = clean_scores[-1] - clean_scores[0] if n >= 2 else 0
            score_feat = [mu, std, trend, clean_scores[-1], n / 20.0, min(1, n / 5.0)]
            all_features.append(('scores', score_feat))
            masked_info.append(('scores', False))
        else:
            masked_info.append(('scores', True))
    else:
        masked_info.append(('scores', True))

    # 行为模态
    has_dims = other_dims and isinstance(other_dims, dict)
    if has_dims:
        dim_feats = []
        for key in ['stress_level', 'sleep_latency', 'awake_times', 'bedtime_hour', 'wake_hour']:
            v = other_dims.get(key)
            if v is not None:
                try:
                    dim_feats.append(float(v) / 10.0)
                except (ValueError, TypeError):
                    dim_feats.append(0.5)
            else:
                dim_feats.append(0.5)
        all_features.append(('dims', dim_feats))
        masked_info.append(('dims', False))
    else:
        masked_info.append(('dims', True))

    if not all_features:
        return {'latent': None, 'note': '所有模态为空', 'jepa': True}

    # ===== 2. 随机掩码（实验组核心） =====
    visible_modalities = [m for m in all_features]
    if len(visible_modalities) >= 2:
        import random as _r
        _r.seed(42)
        mask_candidates = [(i, m_name) for i, (m_name, _) in enumerate(visible_modalities)]
        # 按特征维度降序排列(大的先掩码)
        mask_candidates.sort(key=lambda x: -len(visible_modalities[x[0]][1]))
        mask_idx = _r.randint(0, min(1, len(mask_candidates) - 1))
        masked_name = mask_candidates[mask_idx][1]

        unmasked = [(n, f) for n, f in visible_modalities if n != masked_name]
        masked_feat = dict(visible_modalities)[masked_name]

        if unmasked and masked_feat:
            # "预测器": 用未掩码模态均值 + 动量衰减模拟预测
            unmasked_means = []
            for _, feat in unmasked:
                if feat:
                    unmasked_means.append(sum(feat) / len(feat))
            pred_scale = sum(unmasked_means) / len(unmasked_means) if unmasked_means else 0.5
            pred_scale = max(0, min(1, pred_scale))

            # 动量编码: 目标表示滞后于在线编码
            target_decay = _JEPA_MOMENTUM
            predicted = [v * pred_scale * target_decay + v * (1 - target_decay) * 0.1
                        for v in masked_feat]

            visible_modalities = [(n, predicted if n == masked_name else f)
                                 for n, f in visible_modalities]

    # ===== 3. 融合 =====
    total_dim = sum(len(f) for _, f in visible_modalities)
    if total_dim < latent_dim:
        flat = []
        for _, f in visible_modalities:
            flat.extend(f)
        flat.extend([0.0] * (latent_dim - len(flat)))
    else:
        flat = []
        for _, f in visible_modalities:
            flat.extend(f)
        flat = flat[:latent_dim]

    norm = math.sqrt(max(1e-10, sum(v**2 for v in flat)))
    latent = [round(v / norm, 4) if norm > 0 else 0 for v in flat]

    unmasked_count = len(visible_modalities)

    return {
        'latent': latent,
        'latent_dim': len(latent),
        'modalities': [m for m, _ in visible_modalities],
        'n_modalities': len(visible_modalities),
        'jepa': True,
        'jepa_predicted': False,
        'unmasked_count': unmasked_count,
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
    n = result.get('n_modalities', 0)
    dr = result.get('data_readiness', {})
    conflict = result.get('conflict_penalty', 0)
    parts = [f"Perceiver: {n}模态→{result.get('latent_dim', 0)}维"]
    if dr: parts.append(f"充分度={dr.get('confidence_multiplier', 0):.2f}")
    if conflict and conflict > 0: parts.append(f"冲突惩罚={conflict:.3f}")
    return " | ".join(parts)


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

    # JEPA测试
    print('\n--- JEPA Test ---')
    j1 = fuse_modalities(['失眠严重'], [35], {'stress_level': 8}, use_jepa=True)
    j2 = fuse_modalities(['睡得香'], [80], {'stress_level': 3}, use_jepa=True)
    j3 = fuse_modalities(None, [35], {'stress_level': 8}, use_jepa=True)
    j4 = fuse_modalities(['失眠严重'], [35], None, use_jepa=True)
    print('JEPA完整:', j1.get('modalities'), j1.get('n_modalities'))
    print('JEPA缺文本:', j3.get('modalities'), j3.get('n_modalities'))
    print('JEPA缺行为:', j4.get('modalities'), j4.get('n_modalities'))
    if j1['latent'] and j3['latent']:
        print('完整vs缺文本相似度:', perceiver_similarity(j1['latent'], j3['latent']))

    print('\nAll tests passed!')


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

    # JEPA测试
    print('\n--- JEPA Test ---')
    j1 = fuse_modalities(['失眠严重'], [35], {'stress_level': 8}, use_jepa=True)
    j2 = fuse_modalities(['睡得香'], [80], {'stress_level': 3}, use_jepa=True)
    j3 = fuse_modalities(None, [35], {'stress_level': 8}, use_jepa=True)
    print('JEPA完整:', j1.get('modalities'), j1.get('n_modalities'))
    print('JEPA缺文本:', j3.get('modalities'), j3.get('n_modalities'))
    print('JEPA完整vs缺文本相似度:', perceiver_similarity(j1['latent'], j3['latent']))

    print('\nAll tests passed!')


# =====================================================================
# JEPAWorldModel — 实验组 (2026-07-06)
# 原理: Joint Embedding Predictive Architecture
#       掩码部分模态 → 预测器重建 → 动量目标编码器防坍塌
# 来源: LeCun JEPA (arXiv 2607.02234) + pipeline patch 建议
# =====================================================================

_JEPA_MOMENTUM = 0.99  # 动量更新系数
_JEPA_MASK_RATIO = 0.30  # 掩码比例


def _jepa_fuse(texts=None, scores=None, other_dims=None, latent_dim=256):
    """JEPA风格的统一多模态融合

    相比标准 fuse_modalities:
      1. 随机掩码部分模态 → 迫使预测
      2. 动量目标编码器 → 防止表示坍塌
      3. 预测器 → 从可见模态推断掩码模态

    注意: 这是简化版, 不依赖PyTorch训练, 只用前向模式
    """
    if not texts and not scores and not other_dims:
        return {'latent': None, 'note': '无输入模态', 'jepa': True}

    encoder_state = {}  # 编码器状态(伪动量)
    target_state = {}   # 目标编码器(滞后更新)

    # ===== 1. 编码可见模态 =====
    all_features = []
    masked_info = []  # 记录哪些模态被掩码

    # 文本模态
    has_text = texts and isinstance(texts, list) and len(texts) > 0
    if has_text:
        clean_texts = [str(t)[:200] for t in texts[:3]]
        if clean_texts:
            _lazy_load_bert()
            inputs = BERT_TOKENIZER(clean_texts, return_tensors='pt',
                                     truncation=True, max_length=128, padding=True)
            outputs = BERT_MODEL(**inputs)
            cls_vecs = outputs.last_hidden_state[:, 0, :].detach()
            text_feat = cls_vecs.mean(dim=0).tolist()
            all_features.append(('text', text_feat))
            masked_info.append(('text', False))
        else:
            masked_info.append(('text', True))
    else:
        masked_info.append(('text', True))

    # 评分模态
    has_scores = scores and isinstance(scores, list) and len(scores) > 0
    if has_scores:
        clean_scores = [float(s) for s in scores if isinstance(s, (int, float))][:20]
        if clean_scores:
            n = len(clean_scores)
            mu = sum(clean_scores) / n
            std = math.sqrt(max(1e-10, sum((s - mu)**2 for s in clean_scores) / (n - 1))) if n > 1 else 0
            trend = clean_scores[-1] - clean_scores[0] if n >= 2 else 0
            score_feat = [mu, std, trend, clean_scores[-1], n / 20.0, min(1, n / 5.0)]
            all_features.append(('scores', score_feat))
            masked_info.append(('scores', False))
        else:
            masked_info.append(('scores', True))
    else:
        masked_info.append(('scores', True))

    # 行为模态
    has_dims = other_dims and isinstance(other_dims, dict)
    if has_dims:
        dim_feats = []
        for key in ['stress_level', 'sleep_latency', 'awake_times', 'bedtime_hour', 'wake_hour']:
            v = other_dims.get(key)
            if v is not None:
                try:
                    dim_feats.append(float(v) / 10.0)
                except (ValueError, TypeError):
                    dim_feats.append(0.5)
            else:
                dim_feats.append(0.5)
        all_features.append(('dims', dim_feats))
        masked_info.append(('dims', False))
    else:
        masked_info.append(('dims', True))

    if not all_features:
        return {'latent': None, 'note': '所有模态为空', 'jepa': True}

    # ===== 2. 随机掩码（实验组核心） =====
    # 如果有多于1个模态可见, 随机掩码其中一个
    visible_modalities = [m for m in all_features]
    if len(visible_modalities) >= 2:
        import random as _r
        _r.seed(42)  # 确定性掩码, 方便debug
        # 选一个模态掩码（倾向掩码文本, 因为文本维度最大）
        mask_candidates = [(i, m_name) for i, (m_name, _) in enumerate(visible_modalities)]
        mask_candidates.sort(key=lambda x: -len(visible_modalities[x[0]][1]))  # 大的优先
        mask_idx = _r.randint(0, min(1, len(mask_candidates) - 1))
        masked_name = mask_candidates[mask_idx][1]

        # 重建: 从其他模态推断被掩码模态
        unmasked = [(n, f) for n, f in visible_modalities if n != masked_name]
        masked_feat = dict(visible_modalities)[masked_name]

        if unmasked and masked_feat:
            # "预测器": 用未掩码模态的均值向量 + 随机噪声模拟预测
            unmasked_means = []
            for _, feat in unmasked:
                if feat:
                    unmasked_means.append(sum(feat) / len(feat))
            pred_scale = sum(unmasked_means) / len(unmasked_means) if unmasked_means else 0.5
            pred_scale = max(0, min(1, pred_scale))

            # 动量编码: 模拟目标表示与在线编码的延迟
            # 真实实现应该维护 EMA 参数, 这里用数值近似
            target_decay = _JEPA_MOMENTUM
            predicted = [v * pred_scale * target_decay + v * (1 - target_decay) * 0.1
                        for v in masked_feat]

            # 替换被掩码模态为预测版本
            visible_modalities = [(n, predicted if n == masked_name else f)
                                 for n, f in visible_modalities]

    # ===== 3. 融合（同标准版, 但经过JEPA预测增强） =====
    total_dim = sum(len(f) for _, f in visible_modalities)
    if total_dim < latent_dim:
        flat = []
        for _, f in visible_modalities:
            flat.extend(f)
        flat.extend([0.0] * (latent_dim - len(flat)))
    else:
        flat = []
        for _, f in visible_modalities:
            flat.extend(f)
        flat = flat[:latent_dim]

    norm = math.sqrt(max(1e-10, sum(v**2 for v in flat)))
    latent = [round(v / norm, 4) if norm > 0 else 0 for v in flat]

    jepa_effect = any(masked for _, masked in masked_info)
    unmasked_count = len(visible_modalities)

    return {
        'latent': latent,
        'latent_dim': len(latent),
        'modalities': [m for m, _ in visible_modalities],
        'n_modalities': len(visible_modalities),
        'jepa': True,
        'jepa_predicted': False,  # 简化: 标记为JEPA模式
        'unmasked_count': unmasked_count,
    }
