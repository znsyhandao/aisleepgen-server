# episodic_memory.py v1.0 — 情景记忆层
# 保存1-30天的重要事件，支持按时间/主题检索
# 自动从working_memory和daily数据提取摘要
#
# 存储: data/episodic/{openid}.json
# 每条记录: {id, date, summary, events[], tags[], score, source}

import json, os, time
from datetime import datetime, timedelta
from collections import defaultdict

PROJECT_ROOT = r'D:\AISleepGen_Optimized'
DATA_DIR = os.path.join(PROJECT_ROOT, 'data', 'episodic')

os.makedirs(DATA_DIR, exist_ok=True)


class EpisodicMemory:
    """情景记忆"""

    def __init__(self, openid):
        self.openid = openid
        self.path = os.path.join(DATA_DIR, f'{openid}.json')
        self._cache = None

    def _load(self) -> list:
        """加载所有情景记录"""
        if self._cache is not None:
            if isinstance(self._cache, list):
                return self._cache
        try:
            if os.path.exists(self.path):
                with open(self.path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._cache = data if isinstance(data, list) else []
                    return self._cache
        except Exception:
            pass
        self._cache = []
        return self._cache

    def _save(self, episodes: list):
        """保存"""
        self._cache = episodes
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(episodes, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f'[Episodic] Save error: {e}')

    def add(self, date: str, summary: str, events: list, tags: list, score: int = None, source: str = 'chat'):
        """添加一条情景记录"""
        episodes = self._load()
        episode = {
            'id': f'{date}_{int(time.time())}',
            'date': date,
            'summary': summary,
            'events': events,
            'tags': tags,
            'score': score,
            'source': source,
            'created_at': datetime.now().isoformat(),
        }
        episodes.append(episode)
        self._save(episodes)
        return episode

    def get_by_date(self, date: str) -> list:
        """按日期获取"""
        return [e for e in self._load() if e['date'] == date]

    def get_range(self, start: str, end: str) -> list:
        """按日期范围获取"""
        return [e for e in self._load() if start <= e['date'] <= end]

    def get_recent(self, n: int = 7) -> list:
        """获取最近n条"""
        episodes = self._load()
        episodes.sort(key=lambda x: x.get('date', ''), reverse=True)
        return episodes[:n]

    def get_by_tag(self, tag: str) -> list:
        """按标签检索"""
        return [e for e in self._load() if tag in e.get('tags', [])]

    def search(self, query: str) -> list:
        """全文检索（简单版，以后可升级为embedding）"""
        q = query.lower()
        results = []
        for e in self._load():
            text = f"{e.get('summary','')} {' '.join(e.get('events',[]))} {' '.join(e.get('tags',[]))}".lower()
            if q in text:
                results.append(e)
        return results

    def get_weekly_summary(self) -> dict:
        """获取本周概要"""
        episodes = self._load()
        today = datetime.now()
        week_start = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')
        week_episodes = [e for e in episodes if e['date'] >= week_start]

        scores = [e['score'] for e in week_episodes if e.get('score')]
        tags = {}
        for e in week_episodes:
            for t in e.get('tags', []):
                tags[t] = tags.get(t, 0) + 1

        return {
            'days': len(set(e['date'] for e in week_episodes)),
            'episodes': len(week_episodes),
            'avg_score': round(sum(scores)/len(scores), 1) if scores else None,
            'top_tags': sorted(tags.items(), key=lambda x: -x[1])[:5],
            'period': f'{week_start} ~ {today.strftime("%Y-%m-%d")}',
        }

    def get_semantic_feed(self) -> list:
        """为语义记忆层提供原始数据源"""
        return self._load()

    def summarize_day(self, date: str) -> str:
        """生成单日摘要文本"""
        episodes = self.get_by_date(date)
        if not episodes:
            return f'{date}: 无记录'
        scores = [e['score'] for e in episodes if e.get('score')]
        tags = set()
        events = []
        for e in episodes:
            tags.update(e.get('tags', []))
            events.extend(e.get('events', []))
        avg = round(sum(scores)/len(scores), 1) if scores else 'N/A'
        tag_str = ', '.join(sorted(tags)[:3])
        return f'{date}: 评分{avg}, 标签[{tag_str}], 事件{len(events)}条'


def auto_add_from_diary(openid: str):
    """从auto_diary结果自动添加到情景记忆"""
    try:
        from auto_diary import AutoDiary
        ad = AutoDiary()
        diary = ad.generate_diary(openid)
        em = EpisodicMemory(openid)

        today = diary['date']
        score = diary.get('composite_score')
        summary = diary['diary_text'].split('\n')[1] if '\n' in diary['diary_text'] else diary['diary_text'][:100]

        events = []
        if diary.get('data', {}).get('ring'):
            r = diary['data']['ring']
            events.append(f"手环: 深睡{r.get('deep_sleep',0)}min, REM{r.get('rem',0)}min")
        if diary.get('data', {}).get('audio'):
            a = diary['data']['audio']
            events.append(f"音频: 鼾声{a.get('snore_pct',0)}%, 稳定{a.get('stability',0)}")

        tags = ['auto_diary']
        if diary.get('composite_score', 50) >= 80:
            tags.append('优质睡眠')
        elif diary.get('composite_score', 50) < 50:
            tags.append('睡眠差')

        em.add(today, summary, events, tags, score, source='auto_diary')
        return True
    except Exception as e:
        print(f'[Episodic] auto_add error: {e}')
        return False
