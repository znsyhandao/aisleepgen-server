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
    
    def _build_base_prompt(self, user_id: str, user_message: str) -> str:
        """构建玩具Agent prompt"""
        context = self.memory.get_recent_context(user_id)
        emotion = detect_emotion(user_message)
        
        # 记忆注入
        memory_block = ''
        if context['recent_events']:
            memory_block = '\n用户最近的记忆：\n' + '\n'.join(
                f"- {e['time'][:16]}: {e['content'][:80]}"
                for e in context['recent_events']
            )
        
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

        return f'{persona_prompt}\n{memory_block}\n{emotion_block}\n\n用户：{user_message}'
    
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

# 为兼容性暴露
from random import random
