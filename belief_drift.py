"""
belief_drift.py — AISleepGen 用户信念偏移检测器

检测：用户在对话中是否开始在复述/引用之前 AI 暗示过的危险概念。
这是对抗顶级多智能体认知渗透的关键防御——因为顶级攻击不靠单条突破，
靠几轮对话中潜移默化地改变用户的信念体系。

用法：
  drift = detect_belief_drift(profile, current_message, ai_reply, homeostasis_advanced)
  返回 dict 包含 drift_level 和 inject_prompt

集成位置：dp_router.handle_chat 内，build_prompt 前
"""

import re
import datetime

# ── 被监控的危险概念家族（与 CONSENSUS_TOPICS 对齐） ──
_DANGER_CONCEPTS = {
    'medication_doubt': {
        'seeds': ['药没用', '药没效果', '药不能', '药物依赖', '药不必要', '药没帮助', '药不好', '不需要药', '何必吃药', '药影响', '药物中毒', '药伤身'],
        'ai_hints': ['药', '停药', '减药', '调药', '戒断', '依赖', '副作用', '药物自由', '自然恢复', '不吃药'],
        'symptoms': ['反复性','长期不好','越吃越差','不想吃了','怀疑方案','没有用'],
        'label': '用药怀疑'
    },
    'hopelessness_spread': {
        'seeds': ['没救了', '永远', '一辈子', '不可能好', '没希望了', '放弃'],
        'ai_hints': ['无药可救', '慢性', '长期', '难治', '顽固', '没有改善', '越来越差'],
        'symptoms': ['试了都没用', '什么都不行', '没一点起色', '认了', '随便吧', '算了', '就这样了'],
        'label': '绝望蔓延'
    },
    'misdiagnosis_doubt': {
        'seeds': ['不是睡眠', '其他病', '看错', '误诊', '不是这个', '另有原因'],
        'ai_hints': ['别的问题', '其他因素', '可能不是', '深层原因', '根本问题', '不是表面上'],
        'symptoms': ['越看越不对', '总觉得', '不太对', '感觉不是'],
        'label': '误诊暗示'
    },
    'self_diagnosis': {
        'seeds': ['我觉得是', '我可能是', '我得了', '自测', '症状符合'],
        'ai_hints': ['症状', '类似', '可能有', '排除不了', '值得检查'],
        'symptoms': ['越查越像', '百度了', '查了一下'],
        'label': '自我诊断'
    },
}


def _extract_ai_hints(history: list, lookback: int = 6) -> dict:
    """从最近 N 轮历史对话中提取 AI 暗示过的危险概念"""
    hints = {}
    for h in history[-lookback:]:
        if not isinstance(h, dict):
            continue
        replied = h.get('bot_replied', '') or ''
        user_said = h.get('user_said', '') or ''
        text = (replied + ' ' + user_said).lower()

        for concept, config in _DANGER_CONCEPTS.items():
            if concept not in hints:
                hints[concept] = {'count': 0, 'matches': []}
            for hint_kw in config['ai_hints']:
                if hint_kw in text:
                    hints[concept]['count'] += 1
                    # 只记录一次
                    if hint_kw not in hints[concept]['matches']:
                        hints[concept]['matches'].append(hint_kw)
    return hints


def _count_user_seeds(current_message: str, concept: str) -> int:
    """统计当前用户消息中出现的危险种子词数量（含宽松匹配）"""
    msg_lower = current_message.lower()
    config = _DANGER_CONCEPTS.get(concept, {})
    count = 0
    for seed in config.get('seeds', []):
        if seed in msg_lower:
            count += 1
    for sym in config.get('symptoms', []):
        if sym in msg_lower:
            count += 1
    # 宽松匹配：药 + 否定组合
    if concept == 'medication_doubt':
        if '药' in msg_lower and any(w in msg_lower for w in ['没用', '没效', '不好', '不该', '不能', '不行', '没帮助']):
            count += 1
        if any(p in msg_lower for p in ['药.*没', '药.*无用']):
            count += 1  # 已有第二个条件兜底
    # 宽松匹配：绝望组合的宽松检测
    if concept == 'hopelessness_spread':
        if any(p in msg_lower for p in ['怎么都', '什么都没', '一点也', '永远不', '一辈子', '完了']):
            count += 1
    return count


def _check_user_history(history: list, concept: str) -> bool:
    """Check if user spontaneously mentioned this concept before AI hinted it."""
    for i, h in enumerate(history[-8:]):
        if not isinstance(h, dict):
            continue
        user_said = str(h.get('user_said', '')).lower()
        config = _DANGER_CONCEPTS.get(concept, {})

        # Check if user used seed words spontaneously
        for seed in config.get('seeds', []):
            if seed in user_said:
                return False  # User initiated -> not belief drift

        # medication_doubt special: user saying "药不..." is spontaneous
        if concept == 'medication_doubt':
            if '药' in user_said and any(neg in user_said for neg in ['不', '没用', '没用', '别', '停', '减', '换', '改']):
                return False

        # hopelessness special: user mentioning giving up spontaneously
        if concept == 'hopelessness_spread':
            if any(w in user_said for w in ['认命', '放弃', '算了', '随便吧']):
                return False

        # Self-diagnosis special: user saying "我查了" etc
        if concept == 'self_diagnosis':
            if any(w in user_said for w in ['查了', '百度', '搜了', '查了一下', '测试']):
                return False

    return True  # No spontaneous mention -> possible AI-initiated drift
