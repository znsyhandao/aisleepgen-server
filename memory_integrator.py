# memory_integrator.py v1.0 — 三层记忆整合器
#
# 职责:
#   1. 睡前整理(sleep_consolidate): 工作记忆 → 情景记忆
#   2. 每周整合(weekly_integrate): 情景记忆 → 语义记忆  
#   3. 聊天注入(recall): 三层记忆融合 → prompt上下文
#
# 集成点:
#   - working_memory (工作记忆层)
#   - episodic_memory (情景记忆层)
#   - semantic_memory (语义记忆层)
#   - chat_prompt_builder (注入到LLM prompt)
#   - scheduler_daemon (定时触发整理)

import json, os, time
from datetime import datetime, timedelta

PROJECT_ROOT = r'D:\AISleepGen_Optimized'


def sleep_consolidate(openid: str) -> dict:
    """睡前整理: 工作记忆→情景记忆"""
    from working_memory import get_working_memory
    from episodic_memory import EpisodicMemory

    wm = get_working_memory()
    em = EpisodicMemory(openid)

    today = datetime.now().strftime('%Y-%m-%d')

    # 1. 获取今天的工作记忆
    recent = []
    if wm:
        try:
            recent = wm.recent(openid, n=20)
        except Exception:
            pass

    # 2. 过滤今天的记录
    today_entries = [e for e in recent if e.get('timestamp', '')[:10] == today]

    if not today_entries:
        return {'status': 'no_data', 'reason': 'no entries today'}

    # 3. 提取关键信息
    scores = [e['score_obs'] for e in today_entries if e.get('score_obs') and e['score_obs'] > 0]
    texts = [e.get('text', '') for e in today_entries if e.get('text')]

    # 4. 提取标签
    tags = ['consolidated']
    combined_text = ' '.join(texts)
    if any(k in combined_text for k in ['失眠', '睡不着', '焦虑']):
        tags.append('焦虑')
    if any(k in combined_text for k in ['好', '不错', '改善']):
        tags.append('正面')
    if any(k in combined_text for k in ['酒精', '酒', '喝']):
        tags.append('酒精')
    if any(k in combined_text for k in ['咖啡', '茶']):
        tags.append('咖啡因')

    # 5. 提取事件
    events = []
    for t in texts:
        if len(t) > 5 and not t.startswith('['):
            events.append(t[:80])

    # 6. 生成摘要
    avg_score = round(sum(scores)/len(scores), 1) if scores else None
    if avg_score:
        summary = f'{today}: 评分{avg_score}, 对话{len(texts)}条'
    else:
        summary = f'{today}: 对话{len(texts)}条'

    # 7. 已存在则不重复添加
    existing = em.get_by_date(today)
    if existing:
        return {'status': 'skipped', 'reason': 'already consolidated', 'existing': len(existing)}

    # 8. 写入情景记忆
    episode = em.add(today, summary, events, tags, avg_score, source='sleep_consolidate')

    return {
        'status': 'done',
        'date': today,
        'avg_score': avg_score,
        'events': len(events),
        'tags': tags,
    }


def weekly_integrate(openid: str) -> dict:
    """每周整合: 情景记忆→语义记忆"""
    from episodic_memory import EpisodicMemory
    from semantic_memory import weekly_extract

    result = weekly_extract(openid)
    return result


def recall(openid: str, max_patterns: int = 3, max_episodes: int = 3) -> str:
    """聊天时检索三层记忆，返回注入prompt的文本"""
    from working_memory import get_working_memory
    from episodic_memory import EpisodicMemory
    from semantic_memory import SemanticMemory

    lines = []
    wm = None

    # ===== 工作记忆 (最近) =====
    try:
        wm_obj = get_working_memory()
        if wm_obj:
            recent = wm_obj.recent(openid, n=5)
            if recent:
                items = []
                for e in recent:
                    ts = e.get('timestamp', '')[:16]
                    s = e.get('score_obs')
                    t = e.get('text', '')[:50]
                    items.append(f'{ts} score={s} "{t}"')
                lines.append('[最近情况]')
                lines.extend(items[:3])
    except Exception:
        pass

    # ===== 情景记忆 (本周/重要事件) =====
    try:
        em = EpisodicMemory(openid)
        episodes = em.get_recent(max_episodes)
        if episodes:
            lines.append('')
            lines.append('[本周记忆]')
            for ep in episodes:
                d = ep.get('date', '?')
                s = ep.get('score', '?')
                sm = ep.get('summary', '')[:60]
                tags = ', '.join(ep.get('tags', [])[:3])
                lines.append(f'  {d} 评分{s} {sm} [{tags}]')
    except Exception:
        pass

    # ===== 语义记忆 (长期模式) =====
    try:
        sm = SemanticMemory(openid)
        semantic = sm.get_context()
        if semantic and semantic != '[语义记忆]':
            lines.append('')
            lines.append(semantic)
    except Exception:
        pass

    return '\n'.join(lines)


def recall_for_prompt(openid: str) -> str:
    """生成LLM prompt可用的记忆上下文（不超过800字）"""
    text = recall(openid)
    if len(text) > 800:
        text = text[:797] + '...'
    return text


# ===== 快捷入口：供scheduler_daemon调用 =====

def run_daily_consolidation():
    """每天睡前自动整理所有活跃用户"""
    from scheduler_daemon import _get_active_users
    users = _get_active_users()
    if not users:
        return {'status': 'skipped', 'reason': 'no active users'}

    results = []
    for openid, profile in users:
        try:
            r = sleep_consolidate(openid)
            results.append({'openid': openid, **r})
        except Exception as e:
            results.append({'openid': openid, 'status': 'error', 'error': str(e)})

    return {
        'status': 'done',
        'total': len(users),
        'results': results,
    }


def run_weekly_integration():
    """每周整合"""
    from scheduler_daemon import _get_active_users
    users = _get_active_users()
    if not users:
        return {'status': 'skipped', 'reason': 'no active users'}

    results = []
    for openid, profile in users:
        try:
            r = weekly_integrate(openid)
            results.append({'openid': openid, **r})
        except Exception as e:
            results.append({'openid': openid, 'status': 'error', 'error': str(e)})

    return {
        'status': 'done',
        'total': len(users),
        'results': results,
    }
