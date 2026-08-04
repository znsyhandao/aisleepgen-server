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

    # PerceptionGraph: 自动存入感知图
    try:
        pg = get_perception_graph()
        pg.add_experience(openid, message, fields, wm_result)
    except Exception:
        pass


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




# ===== PerceptionGraph — 分层感知记忆图 v1 (2026-06-09) =====
# CONCEPT_PROOF: MemDreamer 论文的分层记忆方法
# 感知层：每次经验自动提取感知特征，构建图节点
# 推理层：按需 BFS 查找相关记忆，而非全文搜索
# 老化层：超过 7 天的节点自动聚合为摘要节点

class PerceptionGraph:
    """感知记忆图 — 自动提取+关联+老化

    

    节点类型:

      - 'user_vector': 用户描述/问题的感知特征嵌入

      - 'session_summary': 一次 session 的压缩摘要

      - 'aggregated': 超过 7 天的旧节点聚合

    

    边类型:

      - 'same_user': 同一用户的不同经验

      - 'similar': 关键词相似的跨用户经验

      - 'temporal': 时间相邻的 session

    """

    

    def __init__(self, storage_path=None):

        self.graph = {'nodes': {}, 'edges': []}  # node_id -> attrs

        self._dirty = False

        if storage_path:

            self._load(storage_path)

    

    _KEYWORDS = [
        'alcohol','drink','digest','stomach','anxiety','stress',
        'pain','discomfort','env','habit','circadian','rhythm',
        'insomnia','wake','sleep','snore','breath','nightmare',
        'tired','fatigue','dream','melatonin','caffeine','exercise',
        'meditation','breathing','relax','calm','noise','light',
    ]

    def add_experience(self, openid, message, fields, wm_result):

        """从一次经验自动构建感知节点"""

        import hashlib

        node_id = hashlib.md5((openid[:8] + str(time.time())).encode()).hexdigest()[:12]

        

        # 感知特征提取

        keywords = set()

        text = (message or '').lower()

        for kw in self._KEYWORDS:

            if kw in text:

                keywords.add(kw)

        for k, v in (fields or {}).items():

            if isinstance(v, str):

                for kw in self._KEYWORDS:

                    if kw in v.lower():

                        keywords.add(kw)

        

        score = 0

        if wm_result:

            score = wm_result.get('total_score', 0) or wm_result.get('sleep_efficiency', 50)

        

        node = {

            'id': node_id,

            'type': 'user_vector',

            'openid': openid[:8],

            'ts': time.time(),

            'keywords': list(keywords),

            'score': score,

            'message_snippet': (message or '')[:100],

        }

        self.graph['nodes'][node_id] = node

        self._dirty = True

        

        # 自动连边: 同用户

        for nid, n in self.graph['nodes'].items():

            if nid != node_id and n.get('openid') == openid[:8]:

                self.graph['edges'].append({

                    'source': node_id, 'target': nid, 'type': 'same_user',

                    'weight': 1.0 / (1.0 + abs(n.get('ts', 0) - node['ts']))

                })

        

        # 自动连边: 相似关键词

        other_ids = [nid for nid in self.graph['nodes'] if nid != node_id]

        for nid in other_ids:

            n = self.graph['nodes'][nid]

            common_kw = set(n.get('keywords', [])) & keywords

            if common_kw:

                self.graph['edges'].append({

                    'source': node_id, 'target': nid, 'type': 'similar',

                    'weight': len(common_kw) / max(len(keywords | set(n.get('keywords', []))), 1)

                })

        

        # 限制图大小（防止无限增长）

        if len(self.graph['nodes']) > 200:

            self._compress_old()

        

        return node_id

    

    def find_related(self, message, fields, max_nodes=8):

        """从图中查找与当前输入相关的记忆节点"""

        text = (message or '').lower()

        query_kw = set(kw for kw in self._KEYWORDS if kw in text)

        for k, v in (fields or {}).items():

            if isinstance(v, str):

                for kw in self._KEYWORDS:

                    if kw in v.lower():

                        query_kw.add(kw)

        

        if not query_kw:

            # 无关键词: 返回最近的 N 条

            sorted_nodes = sorted(

                self.graph['nodes'].values(),

                key=lambda n: n.get('ts', 0), reverse=True

            )

            return sorted_nodes[:max_nodes]

        

        # BFS 找出所有直接+间接关联节点

        candidates = []

        seen_ids = set()

        for nid, n in self.graph['nodes'].items():

            common = set(n.get('keywords', [])) & query_kw

            if common:

                candidates.append({**n, '_match_score': len(common)})

                seen_ids.add(nid)

                # 通过边扩展

                for e in self.graph['edges']:

                    target = None

                    if e['source'] == nid and e['target'] not in seen_ids:

                        target = e['target']

                    elif e['target'] == nid and e['source'] not in seen_ids:

                        target = e['source']

                    if target and target in self.graph['nodes']:

                        tn = self.graph['nodes'][target]

                        candidates.append({**tn, '_match_score': len(common) * e['weight']})

                        seen_ids.add(target)

        

        candidates.sort(key=lambda x: x.get('_match_score', 0), reverse=True)

        return candidates[:max_nodes]

    

    def record_intervention(self, openid, arousal_state, action_id, completed, score_delta):
        """记录一次干预效果

        Args:
            openid: 用户标识
            arousal_state: 干预时的唤醒状态 (anxious/alert/calm/drowsy/sleeping)
            action_id: 干预动作ID (breath_4_7_8 / rain_sound / ...)
            completed: 用户是否完成
            score_delta: 干预前后的评分变化 (正=改善)
        """
        node_id = f'int_{openid[:8]}_{int(time.time())}'
        self.graph['nodes'][node_id] = {
            'id': node_id,
            'type': 'intervention_record',
            'openid': openid[:8],
            'ts': time.time(),
            'arousal': arousal_state,
            'action_id': action_id,
            'completed': completed,
            'score_delta': score_delta,
        }
        self._dirty = True

    def get_intervention_rate(self, action_id, arousal_state=None, min_records=3) -> float:
        """查某个干预动作的历史成功率

        计算方式: (完成且正效果的次数) / (总尝试次数)
        数据不足(< min_records)时返回 0.0

        Args:
            action_id: 干预动作ID
            arousal_state: 可选，限定唤醒状态
            min_records: 最少记录数，不足返回0

        Returns:
            成功率 0.0~1.0
        """
        total, good = 0, 0
        for nid, n in self.graph['nodes'].items():
            if n.get('type') != 'intervention_record':
                continue
            if n.get('action_id') != action_id:
                continue
            if arousal_state and n.get('arousal') != arousal_state:
                continue
            total += 1
            if n.get('completed') and n.get('score_delta', 0) > 0:
                good += 1

        if total < min_records:
            return 0.0
        return good / max(total, 1)

    def _compress_old(self):

        """聚合 7 天前的旧节点"""

        cutoff = time.time() - 7 * 86400

        old_nodes = {nid: n for nid, n in self.graph['nodes'].items()

                     if n.get('ts', 0) < cutoff}

        if len(old_nodes) < 5:

            return

        

        # 按用户分组

        by_user = {}

        for nid, n in old_nodes.items():

            uid = n.get('openid', 'unknown')

            by_user.setdefault(uid, []).append(n)

        

        for uid, nodes in by_user.items():

            if len(nodes) < 3:

                continue

            avg_score = sum(n.get('score', 0) for n in nodes) / len(nodes)

            all_kw = set()

            for n in nodes:

                all_kw.update(n.get('keywords', []))

            agg_id = f'aggregated_{uid}_{int(cutoff)}'

            self.graph['nodes'][agg_id] = {

                'id': agg_id, 'type': 'aggregated',

                'openid': uid, 'ts': cutoff,

                'keywords': list(all_kw),

                'score': avg_score,

                'message_snippet': f'[{len(nodes)} 条聚合: {uid}]',

            }

            # 删除原始节点

            for n in nodes:

                del self.graph['nodes'][n['id']]

        self._dirty = True

    

    def _load(self, path):

        try:

            with open(path, 'r', encoding='utf-8') as f:

                self.graph = json.load(f)

        except (FileNotFoundError, json.JSONDecodeError):

            pass

    

    def save(self, path):

        if self._dirty:

            os.makedirs(os.path.dirname(path), exist_ok=True)

            with open(path, 'w', encoding='utf-8') as f:

                json.dump(self.graph, f, ensure_ascii=False, indent=2)

            self._dirty = False



# 全局单例

_GRAPH = None

GRAPH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'wm_memory_graph.json')






def get_perception_graph():

    global _GRAPH, GRAPH_PATH

    if _GRAPH is None:

        _GRAPH = PerceptionGraph(GRAPH_PATH)

        # Lazy populate keywords from CATEGORIES-like sources

        _GRAPH_KEYWORDS = [

            'alcohol', 'drink', 'digest', 'stomach', 'anxiety', 'stress',

            'pain', 'discomfort', 'env', 'habit', 'circadian', 'rhythm',

            'insomnia', 'wake', 'sleep', 'snore', 'breath', 'nightmare',

            'tired', 'fatigue', 'dream', 'melatonin', 'caffeine', 'exercise',

            'meditation', 'breathing', 'relax', 'calm', 'noise', 'light',

        ]

    return _GRAPH



concept_proof_anchor = 'PERCEPTION_GRAPH_ACTIVE'


if __name__ == '__main__':
    print('wm_memory v2.0 loaded')
    print(f'Memory file: {MEMORY_PATH}')
