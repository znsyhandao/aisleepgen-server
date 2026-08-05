# -*- coding: utf-8 -*-
"""
algo_recommender.py — 消费通道 v3 个性化推荐（生产轻聚合原则）
读用户睡眠画像 -> 规则映射推荐主题 -> 匹配落地算法 -> top3 + 理由
纯规则零进化逻辑: 不调用 LLM, 不写进化状态, 只读 profile + 只读注册表
"""
import os
import json
import re

_BASE = os.path.dirname(os.path.abspath(__file__))


def _load_profile(openid='default', base=None):
    """读 user_profile.json (只读, 不创建不写回)"""
    base = base or _BASE
    p = os.path.join(base, 'user_profile.json')
    if not os.path.exists(p):
        return {}
    try:
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
        prof = data.get(openid) or data.get('default') or {}
        return prof if isinstance(prof, dict) else {}
    except Exception:
        return {}


def _to_num(v):
    """'未知'/None/非数字 -> None"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    m = re.match(r'^\s*(\d+(?:\.\d+)?)', s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _extract_features(profile):
    """从 profile 提取睡眠画像特征 (全容错)"""
    lat = profile.get('latest') or {}
    sd = lat.get('sleep_data') or {}
    ui = profile.get('user_info') or {}
    hist = profile.get('history') or []
    # 最近一条有 wm_score 的历史 (fallback)
    last_scores = [h.get('wm_score') for h in hist if isinstance(h, dict) and h.get('wm_score')]
    feat = {
        'score': _to_num(lat.get('score')) if _to_num(lat.get('score')) is not None else (
            float(last_scores[-1]) if last_scores else None),
        'latency_min': _to_num(sd.get('sleep_latency')),
        'awake_times': _to_num(sd.get('awake_times')),
        'stress': _to_num(lat.get('stress')) if _to_num(lat.get('stress')) is not None else _to_num(ui.get('stress_level')),
        'sleep_type': str(ui.get('sleep_type') or ''),
        'main_issue': str(ui.get('main_issue') or ''),
        'quality': _to_num(lat.get('quality')),
    }
    return feat


# 推荐规则: (条件函数, 主题关键词, 理由模板)
_RULES = [
    # 入睡困难 / 失眠
    (lambda f: f['latency_min'] is not None and f['latency_min'] > 30,
     ['冥想', '放松'],
     '你的入睡潜伏期约 {latency} 分钟，偏长。推荐冥想放松类算法，帮助缩短入睡时间。'),
    (lambda f: '失眠' in f['main_issue'] or '入睡' in f['main_issue'],
     ['冥想', '放松'],
     '你的主要困扰是「{issue}」。推荐冥想放松类算法，配合改善入睡体验。'),
    # 夜醒多
    (lambda f: f['awake_times'] is not None and f['awake_times'] >= 3,
     ['节律', '同步'],
     '你夜间醒来 {awake} 次，偏多。推荐节律同步类算法，帮助稳定睡眠结构。'),
    # 压力高
    (lambda f: f['stress'] is not None and f['stress'] > 6,
     ['压力', '情绪'],
     '你的压力水平 {stress}，偏高。推荐情绪压力调节类算法，睡前减压。'),
    # 睡不深 / 质量低
    (lambda f: ('睡不深' in f['main_issue'] or '浅' in f['main_issue']) or
     (f['score'] is not None and f['score'] < 70),
     ['质量'],
     '你的睡眠质量分 {score}，有提升空间。推荐质量评估类算法，定位薄弱环节。'),
    # 夜猫型节律
    (lambda f: '夜猫' in f['sleep_type'],
     ['节律', '双过程'],
     '你是「{sleep_type}」作息。推荐昼夜节律类算法，评估并优化生物钟相位。'),
    # 兜底: 正常作息
    (lambda f: True,
     ['双过程', '临界'],
     '你的作息整体平稳。推荐双过程模型类算法，从稳态压力与节律两个维度持续跟踪。'),
]


def recommend(profile, registry_algos, top_n=3):
    """规则映射 + 注册表匹配 -> [{algo, reason}]"""
    feat = _extract_features(profile)
    # 判定命中的规则 (第一条命中的为主, 再补一条不同的)
    matched = []
    seen_reason = set()
    for cond, keys, tpl in _RULES:
        if cond(feat):
            reason = tpl.format(
                latency=int(feat['latency_min']) if feat['latency_min'] else '?',
                awake=int(feat['awake_times']) if feat['awake_times'] else '?',
                stress=feat['stress'] if feat['stress'] is not None else '?',
                score=feat['score'] if feat['score'] is not None else '?',
                issue=feat['main_issue'] or '睡眠质量',
                sleep_type=feat['sleep_type'] or '日常作息',
            )
            matched.append((keys, reason))
            if len(matched) >= 2:
                break
    if not matched:
        matched.append((['双过程'], '推荐双过程模型类算法，持续跟踪你的睡眠节律。'))

    # 注册表匹配: 按主题关键词找算法 (每个主题取 1 个, 保证多样性)
    chosen = []
    used = set()
    for keys, reason in matched:
        picked = None
        for a in registry_algos:
            name = a.get('algo', '')
            if name in used:
                continue
            if any(k in name for k in keys):
                picked = {'algo': name, 'reason': reason,
                          'func': a.get('func', '')}
                used.add(name)
                break
        if picked:
            chosen.append(picked)
        if len(chosen) >= top_n:
            return {'features': feat, 'recommendations': chosen}
    # 不足则补双过程/临界 (每个补一个)
    for a in registry_algos:
        name = a.get('algo', '')
        if name in used:
            continue
        if '双过程' in name or '临界' in name:
            chosen.append({'algo': name, 'reason': matched[0][1] if matched else '',
                           'func': a.get('func', '')})
            used.add(name)
            if len(chosen) >= top_n:
                break
    return {'features': feat, 'recommendations': chosen}


def recommend_for(openid='default', base=None, registry_path=None):
    """一键入口: 读 profile + 注册表 -> 推荐"""
    base = base or _BASE
    profile = _load_profile(openid, base)
    reg_path = registry_path or os.path.join(base, 'core_dev', 'algo_registry.json')
    algos = []
    try:
        with open(reg_path, 'r', encoding='utf-8') as f:
            algos = json.load(f).get('algos', [])
    except Exception:
        algos = []
    if not profile:
        return {'openid': openid, 'error': 'no_profile', 'features': {}, 'recommendations': []}
    out = recommend(profile, algos)
    out['openid'] = openid
    return out


if __name__ == '__main__':
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    oid = sys.argv[1] if len(sys.argv) > 1 else 'default'
    r = recommend_for(oid)
    print('openid:', oid)
    print('features:', json.dumps(r.get('features', {}), ensure_ascii=False))
    print('recommendations:')
    for rec in r.get('recommendations', []):
        print(' -', rec['algo'], '|', rec['reason'][:60])