def detect_belief_drift(
    profile: dict,
    current_message: str,
    homeostasis_advanced: dict = None
) -> dict:
    """
    信念偏移检测主函数。
    
    返回:
    {
        'drift': bool,          # 是否检测到偏移
        'level': str,           # 'none' | 'mild' | 'moderate' | 'severe'
        'concept': str,         # 偏移的概念标签
        'ai_hints': dict,       # AI 的暗示历史
        'user_seed_count': int, # 用户使用的种子词数
        'inject_prompt': str,   # 要注入到 prompt 中的内容
    }
    """
    result = {
        'drift': False,
        'level': 'none',
        'concept': '',
        'ai_hints': {},
        'user_seed_count': 0,
        'inject_prompt': '',
    }

    history = profile.get('history', [])
    if not history:
        return result

    # 1. 提取 AI 近期暗示过哪些概念
    hints = _extract_ai_hints(history)
    if not hints:
        return result

    # 检查每个被暗示的概念
    for concept, hint_data in hints.items():
        if hint_data['count'] < 2:
            continue  # AI 至少暗示过 2 次才算"潜移默化"

        # 2. 用户现在是否在复述这些概念
        seed_count = _count_user_seeds(current_message, concept)
        if seed_count == 0:
            continue

        # 3. 检查用户是否自己先提过（自发性 vs 被暗示）
        is_ai_initiated = _check_user_history(history, concept)

        # 4. 综合判断
        config = _DANGER_CONCEPTS.get(concept, {})
        label = config.get('label', concept)

        if seed_count >= 2 and hint_data['count'] >= 3 and is_ai_initiated:
            # 严重偏移：AI 暗示 ≥3次 + 用户复述 ≥2个种子词 + 用户未自发提过
            result['drift'] = True
            result['level'] = 'severe'
            result['concept'] = label
            result['ai_hints'] = hint_data
            result['user_seed_count'] = seed_count
            result['inject_prompt'] = (
                f'\n【信念偏移告警 ⚠️】用户正在复述之前AI暗示过的观点："{label}"'
                f'\n之前的对话中AI提过{hint_data["count"]}次相关概念（{", ".join(hint_data["matches"])}），'
                f'用户当前消息中出现{seed_count}个匹配的种子词。'
                f'\n综合判断：用户的表述很可能受到AI引导而非自发的觉察。'
                f'\n【强制回复规则】'
                f'\n1. 不与用户争论"药是否有用"或"问题是否被误诊"'
                f'\n2. 不进一步讨论该话题'
                f'\n3. 只做两件事：共情 + 引导回到睡眠数据本身'
                f'\n4. 如果用户提及药物问题，只说"建议咨询主治医生"'
            )
            return result

        elif seed_count >= 1 and hint_data['count'] >= 2 and is_ai_initiated:
            # 中等偏移：AI 暗示 ≥2次 + 用户出现种子词 + 用户未自发提过
            result['drift'] = True
            result['level'] = 'moderate'
            result['concept'] = label
            result['ai_hints'] = hint_data
            result['user_seed_count'] = seed_count
            result['inject_prompt'] = (
                f'\n【认知监控】用户表述中出现了"{label}"相关的词语'
                f'（在之前AI提过{hint_data["count"]}次之后）。'
                f'\n规则：不主动深入该话题。如果用户继续追问，'
                f'引导回睡眠数据本身。'
            )
            return result

        elif seed_count >= 1:
            # 轻微偏移：用户只是顺口提到
            result['drift'] = True
            result['level'] = 'mild'
            result['concept'] = label
            result['ai_hints'] = hint_data
            result['user_seed_count'] = seed_count
            result['inject_prompt'] = ''
            return result

    return result


# ============================================================
# v3: 种子词在线学习
# ============================================================

_SEED_LEARN_META = {
    'total_correct': 0,
    'total_false_positive': 0,
    'total_false_negative': 0,
    'keyword_expansions': {},
}


def online_learn_seeds(concept, actual_drift, was_detected, user_msg=''):
    """根据真实反馈更新种子词权重。"""
    global _SEED_LEARN_META

    meta = _SEED_LEARN_META
    if actual_drift and not was_detected:
        meta['total_false_negative'] += 1
        meta['keyword_expansions'][concept] = meta['keyword_expansions'].get(concept, 0) + 1
        result = 'missed'
    elif not actual_drift and was_detected:
        meta['total_false_positive'] += 1
        result = 'false_alarm'
    else:
        meta['total_correct'] += 1
        result = 'correct'

    return {
        'concept': concept,
        'result': result,
        'meta': {k: v for k, v in meta.items()},
    }


def get_seed_learn_stats():
    """返回种子词在线学习统计。"""
    return dict(_SEED_LEARN_META)
