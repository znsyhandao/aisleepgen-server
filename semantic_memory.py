# semantic_memory.py v1.0 — 语义记忆层
# 保存>30天的长期模式、偏好、习惯
# 每周自动从情景记忆整合
#
# 存储: data/semantic/{openid}.json
# 结构:
# {
#   "patterns": [{"pattern": "周一差", "confidence": 0.8, "evidence": [...]}],
#   "preferences": [{"aspect": "冥想类型", "value": "呼吸引导", "source": "多次选择"}],
#   "triggers": [{"trigger": "饮酒", "effect": "score_drop_12", "count": 3}],
#   "best_conditions": {"bedtime": "23:00", "activity": "medium", ...}
# }

import json, os, time
from datetime import datetime, timedelta
from collections import defaultdict, Counter

PROJECT_ROOT = r'D:\AISleepGen_Optimized'
DATA_DIR = os.path.join(PROJECT_ROOT, 'data', 'semantic')

os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_SEMANTIC = {
    'patterns': [],
    'preferences': [],
    'triggers': [],
    'best_conditions': {},
    'last_updated': None,
    'version': '1.0',
}


class SemanticMemory:
    """语义记忆"""

    def __init__(self, openid):
        self.openid = openid
        self.path = os.path.join(DATA_DIR, f'{openid}.json')
        self._cache = None

    def _load(self) -> dict:
        if self._cache is not None:
            return self._cache
        try:
            if os.path.exists(self.path):
                with open(self.path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in DEFAULT_SEMANTIC.items():
                        if k not in data:
                            data[k] = v
                    self._cache = data
                    return data
        except Exception:
            pass
        self._cache = dict(DEFAULT_SEMANTIC)
        return self._cache

    def _save(self, data: dict = None):
        if data:
            self._cache = data
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f'[Semantic] Save error: {e}')

    def add_pattern(self, pattern: str, confidence: float, evidence: list):
        """添加/更新行为模式"""
        data = self._load()
        existing = [p for p in data['patterns'] if p['pattern'] == pattern]
        if existing:
            existing[0]['confidence'] = max(existing[0]['confidence'], confidence)
            existing[0]['evidence'].extend(evidence)
            existing[0]['evidence'] = list(set(existing[0]['evidence']))
        else:
            data['patterns'].append({
                'pattern': pattern,
                'confidence': confidence,
                'evidence': evidence,
                'created_at': datetime.now().isoformat(),
            })
        data['last_updated'] = datetime.now().isoformat()
        self._save(data)

    def add_preference(self, aspect: str, value: str, source: str = 'observed'):
        """添加/更新偏好"""
        data = self._load()
        existing = [p for p in data['preferences'] if p['aspect'] == aspect]
        if existing:
            existing[0]['value'] = value
            existing[0]['source'] = source
        else:
            data['preferences'].append({
                'aspect': aspect,
                'value': value,
                'source': source,
                'created_at': datetime.now().isoformat(),
            })
        data['last_updated'] = datetime.now().isoformat()
        self._save(data)

    def add_trigger(self, trigger: str, effect: str):
        """记录触发因素"""
        data = self._load()
        existing = [t for t in data['triggers'] if t['trigger'] == trigger]
        if existing:
            existing[0]['count'] = existing[0].get('count', 1) + 1
        else:
            data['triggers'].append({
                'trigger': trigger,
                'effect': effect,
                'count': 1,
                'created_at': datetime.now().isoformat(),
            })
        data['last_updated'] = datetime.now().isoformat()
        self._save(data)

    def get_context(self) -> str:
        """获取简化的语义上下文（给LLM prompt注入）"""
        data = self._load()
        lines = ['[语义记忆]']
        if data['patterns']:
            top = sorted(data['patterns'], key=lambda x: -x['confidence'])[:3]
            parts = []
            for p in top:
                parts.append('{} ({:.0%})'.format(p['pattern'], p['confidence']))
            lines.append('  行为模式: ' + ', '.join(parts))
        if data['preferences']:
            parts = []
            for p in data['preferences'][:3]:
                parts.append('{}={}'.format(p['aspect'], p['value']))
            lines.append('  偏好: ' + '; '.join(parts))
        if data['triggers']:
            top_t = sorted(data['triggers'], key=lambda x: -x['count'])[:3]
            parts = []
            for t in top_t:
                parts.append('{}({}次)'.format(t['trigger'], t['count']))
            lines.append('  触发因素: ' + ', '.join(parts))
        if data.get('best_conditions'):
            lines.append(f"  最佳条件: {json.dumps(data['best_conditions'], ensure_ascii=False)}")
        return '\n'.join(lines)

    def get_preference(self, aspect: str) -> str:
        """获取某个偏好的值"""
        data = self._load()
        for p in data['preferences']:
            if p['aspect'] == aspect:
                return p['value']
        return None


def weekly_extract(openid: str, episodic=None) -> dict:
    """每周从情景记忆提取语义记忆"""
    from episodic_memory import EpisodicMemory
    em = episodic or EpisodicMemory(openid)
    sm = SemanticMemory(openid)

    episodes = em.get_semantic_feed()
    if not episodes:
        return {'status': 'no_data'}

    # 1. 提取评分模式
    scores_by_day = defaultdict(list)
    for e in episodes:
        day = e['date']
        s = e.get('score')
        if s:
            try:
                dt = datetime.fromisoformat(day)
                day_name = ['周一','周二','周三','周四','周五','周六','周日'][dt.weekday()]
                scores_by_day[day_name].append(s)
            except Exception:
                scores_by_day[day].append(s)

    for day, vals in scores_by_day.items():
        if len(vals) >= 2:
            avg = sum(vals) / len(vals)
            overall = sum(sum(v) for v in scores_by_day.values()) / max(1, sum(len(v) for v in scores_by_day.values()))
            diff = avg - overall
            if abs(diff) > 8:
                direction = '较好' if diff > 0 else '较差'
                sm.add_pattern(f'{day}睡眠{direction}(+{diff:.0f}分)', min(0.9, len(vals)*0.15), [f'数据{len(vals)}天'])

    # 2. 提取触发因素
    for e in episodes:
        tags = e.get('tags', [])
        score = e.get('score', 50)
        if '酒精' in tags or '饮酒' in tags or 'alcohol' in tags:
            sm.add_trigger('饮酒', f'score_{score}')
        if '咖啡' in tags or 'caffeine' in tags:
            sm.add_trigger('咖啡因', f'score_{score}')
        if '焦虑' in tags or 'anxiety' in tags:
            sm.add_trigger('焦虑', f'score_{score}')

    # 3. 提取偏好
    tag_counter = Counter()
    for e in episodes:
        for t in e.get('tags', []):
            tag_counter[t] += 1

    fav_tag = tag_counter.most_common(1)
    if fav_tag and fav_tag[0][1] >= 2:
        sm.add_preference('偏好话题', fav_tag[0][0], '多次出现')

    sm._load()  # ensure cache is initialized
    sm._cache['last_updated'] = datetime.now().isoformat()
    sm._save()

    return {
        'status': 'done',
        'patterns': len(sm._cache['patterns']),
        'preferences': len(sm._cache['preferences']),
        'triggers': len(sm._cache['triggers']),
    }
