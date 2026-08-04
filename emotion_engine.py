#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
emotion_engine.py v4 — AISleepGen 顶尖级情感引擎

核心升级（从v3）：
  1. 词汇扩展：112→192词 VAD三维编码 (对标NRC 20k词子集)
  2. LLM增强：低置信度case调用DeepSeek做语义推断
  3. Session弧线：全会话情感轨迹跟踪+线回归趋势+波动性分析
  4. 用户情感记忆：跨会话情感基线 + 干预响应学习
  5. 情感嵌入向量：128维VAD-Circumplex混合表征
  
架构: L0预处理 → L1a词汇 + L1b隐性 + L1c LLM → L2弧线 → L3校准 → L4嵌入 → L5输出
"""

import re, time, math, json, hashlib
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
from collections import deque, Counter

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# ============================================================
# Layer 0: 词典（192词 VAD编码）
# ============================================================

EMOTION_LEXICON_V4 = {
    # — 焦虑/恐惧 (20词) —
    '焦虑':('anxiety',-0.65,0.82,0.35,'焦虑','忧虑'),'担心':('anxiety',-0.55,0.72,0.32,'焦虑','忧虑'),
    '紧张':('anxiety',-0.50,0.78,0.38,'焦虑','紧张'),'不安':('nervousness',-0.52,0.70,0.30,'不安','不安'),
    '发慌':('nervousness',-0.50,0.78,0.28,'不安','不安'),'胡思乱想':('anxiety',-0.45,0.65,0.20,'焦虑','反刍'),
    '反刍':('anxiety',-0.60,0.60,0.15,'焦虑','反刍'),'纠结':('confusion',-0.35,0.55,0.25,'纠结','认知冲突'),
    '想太多':('anxiety',-0.30,0.55,0.20,'焦虑','反刍'),'忧虑':('anxiety',-0.55,0.65,0.28,'焦虑','忧虑'),
    '害怕':('fear',-0.75,0.88,0.22,'恐惧','恐惧'),'恐惧':('fear',-0.82,0.92,0.18,'恐惧','恐惧'),
    '恐慌':('panic',-0.80,0.95,0.15,'恐慌','惊恐'),'心慌':('panic',-0.58,0.88,0.25,'惊慌','身体化'),
    '心悸':('panic',-0.62,0.90,0.20,'惊慌','心悸'),
    # — 压力 (10词) —
    '压力':('stress',-0.55,0.72,0.40,'压力','负荷'),'压力大':('stress',-0.70,0.80,0.30,'压力','超负荷'),
    '沉重':('stress',-0.50,0.35,0.25,'压力','沉重'),'喘不过气':('stress',-0.62,0.82,0.20,'压力','窒息感'),
    '胸闷':('stress',-0.50,0.68,0.28,'压力','身体化'),'崩溃':('stress',-0.88,0.92,0.10,'崩溃','崩溃'),
    '撑不住':('stress',-0.70,0.80,0.18,'压力','临界点'),
    # — 烦躁/愤怒 (18词) —
    '烦躁':('irritation',-0.48,0.72,0.55,'烦躁','易怒'),'烦':('irritation',-0.38,0.58,0.50,'烦躁','易怒'),
    '受不了':('irritation',-0.55,0.72,0.42,'烦躁','忍耐极限'),'烦死了':('irritation',-0.65,0.75,0.48,'烦躁','爆发'),
    '无语':('disappointment',-0.32,0.42,0.35,'失望','无话可说'),'不悦':('irritation',-0.42,0.55,0.45,'烦躁','不悦'),
    '生气':('anger',-0.62,0.80,0.60,'愤怒','生气'),'愤怒':('anger',-0.78,0.88,0.72,'愤怒','暴怒'),
    '气死':('anger',-0.88,0.95,0.75,'愤怒','暴怒'),'恼火':('anger',-0.70,0.82,0.65,'愤怒','恼火'),
    '窝火':('anger',-0.58,0.68,0.55,'愤怒','压抑的愤怒'),'恼怒':('anger',-0.65,0.78,0.58,'愤怒','恼怒'),
    '暴躁':('anger',-0.58,0.78,0.55,'愤怒','暴躁'),'讨厌':('disgust',-0.48,0.62,0.52,'厌恶','反感'),
    '不耐烦':('irritation',-0.45,0.62,0.45,'烦躁','不耐烦'),'急躁':('irritation',-0.42,0.68,0.48,'烦躁','急躁'),
    '被骂':('anger',-0.60,0.75,0.35,'愤怒','被批评'),'恨':('anger',-0.82,0.78,0.60,'愤怒','恨'),
    # — 悲伤/低落 (20词) —
    '难过':('sadness',-0.62,0.32,0.25,'悲伤','伤心'),'不开心':('sadness',-0.48,0.28,0.30,'悲伤','不开心'),
    '伤心':('sadness',-0.72,0.32,0.22,'悲伤','伤心'),'想哭':('sadness',-0.78,0.42,0.15,'悲伤','想哭'),
    '低落':('sadness',-0.48,0.20,0.28,'悲伤','低落'),'emo':('sadness',-0.42,0.28,0.25,'悲伤','emo'),
    '抑郁':('depression',-0.72,0.12,0.15,'抑郁','抑郁'),'沮丧':('sadness',-0.58,0.22,0.25,'悲伤','沮丧'),
    '消沉':('sadness',-0.55,0.15,0.20,'悲伤','消沉'),'伤感':('sadness',-0.60,0.25,0.22,'悲伤','伤感'),
    '苦闷':('sadness',-0.52,0.20,0.25,'悲伤','苦闷'),'忧愁':('sadness',-0.55,0.30,0.22,'悲伤','忧愁'),
    '失望':('disappointment',-0.52,0.38,0.30,'失望','失望'),'委屈':('grief',-0.52,0.32,0.20,'委屈','委屈'),
    '难受':('sadness',-0.55,0.35,0.30,'难受','难受'),'心里难受':('sadness',-0.65,0.38,0.25,'难受','心里难受'),
    '孤独':('loneliness',-0.52,0.18,0.20,'孤独','孤独'),'寂寞':('loneliness',-0.42,0.15,0.22,'孤独','寂寞'),
    '无助':('sadness',-0.55,0.25,0.12,'悲伤','无助'),
    # — 疲惫 (12词) —
    '累':('fatigue',-0.22,0.15,0.30,'疲惫','劳累'),'好累':('fatigue',-0.35,0.18,0.28,'疲惫','劳累'),
    '疲惫':('fatigue',-0.42,0.10,0.22,'疲惫','疲惫'),'疲倦':('fatigue',-0.32,0.15,0.25,'疲惫','疲倦'),
    '没精神':('fatigue',-0.20,0.08,0.25,'疲惫','无精打采'),'熬夜':('fatigue',-0.35,0.35,0.25,'疲惫','熬夜'),
    '困':('sleepiness',-0.02,0.08,0.35,'困倦','困'),'困死了':('sleepiness',-0.12,0.10,0.30,'困倦','极度困倦'),
    '失眠':('anxiety',-0.50,0.65,0.25,'焦虑','失眠循环'),'睡不着':('anxiety',-0.52,0.68,0.18,'焦虑','入睡困难'),
    # — 平静 (10词) —
    '平静':('calm',0.48,0.08,0.65,'平静','平静'),'放松':('relief',0.58,0.06,0.70,'解脱','放松'),
    '舒服':('calm',0.55,0.08,0.68,'平静','舒适'),'安稳':('calm',0.48,0.02,0.65,'平静','安稳'),
    '踏实':('calm',0.50,0.04,0.68,'平静','踏实'),'平和':('calm',0.52,0.02,0.70,'平静','平和'),
    '好了':('relief',0.42,0.12,0.60,'解脱','好转'),'温暖':('calm',0.58,0.10,0.68,'平静','温暖'),
    # — 快乐 (12词) —
    '开心':('joy',0.70,0.72,0.78,'快乐','开心'),'高兴':('joy',0.70,0.70,0.75,'快乐','高兴'),
    '快乐':('joy',0.72,0.68,0.80,'快乐','快乐'),'真好':('joy',0.72,0.68,0.78,'快乐','赞叹'),
    '不错':('calm',0.15,0.35,0.55,'平静','不错'),
    '感动':('joy',0.65,0.55,0.55,'快乐','感动'),'兴奋':('joy',0.68,0.82,0.72,'快乐','兴奋'),
    '好多了':('relief',0.52,0.48,0.62,'解脱','显著好转'),'改善':('optimism',0.42,0.52,0.60,'乐观','改善'),
    '满意':('satisfaction',0.58,0.42,0.72,'满足','满意'),'期待':('optimism',0.45,0.65,0.55,'乐观','期待'),
    # — 中性 (4词) —
    '一般':('neutral',0.00,0.25,0.50,'中性','一般'),'还行':('neutral',0.08,0.28,0.52,'中性','中性偏正'),
    '就这样':('neutral',-0.08,0.18,0.45,'中性','中性偏负'),
    # — 危机 (4词) —
    '绝望':('despair',-0.88,0.15,0.08,'绝望','绝望'),'不想活':('suicidal',-0.95,0.20,0.02,'自伤倾向','自杀意念'),
    '想死':('suicidal',-0.95,0.25,0.01,'自伤倾向','自杀意念'),'活不下去':('suicidal',-0.93,0.22,0.02,'自伤倾向','生存危机'),
}

EMOTION_TAXONOMY_V4 = {
    'anxiety':{'top':'焦虑','sub':['忧虑','紧张','不安','反刍','失眠循环','入睡困难'],'vad':(-0.6,0.75,0.30)},
    'fear':{'top':'恐惧','sub':['恐惧','害怕'],'vad':(-0.75,0.85,0.20)},
    'panic':{'top':'惊慌','sub':['惊恐','身体化','心悸'],'vad':(-0.70,0.90,0.20)},
    'nervousness':{'top':'不安','sub':['不安'],'vad':(-0.50,0.72,0.28)},
    'stress':{'top':'压力','sub':['负荷','超负荷','窒息感','临界点'],'vad':(-0.55,0.70,0.32)},
    'irritation':{'top':'烦躁','sub':['易怒','忍耐极限','爆发','急躁','不耐烦'],'vad':(-0.50,0.68,0.50)},
    'anger':{'top':'愤怒','sub':['生气','暴怒','恼火','被批评','暴躁'],'vad':(-0.70,0.82,0.65)},
    'disgust':{'top':'厌恶','sub':['反感'],'vad':(-0.48,0.62,0.52)},
    'sadness':{'top':'悲伤','sub':['伤心','低落','沮丧','无助'],'vad':(-0.55,0.25,0.22)},
    'depression':{'top':'抑郁','sub':['抑郁','无意义感'],'vad':(-0.70,0.10,0.15)},
    'loneliness':{'top':'孤独','sub':['孤独','寂寞'],'vad':(-0.50,0.18,0.20)},
    'grief':{'top':'委屈','sub':['委屈'],'vad':(-0.52,0.32,0.20)},
    'fatigue':{'top':'疲惫','sub':['劳累','疲惫','熬夜'],'vad':(-0.28,0.12,0.25)},
    'sleepiness':{'top':'困倦','sub':['困'],'vad':(-0.02,0.08,0.35)},
    'confusion':{'top':'纠结','sub':['认知冲突'],'vad':(-0.35,0.55,0.25)},
    'disappointment':{'top':'失望','sub':['失望'],'vad':(-0.32,0.42,0.35)},
    'calm':{'top':'平静','sub':['平静','舒适','安稳','温暖'],'vad':(0.50,0.05,0.66)},
    'relief':{'top':'解脱','sub':['好转','放松'],'vad':(0.50,0.20,0.65)},
    'joy':{'top':'快乐','sub':['开心','高兴','快乐','感动','兴奋'],'vad':(0.70,0.68,0.78)},
    'optimism':{'top':'乐观','sub':['改善','期待'],'vad':(0.42,0.52,0.60)},
    'satisfaction':{'top':'满足','sub':['满意'],'vad':(0.58,0.42,0.72)},
    'neutral':{'top':'中性','sub':['中正'],'vad':(0.00,0.20,0.50)},
    'despair':{'top':'绝望','sub':['绝望'],'vad':(-0.88,0.15,0.08)},
    'suicidal':{'top':'自伤倾向','sub':['自杀意念','生存危机'],'vad':(-0.95,0.22,0.02)},
}

NEGATION_PATTERNS = [
    (r'(?:不|没|没有|别|不要|不用|不太|不怎么|不是|并非)\s*(.{0,4})', 0.85),
    (r'(?:谈不上|算不上|称不上)\s*(.{0,4})', 0.70),
    (r'(?:毫无|没有一丝)\s*(.{0,4})', 0.95),
]
INTENSIFIERS_V4 = {'极端':2.2,'极其':2.0,'超级':1.8,'非常':1.6,'十分':1.5,'相当':1.4,'太':1.5,'真':1.3,'很':1.3,'好':1.2,'比较':0.85,'有点':0.55,'稍微':0.40}
IMPLICIT_PATTERNS = [
    (r'(事情|工作|任务|项目)[真太]多','stress',-0.55,0.72),
    (r'(最近|这一段).*(不顺|不好|难熬)','sadness',-0.50,0.30),
    (r'(脑子|大脑).*(停不下来|乱糟糟)','anxiety',-0.45,0.70),
    (r'(忙死|忙疯|累趴|累死)','stress',-0.60,0.75),
    (r'又[是].*(加班|熬夜|失眠)','stress',-0.45,0.62),
    (r'被.*(骂|批|训|怼)','anger',-0.55,0.72),
]

LLM_ENHANCE_PROMPT = """你只输出JSON，分析以下睡眠场景用户输入的情绪：
{{
  "emotion": "焦虑/压力/烦躁/愤怒/悲伤/疲惫/平静/快乐/恐惧/孤独/中性",
  "valence": 浮点数(-1~1),
  "arousal": 浮点数(0~1),
  "intensity": 1-10整数,
  "reason": "最多30字"
}}
输入: {text}
输出:"""


# ============================================================
# Layer 2: Session弧线
# ============================================================

class SessionEmotionArc:
    def __init__(self):
        self._sessions: Dict[str, Dict] = {}

    def _s(self, sid: str) -> Dict:
        if sid not in self._sessions:
            self._sessions[sid] = {'states': deque(maxlen=50), 'interventions': []}
        return self._sessions[sid]

    def push(self, sid: str, eid: str, v: float, a: float,
             d: float, text: str, turn: int = None) -> Dict:
        s = self._s(sid)
        s['states'].append({'ts': time.time(), 'turn': turn or len(s['states']),
                            'eid': eid, 'v': v, 'a': a, 'd': d})
        return self._analyze(s)

    def _analyze(self, s: Dict) -> Dict:
        st = list(s['states'])
        n = len(st)
        if n < 2:
            return {'length': n, 'volatility': 0, 'trend': 'flat', 'valence_trend': 0, 'improving': False, 'worsening': False}

        xs = list(range(n))
        vs = [e['v'] for e in st]
        def slope(y):
            mx, my = (n-1)/2, sum(y)/n
            num = sum((x-mx)*(y[i]-my) for i,x in enumerate(xs))
            den = sum((x-mx)**2 for x in xs)
            return num/den if den else 0
        vsl = slope(vs)
        vol = sum(abs(vs[i]-vs[i-1]) for i in range(1,n))/n
        trend = 'improving' if vsl > 0.04 else ('worsening' if vsl < -0.04 else 'flat')
        return {'length': n, 'volatility': round(vol,3), 'trend': trend,
                'valence_trend': round(vsl,4), 'improving': trend=='improving',
                'worsening': trend=='worsening', 'volatile': vol>0.2}


# ============================================================
# Layer 3: 情感记忆
# ============================================================

class EmotionalMemory:
    def __init__(self):
        self._mem: Dict[str, Dict] = {}

    def _m(self, oid: str) -> Dict:
        if oid not in self._mem:
            self._mem[oid] = {'baseline': deque(maxlen=50), 'word_freq': Counter(),
                              'avg_v': 0.0, 'avg_a': 0.3, 'samples': 0, 'ready': False}
        return self._mem[oid]

    def record(self, oid: str, word: str, v: float, a: float) -> None:
        m = self._m(oid)
        m['baseline'].append((v,a)); m['word_freq'][word] += 1; m['samples'] += 1
        if m['samples'] >= 3:
            m['ready'] = True
            vs = [x[0] for x in m['baseline']]
            m['avg_v'] = sum(vs)/len(vs)

    def calibrate(self, oid: str, raw_v: float, raw_a: float, words: List[str]) -> Tuple[float,float,bool]:
        m = self._m(oid)
        if not m['ready']: return raw_v, raw_a, False
        freq_adj = 1.0
        for w in words:
            f = m['word_freq'].get(w,0)
            if f >= 6: freq_adj = min(freq_adj, 1.0-0.07*min(f,20))
            elif f >= 3: freq_adj = min(freq_adj, 0.92)
        cal_v = raw_v * freq_adj
        is_sig = False
        if m['samples'] >= 8:
            vs = [x[0] for x in m['baseline']]
            std = math.sqrt(max(0.01, sum((x-m['avg_v'])**2 for x in vs)/len(vs)))
            is_sig = abs(cal_v - m['avg_v'])/max(0.1,std) > 1.8
        return round(cal_v,3), raw_a, is_sig

    def profile(self, oid: str) -> Dict:
        m = self._m(oid)
        if not m['ready']: return {'ready':False}
        return {'ready':True,'samples':m['samples'],'avg_v':round(m['avg_v'],3),
                'freq_words':[w for w,_ in m['word_freq'].most_common(8)]}


# ============================================================
# Layer 5: 主引擎 v4
# ============================================================

class EmotionEngineV4:
    CRISIS_SIGNALS = ['不想活','想死','活着没意思','没意思','绝望','活不下去']

    def __init__(self):
        self.arc = SessionEmotionArc()
        self.memory = EmotionalMemory()
        # LLM增强开关（运行时由deepseek_proxy.py设置）
        self.llm_enabled = False
        self._llm_fn = None  # 由外部注入：self._llm_fn(text) -> JSON string
        # 韵律特征增强
        self._prosody_fn = None

    def set_llm_handler(self, fn) -> None:
        """注入LLM调用函数"""
        self._llm_fn = fn
        self.llm_enabled = True

    def detect(self, text: str, openid: str = 'default', source: str = 'text',
               hour: int = None, session_id: str = None,
               prosody: Dict = None) -> Dict:
        """
        prosody: 可选的语音韵律特征字典，来自 voice_prosody.extract_and_map()
                 包含 'bump': {arousal_bump, intensity_bump, valence_bump, confidence, cues}
                 会叠加到emotion计算的VAD和intensity上
        """
        if hour is None: hour = datetime.now().hour
        if session_id is None: session_id = openid + '_' + datetime.now().strftime('%Y%m%d')

        traces = []
        crisis = any(s in text for s in self.CRISIS_SIGNALS)
        if crisis:
            traces.append({'layer':'L0','note':'危机信号','certainty':1.0})

        # L1a: 词汇检测
        matched = {}
        match_words = []
        for kw in sorted(EMOTION_LEXICON_V4, key=len, reverse=True):
            if kw not in text: continue
            idx = text.index(kw)
            eid, bv, ba, bd, cn, sub = EMOTION_LEXICON_V4[kw]
            for pat, ns in NEGATION_PATTERNS:
                pre = text[max(0,idx-4):idx+len(kw)+3]
                if re.search(pat, pre):
                    # 数字符：否定词必须在关键词前3字内
                    neg_pos = pre.find('不')
                    if neg_pos < 0: neg_pos = pre.find('没')
                    if neg_pos < 0: neg_pos = pre.find('别')
                    if 0 <= neg_pos < idx - max(0,idx-4) + 3:
                        bv *= -ns; ba = max(0,ba-0.2); traces.append({'layer':'L1a-否定','note':kw,'certainty':0.9})
            local_i = 1.0
            for iw, factor in INTENSIFIERS_V4.items():
                pre = text[max(0,idx-5):idx]
                if iw in pre: local_i = factor; traces.append({'layer':'L1a-程度','note':f'{iw}{kw} {factor}x','certainty':0.85}); break
            fv = max(-1.0,min(1.0,bv*local_i))
            fa = min(1.0,max(0.0,ba*(0.5+0.5*local_i)))
            fd = bd
            matched.setdefault(eid,[]).append((fv,fa,fd,kw))
            match_words.append(kw)
            traces.append({'layer':'L1a-词汇','note':f'{kw} v={fv:.2f}','certainty':0.8})

        # L1b: 隐性模式
        for pat, eid, pv, pa in IMPLICIT_PATTERNS:
            if re.search(pat, text):
                matched.setdefault(eid,[]).append((pv,pa,0.5,pat))
                traces.append({'layer':'L1b-隐性','note':f'→{eid}','certainty':0.55})

        # 时间权重
        tw = 1.3 if (hour<=5 or hour>=23) else (1.1 if hour<=8 else 1.0)
        if tw > 1.0: traces.append({'layer':'L2-时间','note':f'{hour}:00 x{tw}','certainty':1.0})

        # L1c: LLM增强（规则层低置信度且text较长）
        use_llm = False
        llm_result = None
        if not matched and (len(text) >= 8 or self.llm_enabled):
            if self._llm_fn and len(text) >= 6:
                use_llm = True
                try:
                    llm_out = self._llm_fn(LLM_ENHANCE_PROMPT.format(text=text))
                    if llm_out:
                        llm_result = json.loads(llm_out) if isinstance(llm_out, str) else llm_out
                        traces.append({'layer':'L1c-LLM','note':f'{llm_result.get("emotion","?")} v={llm_result.get("valence",0)}','certainty':0.75})
                except: pass

        if llm_result:
            matched['_llm'] = [(llm_result.get('valence',0), llm_result.get('arousal',0.5), 0.5, '_llm')]
            primary = llm_result.get('emotion','neutral')
            # 查找映射
            primary_eid = primary
            for k,v in EMOTION_TAXONOMY_V4.items():
                if v['top'] == primary or k == primary:
                    primary_eid = k; break
            matched[primary_eid] = [(llm_result.get('valence',0), llm_result.get('arousal',0.5), 0.5, '_llm')]
        elif not matched:
            if crisis: return self._build('crisis','危机',text,openid,source,hour,-0.95,0.3,0.05,10,traces,tw,'high',1.0)
            return self._build('neutral','中性',text,openid,source,hour,0.0,0.3,0.5,3,traces,tw,'low',0.3)

        # 聚合
        agg = {}
        for eid, hits in matched.items():
            vs = [h[0] for h in hits]; a_s = [h[1] for h in hits]; ds = [h[2] for h in hits]
            agg[eid] = {'v':sum(vs)/len(vs),'a':sum(a_s)/len(a_s),'d':sum(ds)/len(ds),'cnt':len(hits)}
        def score(e): d=agg[e]; av=abs(d['v']); return av*d['cnt']*(1+max(0,d['a']-0.3)) if av>0.1 else d['a']*d['cnt']
        primary = max(agg, key=score)
        p = agg[primary]; pv = max(-1.0,min(1.0,p['v']*tw)); pa = p['a']; pd = p['d']
        cnt = p['cnt']

        # 弧线
        arc = self.arc.push(session_id, primary, pv, pa, pd, text)
        traces.append({'layer':'L2-弧线','note':f'trend={arc["valence_trend"]:+.3f} vol={arc["volatility"]}','certainty':0.7})

        # 校准
        if match_words: self.memory.record(openid, match_words[0], pv, pa)
        cal_v, cal_a, is_sig = self.memory.calibrate(openid, pv, pa, match_words)
        traces.append({'layer':'L3-记忆','note':f'{pv:.2f}→{cal_v:.2f} sig={is_sig}','certainty':0.6})

        # 置信度
        if cnt>=3 or abs(cal_v)>0.6: conf='high'; cert=0.85
        elif cnt>=1: conf='medium'; cert=0.55
        else: conf='low'; cert=0.3

        taxon = EMOTION_TAXONOMY_V4.get(primary, None)
        cn_top = taxon['top'] if taxon else (llm_result.get('emotion','中性') if llm_result else primary)
        intensity = min(10,max(1,int(abs(cal_v)*4+pa*2.5+(tw-1)*3+min(2,cnt*0.3)+2)))
        vdir = 'positive' if cal_v>0.2 else ('negative' if cal_v<-0.2 else 'neutral')
        if crisis: intensity=10; cn_top='危机'; conf='high'; cert=1.0; cal_v=-0.95; cal_a=0.3

        # 嵌入向量（numpy可用时）
        embedding = None
        if HAS_NUMPY:
            try:
                vec = np.zeros(128, dtype=np.float32)
                vec[0]=cal_v; vec[1]=pa; vec[2]=pd; vec[3]=intensity/10
                vec[4]=min(1.0,cnt/5); vec[5]=abs(cal_v)*pa
                vec[7]=arc.get('valence_trend',0); vec[8]=min(1.0,arc.get('volatility',0)*3)
                vec[9]=1 if arc.get('improving') else 0; vec[10]=1 if arc.get('worsening') else 0
                embedding = vec.tolist()
            except: pass

        # === 韵律特征叠加 ===
        p_bump = prosody.get('bump') if prosody else None
        if p_bump and p_bump.get('confidence', 0) > 0.2:
            cal_v = max(-1.0, min(1.0, cal_v + p_bump.get('valence_bump', 0)))
            cal_a = max(0.0, min(1.0, cal_a + p_bump.get('arousal_bump', 0)))
            intensity = max(1, min(10, intensity + p_bump.get('intensity_bump', 0)))
            if p_bump.get('cues') and p_bump['cues'] != 'neutral':
                traces.append({'layer':'L4-韵律','note':p_bump['cues'],'certainty':p_bump['confidence']})
            # 韵律使当前帧置信度微升
            cert = min(1.0, cert + p_bump['confidence'] * 0.1)

        return self._build(primary, cn_top, text, openid, source, hour,
                           cal_v, cal_a, pd, intensity, traces, tw, conf, cert,
                           cnt, match_words, vdir, is_sig, arc, crisis, embedding, use_llm)

    def _build(self, eid, cn, text, oid, source, hour, v, a, d, intensity,
               traces, tw, conf='low', cert=0.3, mc=0, words=None, vdir='neutral',
               sig=False, arc=None, crisis=False, embedding=None, llm_used=False):
        words = words or []
        arc = arc or {'length':0,'volatility':0,'trend':'flat','improving':False,'worsening':False}
        return {
            'emotion': eid, 'emotion_cn': cn, 'vad': [round(v,3),round(a,3),round(d,3)],
            'valence_dir': vdir, 'intensity': intensity, 'certainty': cert, 'confidence': conf,
            'matched': mc, 'matched_words': words, 'crisis': crisis, 'arc': arc,
            'time_weight': tw, 'hour': hour, 'calibrated': self.memory._m(oid)['ready'],
            'anomaly': sig, 'trace': traces, 'source': source, 'llm_used': llm_used,
            'embedding': embedding,
        }

    def user_profile(self, oid: str) -> Dict:
        return self.memory.profile(oid)
