#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bge_rag.py — BGE RAG检索增强生成 (v7.5+)
原理: RAG — 用BGE中文嵌入从历史记录检索最相关内容，注入推理上下文
落地: 用户聊天时实时检索最相关的过往睡眠记录，作为few-shot注入prompt

用法:
  from bge_rag import retrieve_context, index_history, rag_summary
  chunks = index_history(history)  # 建索引
  context = retrieve_context(chunks, query)  # 检索
"""

import os, math, json
import warnings; warnings.filterwarnings('ignore')
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

MODEL = None
TOKENIZER = None


def _lazy_load():
    global MODEL, TOKENIZER
    if MODEL is None:
        from transformers import AutoModel, AutoTokenizer
        TOKENIZER = AutoTokenizer.from_pretrained('BAAI/bge-small-zh-v1.5')
        MODEL = AutoModel.from_pretrained('BAAI/bge-small-zh-v1.5')


def _mean_pooling(embeddings, attention_mask):
    """BGE: mean pooling + 归一化"""
    mask = attention_mask.unsqueeze(-1).float()
    masked = (embeddings * mask).sum(dim=1)
    count = mask.sum(dim=1).clamp(min=1)
    return masked / count


def _encode(texts):
    """统一编码: 文本→512维归一化向量"""
    _lazy_load()
    inputs = TOKENIZER(texts, return_tensors='pt', truncation=True, max_length=128, padding=True)
    outputs = MODEL(**inputs)
    vecs = _mean_pooling(outputs.last_hidden_state, inputs['attention_mask'])
    # 归一化
    norms = vecs.norm(dim=1, keepdim=True).clamp(min=1e-10)
    vecs = vecs / norms
    return vecs.detach()


def index_history(history, max_chunks=30):
    """建索引: 历史记录→可检索的文本chunk和嵌入

    Args:
        history: list[dict] — 用户的睡眠记录
        max_chunks: int — 最多索引条数

    Returns:
        list[dict] — [{text, embedding, score, timestamp}]
    """
    if not history:
        return []

    # 构建文本chunk
    chunks = []
    for rec in history[-max_chunks:]:
        if not isinstance(rec, dict):
            continue
        score = rec.get('score', '?')
        stress = rec.get('stress_level', '?')
        latency = rec.get('sleep_latency', '?')
        awake = rec.get('awake_times', '?')
        text = '评分=%s,压力=%s,入睡=%s分钟,夜醒=%s次' % (score, stress, latency, awake)

        # 如果有关键词标签或用户描述
        tags = rec.get('tags', rec.get('keywords', ''))
        if tags:
            text += ', 标签=%s' % (tags if isinstance(tags, str) else ','.join(tags))

        chunks.append({
            'text': text,
            'score': score if isinstance(score, (int, float)) else 50,
            'index': len(chunks),
        })

    if not chunks:
        return []

    # 批量编码
    texts = [c['text'] for c in chunks]
    vecs = _encode(texts)

    for i, c in enumerate(chunks):
        c['embedding'] = vecs[i].cpu().tolist()

    return chunks


def retrieve_context(chunks, query, top_k=3, min_similarity=0.3):
    """检索最相关的上下文chunk

    Args:
        chunks: list[dict] — index_history 的输出
        query: str — 用户当前消息
        top_k: int — 返回条数
        min_similarity: float — 最低相似度阈值

    Returns:
        list[dict] — [{text, score, similarity}, ...]
    """
    if not chunks or not query:
        return []

    q_vec = _encode([query])[0]

    scored = []
    for c in chunks:
        if 'embedding' not in c:
            continue
        e_vec = c['embedding']
        dot = sum(a * b for a, b in zip(q_vec.tolist(), e_vec))
        # 向量已归一化，dot就是余弦相似度
        sim = max(-1, min(1, dot))
        if sim >= min_similarity:
            scored.append({
                'text': c['text'],
                'score': c.get('score', 0),
                'similarity': round(float(sim), 3),
                'index': c.get('index', 0),
            })

    scored.sort(key=lambda x: -x['similarity'])
    return scored[:top_k]


def build_rag_context(chunks, query, top_k=3):
    """构建RAG上下文文本，直接可用于prompt注入"""
    results = retrieve_context(chunks, query, top_k)
    if not results:
        return ''
    lines = ['【与当前问题相关的历史睡眠记录】']
    for r in results:
        lines.append('  - [相关度%.2f] %s' % (r['similarity'], r['text']))
    return '\n'.join(lines)


def rag_summary(chunks):
    """摘要"""
    return 'RAG: %d条chunk索引, 512维BGE嵌入' % len(chunks)


# ===== 自测 =====
if __name__ == '__main__':
    print('=== BGE RAG Test ===\n')

    history = [
        {'score': 45, 'stress_level': 8, 'sleep_latency': 60, 'awake_times': 3, 'tags': '失眠,压力大'},
        {'score': 72, 'stress_level': 4, 'sleep_latency': 25, 'awake_times': 1, 'tags': '冥想,改善'},
        {'score': 35, 'stress_level': 9, 'sleep_latency': 75, 'awake_times': 4, 'tags': '焦虑'},
        {'score': 80, 'stress_level': 3, 'sleep_latency': 15, 'awake_times': 0, 'tags': '很好'},
    ]

    chunks = index_history(history)
    print(rag_summary(chunks))
    assert len(chunks) == 4
    assert 'embedding' in chunks[0]
    assert len(chunks[0]['embedding']) == 512

    # 检索: 压力大失眠
    results = retrieve_context(chunks, '我最近压力很大晚上睡不着')
    print('Query: 压力大失眠')
    for r in results:
        print('  %.3f: %s' % (r['similarity'], r['text']))
    assert len(results) >= 1

    # 构建RAG上下文
    ctx = build_rag_context(chunks, '睡得怎么样')
    print('\nRAG context:\n%s' % ctx)
    assert '【与当前问题相关的历史睡眠记录】' in ctx

    print('\nAll tests passed!')
