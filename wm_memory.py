#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wm_memory.py — 世界模型经验记忆层 v2.0

核心升级 v2.0:
  不再依赖余弦相似度做语义匹配，改用 DeepSeek 判断案例相关性。
  
  流程:
    1. 余弦初筛（低阈值0.2，召回尽可能多的候选）
    2. DeepSeek 精判（发一条"请判断以下案例是否和当前用户问题同类"的请求）
    3. 只注入 DeepSeek 判定为"同类"的案例

  前沿依据: In-Context Meta-Learning（上下文内学习），
  让 LLM 在推理时自己做"这些历史经验是否适用"的判断，
  远优于固定阈值的向量相似度。

依赖: ai_client (DeepSeek API带缓存)
"""

import json
import os
import time
import math
from datetime import datetime
import logging

_ai_log = logging.getLogger('aisleepgen.wm_memory')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MEMORY_PATH = os.path.join(PROJECT_ROOT, 'data', 'wm_memory.jsonl')


def save_experience(openid, message, fields, wm_result, ds_result=None, reply=''):
    """保存一次推理经验到记忆库"""
    entry = {
        'ts': time.time(),
        'date': datetime.now().strftime('%Y-%m-%d'),
        'openid': openid[:8],
        'message': (message or '')[:500],
        'fields': {k: str(v) for k, v in (fields or {}).items() if v},
        'wm_score': wm_result.get('total_score', 0) if wm_result else 0,
        'quality': wm_result.get('quality', '') if wm_result else '',
        'ds_findings': (ds_result or {}).get('findings', [])[:5],
        'ds_score': (ds_result or {}).get('score', 0),
        'reply': (reply or '')[:300],
    }
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def _keyword_recall(fields, raw_text, entries, top_k=8):
    """关键词初筛：用共同关键词召回候选案例

    只做关键词交集，不做向量相似度。
    要求：候选案例的核心关键词与当前输入有至少1个交集。
    """
    text = (raw_text or '').lower()
    query_keywords = set()
    
    # 从字段提取关键词
    if fields:
        if fields.get('drink') == 'alcohol':
            query_keywords.update(['酒', '酒精', 'drink'])
        if fields.get('has_pain'):
            query_keywords.update(['痛', '不舒服', '疼', 'pain'])
        if fields.get('awake_cause'):
            cause = str(fields['awake_cause']).lower()
            if '消化' in cause or '肚' in cause or '胃' in cause or 'stomach' in cause:
                query_keywords.update(['肚子', '胃', '消化', '肠胃'])
            if '焦虑' in cause or '压力' in cause or 'anxiety' in cause or 'stress' in cause:
                query_keywords.update(['焦虑', '压力', '紧张'])
            if '痛' in cause or '疼痛' in cause or 'pain' in cause:
                query_keywords.update(['痛', '疼'])
        if fields.get('snore_related'):
            query_keywords.update(['打鼾', '打呼', 'snore'])
        if fields.get('mood'):
            query_keywords.update([str(fields['mood'])])
    
    # 从原始文本补充
    if '酒' in text or '红酒' in text:
        query_keywords.add('酒')
    if '肚子' in text or '胃' in text:
        query_keywords.update(['肚子', '胃'])
    if '焦虑' in text or '压力' in text:
        query_keywords.update(['焦虑', '压力'])
    if '打鼾' in text or '打呼' in text:
        query_keywords.add('打鼾')
    if '噩梦' in text or '梦' in text:
        query_keywords.add('梦')
    if '醒' in text:
        query_keywords.add('醒')
    if '睡不' in text:
        query_keywords.add('失眠')

    if not query_keywords:
        return entries[:top_k]  # 没关键词就返回最近的

    # 评分候选：计算每个条目的匹配关键词数
    scored = []
    for entry in entries:
        entry_msg = (entry.get('message', '') or '').lower()
        entry_fields = entry.get('fields', {})
        
        matches = 0
        for kw in query_keywords:
            if kw in entry_msg:
                matches += 1
            else:
                # 也查fields
                for fv in entry_fields.values():
                    if kw in str(fv).lower():
                        matches += 1
                        break
        if matches >= 1:  # 至少1个关键词匹配
            scored.append((matches, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_k]]


def _deepseek_rank(query_fields, query_text, candidates):
    """用 DeepSeek 精判：哪些候选案例与当前问题同类

    发送一条请求让 DeepSeek 判断：
    - 当前用户问题类型
    - 每个候选案例是否属于同一类型
    - 只返回"是"的案例

    Returns:
        list[dict]: DeepSeek 判定为相关的案例
    """
    if not candidates:
        return []

    try:
        from ai_client import call_deepseek_api as _call_ds
    except Exception:
        return candidates  # 降级：全返回

    # 构造判断 prompt
    case_lines = []
    for i, c in enumerate(candidates):
        msg = c.get('message', '')[:100]
        flds = c.get('fields', {})
        fld_str = ', '.join(f'{k}={v}' for k, v in list(flds.items())[:5])
        case_lines.append(f'[{i}] 用户说: "{msg}" | 数据: {fld_str}')

    query_text_clean = (query_text or '')[:200]
    query_fields_str = ', '.join(f'{k}={v}' for k, v in (query_fields or {}).items() if v)
    
    system_prompt = (
        '你是一个睡眠分析系统的案例匹配判断器。'
        '你的任务：判断用户当前的问题，与历史案例是否属于同一类型。'
        '输出格式：仅输出一个JSON数组，包含被判定为同类的案例编号。'
        '例如：[0, 2]表示案例0和案例2与当前问题同类，案例1不同类。'
        '判定标准：睡眠分析中，"同类"指症状类型相同（如都是"酒精+消化不适"、"焦虑性失眠"、"疼痛性睡眠障碍"等），'
        '不要求完全相同的描述。'
    )
    user_prompt = (
        f"当前用户问题：{query_text_clean}\n"
        f"当前系统识别数据：{query_fields_str}\n\n"
        f"历史案例列表：\n" + '\n'.join(case_lines) + "\n\n"
        f"请判断哪些案例与当前问题属于同一类型？只输出JSON数组。"
    )

    try:
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        reply = _call_ds(messages, use_async=False)
        if not reply or len(reply) < 3:
            return candidates

        # 解析JSON数组回复
        reply_clean = reply.strip()
        # 找 [...]
        import re as _re
        m = _re.search(r'\[[\d,\s]+\]', reply_clean)
        if m:
            indices = json.loads(m.group(0))
            if isinstance(indices, list) and len(indices) > 0:
                selected = [candidates[i] for i in indices if 0 <= i < len(candidates)]
                if selected:
                    _ai_log.info('[Memory] DeepSeek selected %d/%d relevant cases', len(selected), len(candidates))
                    return selected
    except Exception as e:
        _ai_log.debug('[Memory] DeepSeek ranking failed: %s', e)

    return candidates  # 降级：全返回


def retrieve_similar(fields, raw_text='', top_k=3, max_age_days=30):
    """检索相似历史案例 v2.0

    流程: 关键词初筛 → DeepSeek精判 → 排序输出

    Args:
        fields: neural_extractor提取的字段
        raw_text: 用户原始输入
        top_k: 返回最多多少个案例
        max_age_days: 只看最近多少天的数据
    """
    if not os.path.exists(MEMORY_PATH):
        return []

    cutoff = time.time() - max_age_days * 86400

    # 读所有有效条目
    all_entries = []
    with open(MEMORY_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get('ts', 0) >= cutoff:
                    all_entries.append(entry)
            except Exception:
                continue

    if not all_entries:
        return []

    # 1. 关键词初筛（召回候选）
    candidates = _keyword_recall(fields, raw_text, all_entries, top_k=8)
    if not candidates:
        return []

    # 2. DeepSeek 精判（过滤不相关）
    relevant = _deepseek_rank(fields, raw_text, candidates)
    if not relevant:
        return []

    # 3. 按时间排序（最新的优先）
    relevant.sort(key=lambda x: x.get('ts', 0), reverse=True)
    return relevant[:top_k]


def format_memory_context(similar_cases):
    """将相似案例格式化为世界模型可读的上下文"""
    if not similar_cases:
        return ''

    parts = []
    for i, case in enumerate(similar_cases):
        msg = case.get('message', '')[:80]
        score = case.get('wm_score', '?')
        quality = case.get('quality', '?')
        findings = case.get('ds_findings', [])
        findings_text = '；'.join(
            [f.get('finding', '')[:60] if isinstance(f, dict) else str(f)[:60]
             for f in findings[:3]]
        )
        parts.append(
            f'[案例{i+1}] 用户说"{msg}" → '
            f'评分{score}({quality})'
            + (f' | 分析: {findings_text}' if findings_text else '')
        )

    return '\n'.join(parts)


def optimize_memory(days=1):
    """每日优化：合并相似条目，去重，压缩"""
    if not os.path.exists(MEMORY_PATH):
        return 0

    cutoff = time.time() - days * 86400
    entries = []
    with open(MEMORY_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get('ts', 0) >= cutoff:
                    entries.append(entry)
            except json.JSONDecodeError:
                continue

    if len(entries) <= 1:
        return 0

    seen = set()
    unique = []
    removed = 0
    for entry in entries:
        key = entry.get('message', '')[:100] + str(entry.get('fields', {}))
        if key not in seen:
            seen.add(key)
            unique.append(entry)
        else:
            removed += 1

    if removed > 0:
        remaining = []
        with open(MEMORY_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get('ts', 0) >= cutoff:
                        key = entry.get('message', '')[:100] + str(entry.get('fields', {}))
                        if key not in seen:
                            remaining.append(line)
                        else:
                            seen.discard(key)
                            remaining.append(line)
                    else:
                        remaining.append(line)
                except Exception:
                    remaining.append(line)

        with open(MEMORY_PATH, 'w', encoding='utf-8') as f:
            for line in remaining:
                f.write(line + '\n')

    return removed


if __name__ == '__main__':
    print('wm_memory v2.0 loaded')
    print(f'Memory file: {MEMORY_PATH}')
