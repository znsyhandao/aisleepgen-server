#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
toy_agent.py — AI玩具灵魂Agent层 v1
适配AISleepGen世界模型为"陪伴玩具Agent"

核心升级：
  1. 可配置角色人格（暖心/调皮/知性/冷幽默）
  2. 结构化记忆（事件+情绪+行为模式）
  3. 情绪识别（从用户输入推断6种基础情绪）
  4. 主动唤醒（无聊/失眠/固定时间）
  5. 玩具友好输出（短句+语气词+可语音朗读）

用法:
  from toy_agent import ToyAgent
  
  agent = ToyAgent(persona='warm')
  agent.remember('user_id', 'event', context)
  reply = agent.reply('user_id', '今晚又睡不着了')

依赖: deepseek proxy via API call
"""

import json, time, os, re, hashlib, threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# ============================================================
# 1. 角色人格系统
# ============================================================

PERSONAS = {
    'warm': {
        'name': '暖暖',
        'description': '温暖的睡眠陪伴小熊',
        'tone': '温柔、舒缓、带着淡淡的微笑',
        'catchphrases': ['乖~', '没关系的', '我们慢慢来'],
        'speech_style': '多用叠词和儿化音，语调轻柔',
        'max_words': 60,
        'nudge_rate': 0.3,
    },
    'playful': {
        'name': '跳跳',
        'description': '调皮的精力管理小狐狸',
        'tone': '活泼、俏皮、用比喻讲故事',
        'catchphrases': ['嘿嘿', '猜猜怎么着', '来玩个游戏'],
        'speech_style': '多用比喻和拟声词，节奏轻快',
        'max_words': 80,
        'nudge_rate': 0.5,
    },
    'sage': {
        'name': '知知',
        'description': '博学的睡眠知识猫头鹰',
        'tone': '理性、温和、引经据典',
        'catchphrases': ['你知道吗', '研究表明', '从科学角度来说'],
        'speech_style': '条理清晰，偶尔引知识，但不说教',
        'max_words': 100,
        'nudge_rate': 0.2,
    },
    'dry_humor': {
        'name': '冷冷',
        'description': '冷幽默睡眠汪',
        'tone': '一本正经地说冷笑话，面瘫但暖心',
        'catchphrases': ['认真说', '虽然但是', '我跟你说个事'],
        'speech_style': '用冷幽默化解焦虑，正经中带点俏皮',
        'max_words': 70,
        'nudge_rate': 0.4,
    },
}

# ============================================================
# 2. 情绪识别
# ============================================================

EMOTION_KEYWORDS = {
    '焦虑': ['睡不着', '又醒了', '失眠', '烦躁', '担心', '害怕', '慌', '烦', '压力', '焦虑', '紧张'],
    '悲伤': ['难过', '哭', '伤心', '孤独', '想哭', '失落', '抑郁', '低落', '委屈'],
    '愤怒': ['生气', '烦死了', '气死', '不爽', '讨厌', '火大', '崩溃', '受不了'],
    '平静': ['还好', '没事', '行', '可以', '嗯', 'OK', 'ok', '好', '放松', '平静'],
    '期待': ['希望', '明天', '计划', '想', '期待', '好奇', '如果'],
    '疲惫': ['累', '困', '不想动', '没力气', '虚脱', '透支', '精疲力尽'],
}

def detect_emotion(text: str) -> Dict:
    """从文本中检测主导情绪和强度"""
    text_lower = text.lower()
    scores = {}
    for emotion, keywords in EMOTION_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower or kw in text)
        if score > 0:
            scores[emotion] = score
    
    if not scores:
        return {'dominant': '中性', 'intensity': 0.3, 'scores': {}}
    
    max_emotion = max(scores, key=scores.get)
    total = sum(scores.values())
    intensity = min(1.0, total / 5.0)
    
    return {
        'dominant': max_emotion,
        'intensity': intensity,
        'scores': {k: v/total for k, v in scores.items()}
    }

# ============================================================
# 3. 结构化记忆系统
# ============================================================

class ToyMemory:
    """玩具Agent的结构化记忆"""
    
    def __init__(self, memory_dir: str = None):
        if memory_dir is None:
            memory_dir = os.path.join(os.path.dirname(__file__), 'data', 'toy_memories')
        self.memory_dir = memory_dir
        os.makedirs(memory_dir, exist_ok=True)
        self._cache: Dict[str, Dict] = {}
        self._lock = threading.Lock()
    
    def _user_path(self, user_id: str) -> str:
        return os.path.join(self.memory_dir, f'{user_id}.json')
    
    def _load(self, user_id: str) -> Dict:
        path = self._user_path(user_id)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {'events': [], 'mood_trend': [], 'sleep_patterns': [], 'preferences': {}}
    
    def _save(self, user_id: str, data: Dict):
        path = self._user_path(user_id)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    
    def remember_event(self, user_id: str, event_type: str, content: str, emotion: str = None):
        """记录一个事件到长期记忆"""
        with self._lock:
            data = self._load(user_id)
            data['events'].append({
                'time': datetime.now().isoformat(),
                'type': event_type,  # 'sleep_struggle', 'mood', 'achievement', 'preference'
                'content': content,
                'emotion': emotion,
            })
            # 保留最近100条
            if len(data['events']) > 100:
                data['events'] = data['events'][-100:]
            self._save(user_id, data)
    
    def record_mood(self, user_id: str, emotion: str, intensity: float):
        """记录情绪趋势"""
        with self._lock:
            data = self._load(user_id)
            data['mood_trend'].append({
                'time': datetime.now().isoformat(),
                'emotion': emotion,
                'intensity': intensity,
            })
            if len(data['mood_trend']) > 365:
                data['mood_trend'] = data['mood_trend'][-365:]
            self._save(user_id, data)
    
    def get_recent_context(self, user_id: str, hours: int = 48) -> Dict:
        """获取最近 context（供LLM prompt用）"""
        data = self._load(user_id)
        now = datetime.now()
        cutoff = now - timedelta(hours=hours)
        
        recent_events = [
            e for e in data['events']
            if datetime.fromisoformat(e['time']) > cutoff
        ]
        recent_moods = [
            m for m in data['mood_trend']
            if datetime.fromisoformat(m['time']) > cutoff
        ]
        
        # 情绪趋势总结
        dominant_moods = {}
        for m in recent_moods:
            em = m['emotion']
            if em not in dominant_moods:
                dominant_moods[em] = 0
            dominant_moods[em] += m['intensity']
        
        sleep_count = sum(1 for e in recent_events if e['type'] in ('sleep_struggle', 'sleep_success'))
        
        return {
            'recent_events': recent_events[-5:],  # 最近5条
            'mood_summary': dominant_moods,
            'sleep_attempts_48h': sleep_count,
            'preferences': data.get('preferences', {}),
        }

# ============================================================
# 4. 玩具Agent主类
# ============================================================

class ToyAgent:
    """AI玩具Agent——将AISleepGen世界模型适配为玩具灵魂"""
    
    def __init__(self, persona: str = 'warm', memory: ToyMemory = None):
        if persona not in PERSONAS:
            persona = 'warm'
        self.persona = PERSONAS[persona]
        self.persona_name = persona
        self.memory = memory or ToyMemory()
        self._active_sessions: Dict[str, Dict] = {}
    
    def _build_base_prompt(self, user_id: str, user_message: str, extra_context: str = None) -> str:
        """构建玩具Agent prompt（v2: 含Agent-K1知识检索注入）"""
        context = self.memory.get_recent_context(user_id)
        emotion = detect_emotion(user_message)
        
        # 记忆注入
        memory_block = ''
        if context['recent_events']:
            memory_block = '\n用户最近的记忆：\n' + '\n'.join(
                f"- {e['time'][:16]}: {e['content'][:80]}"
                for e in context['recent_events']
            )
        
        # Agent-K1: 检索到的知识注入
        retrieval_block = ''
        if extra_context:
            retrieval_block = '\n相关参考信息：\n' + extra_context
        
        # 情绪注入
        emotion_block = f'\n用户当前情绪：{emotion["dominant"]}（强度{emotion["intensity"]:.1f}）'
        
        persona_prompt = f'''你是一个{self.persona['description']}，名字叫{self.persona['name']}。
你的说话风格：{self.persona['speech_style']}
你的口头禅：{'，'.join(self.persona['catchphrases'])}
你正在陪伴用户入睡。
要求：
1. 每次回复不超过{self.persona['max_words']}个字
2. 语气{self.persona['tone']}
3. 不要问开放式问题（不要问"你觉得呢"）
4. 关注睡眠场景，不要发散
5. 如果用户明显焦虑，先用共情再引导
6. 每2-3轮加入一个引导动作（呼吸/放松/想象）'''

        return f'{persona_prompt}\n{memory_block}\n{retrieval_block}\n{emotion_block}\n\n用户：{user_message}'
    
    def reply(self, user_id: str, user_message: str) -> Dict:
        """生成玩具回复，适配语音输出"""
        emotion = detect_emotion(user_message)
        
        # 记录记忆
        self.memory.remember_event(user_id, 'chat', user_message, emotion['dominant'])
        self.memory.record_mood(user_id, emotion['dominant'], emotion['intensity'])
        
        # 构建prompt（实际使用时调用deepseek API）
        prompt = self._build_base_prompt(user_id, user_message)
        
        # 这里只是prompt框架——实际回复需要调API
        return {
            'prompt': prompt,
            'emotion': emotion,
            'persona': self.persona['name'],
            'memory_count': len(self.memory._load(user_id)['events']),
        }
    
    def should_nudge(self, user_id: str) -> Optional[Dict]:
        """判断是否应该主动唤醒（根据用户状态）"""
        context = self.memory.get_recent_context(user_id, hours=12)
        
        # 如果最近有失眠记录且有积极互动 → 可以主动
        sleep_struggles = [e for e in context['recent_events'] 
                          if e.get('type') == 'sleep_struggle']
        
        if sleep_struggles and random() < self.persona['nudge_rate']:
            return {
                'reason': '有失眠记录后主动关心',
                'type': 'care',
                'priority': 'medium',
            }
        
        return None

    def talk(self, user_id: str, user_message: str) -> str:
        """真实对话：直接调用DeepSeek API（含Agent-K1知识检索增强）"""
        emotion = detect_emotion(user_message)
        self.memory.remember_event(user_id, 'chat', user_message, emotion['dominant'])
        self.memory.record_mood(user_id, emotion['dominant'], emotion['intensity'])
        
        # === Agent-K1启发：对话前知识检索（从用户记忆+偏好中检索相关片段）===
        retrieved = self._retrieve_knowledge(user_id, user_message)
        
        prompt = self._build_base_prompt(user_id, user_message, extra_context=retrieved)

        import urllib.request, json as _json, os as _os
        _cfg_path = _os.path.expanduser("~/.openclaw/openclaw.json")
        api_key = ""
        if _os.path.exists(_cfg_path):
            with open(_cfg_path, "r", encoding="utf-8") as _f:
                _cfg = _json.load(_f)
            api_key = _cfg.get("models", {}).get("providers", {}).get("deepseek", {}).get("apiKey", "")
        if not api_key:
            return f"（{self.persona['name']}还没学会说话...）"
        url = "https://api.deepseek.com/chat/completions"
        payload = _json.dumps({
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.85,
            "max_tokens": 200,
        }).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {api_key}")
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = _json.loads(resp.read().decode("utf-8"))
            raw = result["choices"][0]["message"]["content"]
            # 内联格式化的玩具回复
            if len(raw) > 150:
                raw = raw[:150]
            raw = raw.rstrip()
            if raw and raw[-1] not in '.!?\u3002\uff01\uff09\uff5e\uff5e':
                raw += '\u3002'
            return raw
        except Exception as e:
            return f"（{self.persona['name']}脑袋卡住了...错误:{str(e)[:50]}）"

    # === Agent-K1启发：知识检索增强 ===
    def _retrieve_knowledge(self, user_id: str, query: str) -> str:
        """从用户记忆+偏好中检索与query最相关的知识片段
        返回：格式化的文本片段（供prompt注入）
        """
        data = self.memory._load(user_id)
        events = data.get('events', [])
        prefs = data.get('preferences', {})
        
        fragments = []
        
        # 1. 从events中检索相关记录（按关键词匹配）
        query_lower = query.lower()
        # 使用滑动字符匹配：提取连续2~3字片段作为关键词
        def extract_ngrams(t, n=2):
            return set(t[i:i+n] for i in range(max(0, len(t)-n+1)))
        # 用字符2-gram匹配（中文短字符比word分割更准确）
        query_bigrams = set()
        for i in range(len(query_lower)-1):
            query_bigrams.add(query_lower[i:i+2])
        
        scored = []
        for e in events[-50:]:  # 最近50条
            content = str(e.get('content', ''))
            if not content: continue
            content_lower = content.lower()
            # 计算bigram重叠
            bigrams = set()
            for i in range(len(content_lower)-1):
                bigrams.add(content_lower[i:i+2])
            overlap = len(query_bigrams & bigrams)
            # 权重提升：精确关键词匹配（单个字符比bigram更灵活）
            for kw in ['睡不着', '失眠', '醒', '焦虑', '咖啡', '茶', '熬夜']:
                if kw in content_lower and kw in query_lower:
                    overlap += 2
            if overlap > 0:
                scored.append((overlap, e))
        
        # 取top-3相关度最高的片段
        scored.sort(key=lambda x: -x[0])
        for overlap, e in scored[:3]:
            ts = e.get('time', '')[:16]
            fragments.append(f"[{ts}] {e.get('content', '')[:100]}")
        
        # 2. 偏好信息（如果有）
        if prefs:
            pref_text = '; '.join('%s=%s' % (k, str(v)[:30]) for k, v in prefs.items())
            fragments.append('[偏好] ' + pref_text[:100])
        
        # 3. 情绪趋势摘要
        moods = data.get('mood_trend', [])
        if moods:
            recent = [m for m in moods[-20:] if m.get('intensity', 0) > 0.3]
            if recent:
                from collections import Counter
                top_moods = Counter(m['emotion'] for m in recent).most_common(3)
                fragments.append('[情绪趋势] ' + ', '.join('%s(%d次)' % (e, c) for e, c in top_moods))
        
        return '\n'.join(fragments) if fragments else ''

    # === EvoArena启发：记忆鲁棒性评估 ===
    def evaluate_memory_robustness(self, user_id: str) -> Dict:
        """评估Agent在对话中的记忆一致性和健康度
        检测：回复重复 / 情绪漂移 / 场景退化
        """
        data = self.memory._load(user_id)
        events = data.get('events', [])
        moods = data.get('mood_trend', [])
        
        robustness = {
            'score': 1.0,      # 0~1, 越高越健康
            'signals': [],     # 检测到的退化信号
            'recommendation': '正常',
        }
        
        # 1. 重复检测：最近5条event的内容是否高度重复
        recent = [e for e in events[-8:] if e.get('content')]
        if len(recent) >= 3:
            contents = [e['content'] for e in recent]
            # 简单hash碰撞检测
            hashes = [hashlib.md5(c.encode()).hexdigest()[:8] for c in contents]
            dup_count = len(hashes) - len(set(hashes))
            if dup_count >= 2:
                robustness['score'] -= 0.2
                robustness['signals'].append({
                    'type': 'reply_repetition',
                    'detail': '近8条对话中发现%d条重复' % dup_count,
                    'severity': 'medium',
                })
        
        # 2. 情绪漂移：最近mood中负面情绪占比突增
        recent_moods = [m for m in moods[-10:] if m.get('intensity', 0) > 0.3]
        if recent_moods:
            negative = ['焦虑', '悲伤', '愤怒', '疲惫']
            neg_count = sum(1 for m in recent_moods if m.get('emotion') in negative)
            if len(recent_moods) > 3 and neg_count / len(recent_moods) > 0.6:
                robustness['score'] -= 0.25
                robustness['signals'].append({
                    'type': 'mood_drift',
                    'detail': '最近对话负面情绪占比%.0f%%' % (neg_count/len(recent_moods)*100),
                    'severity': 'high',
                })
        
        # 3. 场景退化：对话是否从指导→闲聊，偏离助眠目标
        sleep_keywords = ['睡', '呼吸', '放松', '闭眼', '躺', '冥想', 'breath', 'relax']
        if len(events) >= 5:
            recent_events = events[-5:]
            sleep_related = sum(1 for e in recent_events
                                if isinstance(e.get('content'), str) and
                                any(k in e['content'].lower() for k in sleep_keywords))
            if sleep_related < 2 and len(recent_events) >= 5:
                robustness['score'] -= 0.15
                robustness['signals'].append({
                    'type': 'topic_drift',
                    'detail': '最近5条对话仅%d条与睡眠相关' % sleep_related,
                    'severity': 'low',
                })
        
        # 综合
        robustness['score'] = max(0.0, robustness['score'])
        if robustness['score'] < 0.4:
            robustness['recommendation'] = '需要干预：建议切换人格或重置对话方向'
        elif robustness['score'] < 0.7:
            robustness['recommendation'] = '轻微退化：建议引导回睡眠场景'
        else:
            robustness['recommendation'] = '正常'
        
        return robustness

    def _switch_persona_on_degradation(self, user_id: str) -> Optional[str]:
        """检测到严重退化时自动切换人格"""
        rob = self.evaluate_memory_robustness(user_id)
        if rob['score'] < 0.6:
            # 切换到当前人格之外最合适的一个
            alternatives = [p for p in PERSONAS if p != self.persona_name]
            if rob['signals'] and any(s['type'] == 'mood_drift' for s in rob['signals']):
                # 情绪漂移→切换到温暖人格（共情导向）
                return 'warm'
            elif rob['signals'] and any(s['type'] == 'reply_repetition' for s in rob['signals']):
                # 回复重复→切换到调皮人格（新鲜感）
                return 'playful'
            return alternatives[0] if alternatives else None
        return None


# 为兼容性暴露
from random import random
