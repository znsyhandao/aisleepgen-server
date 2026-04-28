"""
偏好学习引擎 v2 — 真·偏好学习
DeepSeek 负责语义理解，Python 负责长期记忆和衰减
"""

import json
import math
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional


# 偏好分类体系（每句话都会归到这些类别之一）
PREFERENCE_CATEGORIES = {
    'relaxation': {
        'name': '放松类方法',
        'examples': ['冥想', '正念', '呼吸法', '白噪音', '轻音乐', '渐进式放松'],
        'alternatives': ['呼吸法', '白噪音', '轻音乐', '渐进式放松']
    },
    'routine': {
        'name': '作息调整',
        'examples': ['固定作息', '定时睡觉', '规律起床', '生物钟调整'],
        'alternatives': ['渐进式作息调整', '光线调节']
    },
    'environment': {
        'name': '环境优化',
        'examples': ['卧室改造', '温度调节', '遮光', '降噪', '床垫枕头'],
        'alternatives': ['温度调节', '遮光窗帘', '白噪音']
    },
    'diet': {
        'name': '饮食调整',
        'examples': ['戒咖啡', '戒茶', '调整晚餐', '控制宵夜', '戒酒'],
        'alternatives': ['调整晚餐时间', '减少咖啡因', '温热牛奶']
    },
    'exercise': {
        'name': '运动辅助',
        'examples': ['跑步', '散步', '瑜伽', '拉伸', '太极', '健身'],
        'alternatives': ['散步', '拉伸', '瑜伽', '太极']
    },
    'cognitive': {
        'name': '认知调整',
        'examples': ['CBT-I', '认知行为', '写日记', '情绪记录', '思维记录'],
        'alternatives': ['写日记', '情绪记录', '感恩练习']
    },
    'medication': {
        'name': '药物/医疗',
        'examples': ['褪黑素', '安眠药', '处方药', '就医', '诊断', '治疗'],
        'alternatives': ['就医评估', '褪黑素短期使用']
    },
}


from preference_storage import PreferenceStorage, PreferenceMerge


class PreferenceMemory:
    """偏好记忆 — 存储和管理用户偏好向量（由存储层持久化）"""
    
    def __init__(self):
        self.storage = PreferenceStorage()
        self.data = self.storage.load()
    
    def from_profile(self, profile: Dict) -> Dict:
        """从用户画像加载偏好数据，优先使用独立文件"""
        stored = self.storage.load()
        
        # 优先用独立文件的偏好数据
        if stored.get('categories') or stored.get('methods'):
            self.data = stored
            return self.data
        
        # 独立文件为空，尝试从profile恢复
        if profile and 'preferences' in profile and profile['preferences'].get('version') == 2:
            self.data = profile['preferences']
            # 同步到独立文件
            self.storage.save(self.data)
        
        return self.data
    
    def to_dict(self) -> Dict:
        return self.data
    
    def apply_decay(self):
        """艾宾浩斯遗忘曲线衰减"""
        today = datetime.now().strftime('%Y-%m-%d')
        if self.data['last_decay'] == today:
            return
        
        decay_rate = 0.05  # 每天衰减5%
        
        for cat in self.data['categories']:
            entry = self.data['categories'][cat]
            days_since = (datetime.now() - datetime.strptime(entry['last_mention'], '%Y-%m-%d')).days if entry['last_mention'] else 0
            if days_since > 0:
                decay = math.exp(-decay_rate * days_since)
                entry['score'] = round(entry['score'] * decay, 3)
        
        self.data['last_decay'] = today
    
    def update_category(self, category: str, score: float, sentiment: str = 'neutral'):
        """更新分类偏好分数（自动保存）"""
        if category not in self.data['categories']:
            self.data['categories'][category] = {
                'score': 0.5, 'count': 0, 'last_mention': '', 'trend': 'stable', 'sentiments': []
            }
        
        cat = self.data['categories'][category]
        cat['count'] += 1
        cat['last_mention'] = datetime.now().strftime('%Y-%m-%d')
        cat['sentiments'].append(sentiment)
        if len(cat['sentiments']) > 10:
            cat['sentiments'] = cat['sentiments'][-10:]
        
        alpha = 1 / (cat['count'] + 1)
        cat['score'] = round(cat['score'] * (1 - alpha) + score * alpha, 3)
        
        recent = cat['sentiments'][-3:]
        pos = recent.count('positive')
        neg = recent.count('negative')
        if pos > neg: cat['trend'] = 'improving'
        elif neg > pos: cat['trend'] = 'declining'
        else: cat['trend'] = 'stable'
        
        # 每次修改都持久化
        self._persist()
    
    def update_method(self, method: str, category: str, effective: bool = None):
        """更新具体方法的尝试结果（自动保存）"""
        if method not in self.data['methods']:
            self.data['methods'][method] = {
                'tried': 0, 'effective': 0, 'ineffective': 0,
                'category': category, 'last_mention': '', 'outcome_chain': []
            }
        
        m = self.data['methods'][method]
        m['tried'] += 1
        m['last_mention'] = datetime.now().strftime('%Y-%m-%d')
        
        if effective is True:
            m['effective'] += 1
            m['outcome_chain'].append('effective')
        elif effective is False:
            m['ineffective'] += 1
            m['outcome_chain'].append('ineffective')
        
        if len(m['outcome_chain']) > 5:
            m['outcome_chain'] = m['outcome_chain'][-5:]
        
        self._persist()
    
    def _persist(self):
        """持久化：加载现有数据，合并，保存"""
        existing = self.storage.load()
        merged = PreferenceMerge.merge(existing, self.data)
        self.data = merged
        self.storage.save(self.data)
    
    def add_inference(self, inference: Dict):
        """添加DeepSeek的偏好推断"""
        self.data['inferred'].append({
            **inference,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        if len(self.data['inferred']) > 10:
            self.data['inferred'] = self.data['inferred'][-10:]
    
    def add_sentence(self, sentence: str, category: str, sentiment: str):
        """添加原始句子（自动去重，相同文本不重复记录）"""
        text = sentence[:100]
        # 去重：检查最近5条有没有相同文本
        recent = [s['text'] for s in self.data['sentences'][-5:]]
        if text in recent:
            return
        
        self.data['sentences'].append({
            'text': text,
            'category': category,
            'sentiment': sentiment,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        if len(self.data['sentences']) > 20:
            self.data['sentences'] = self.data['sentences'][-20:]


class DeepSeekPreferenceAnalyzer:
    """调用 DeepSeek 做偏好语义分析"""
    
    def __init__(self, call_deepseek_fn=None):
        self.call_deepseek = call_deepseek_fn
    
    def analyze(self, user_message: str, history: List[Dict] = None) -> Dict:
        """分析用户消息中的偏好信息"""
        if not self.call_deepseek:
            return self._fallback_analyze(user_message)
        
        prompt = f"""分析下面这句话中的睡眠偏好信息，以JSON格式返回。

用户说: "{user_message}"

请分析：
1. category: 这句话涉及哪个策略方向？可选值: relaxation, routine, environment, diet, exercise, cognitive, medication, None
2. sentiment: 积极(positive)/消极(negative)/中性(neutral)/无(None)
3. method: 提到的具体方法名称（如呼吸法、冥想、白噪音），没有则null
4. inferred_preference: 推断用户对这个方法的态度（喜欢/like、不喜欢/dislike、尝试过/tried、想尝试/want_to_try、无/None）
5. alternative_suggestion: 如果用户不喜欢当前方法，有什么替代方案可选？（一句话建议）

只返回JSON，不要其他文字。格式:
{{"category": "...", "sentiment": "...", "method": "...", "inferred_preference": "...", "alternative_suggestion": "..."}}"""
        
        try:
            result = self.call_deepseek([{'role': 'user', 'content': prompt}], max_tokens=200, temperature=0.1)
            text = result.get('content', '')
            # 提取JSON
            import re
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        return self._fallback_analyze(user_message)
    
    def _fallback_analyze(self, text: str) -> Dict:
        """关键词回退分析（DeepSeek不可用时）"""
        text = text.lower()
        
        # 方法匹配
        method_map = {
            '冥想': '冥想', '正念': '正念', '呼吸': '呼吸法', '白噪音': '白噪音',
            '轻音乐': '轻音乐', '跑步': '跑步', '散步': '散步', '瑜伽': '瑜伽',
            '拉伸': '拉伸', '太极': '太极', '咖啡': '戒咖啡', '褪黑素': '褪黑素',
            '日记': '写日记', '运动': '运动', '固定作息': '固定作息',
        }
        found_method = None
        for kw, method in method_map.items():
            if kw in text:
                found_method = method
                break
        
        # 类别匹配
        category = None
        for cat, info in PREFERENCE_CATEGORIES.items():
            if found_method and found_method in info['examples']:
                category = cat
                break
            for ex in info['examples']:
                if ex in text:
                    category = cat
                    break
            if category:
                break
        
        # 情感分析
        sentiment = 'neutral'
        positive = ['好了', '有效', '不错', '有用', '改善', '喜欢', '不错', '有用', '坚持了']
        negative = ['没用', '不行', '没效果', '不喜欢', '不想', '不要', '试过', '不好', '坚持不了', '无聊', '太累']
        
        for w in positive:
            if w in text:
                sentiment = 'positive'
                break
        for w in negative:
            if w in text:
                sentiment = 'negative'
                break
        
        # 推断偏好（注意优先级：情感 > 动作）
        pref = 'None'
        if sentiment == 'positive':
            pref = 'like'
        elif sentiment == 'negative':
            pref = 'dislike'  # 负面情感优先
        if pref == 'None':
            if '试过' in text or '尝试' in text or '用了' in text or '坚持' in text:
                pref = 'tried'
            if '想' in text or '打算' in text or '试试' in text or '开始' in text:
                pref = 'want_to_try'
            pref = 'want_to_try'
        
        return {
            'category': category,
            'sentiment': sentiment if sentiment != 'neutral' else 'None',
            'method': found_method,
            'inferred_preference': pref,
            'alternative_suggestion': ''
        }


class PreferenceEngine:
    """偏好学习引擎主类"""
    
    def __init__(self, call_deepseek_fn=None):
        self.memory = PreferenceMemory()
        self.analyzer = DeepSeekPreferenceAnalyzer(call_deepseek_fn)
    
    def process_message(self, user_message: str, profile: Dict) -> Dict:
        """处理用户消息，更新偏好"""
        self.memory.from_profile(profile)
        self.memory.apply_decay()
        
        analysis = self.analyzer.analyze(user_message)
        
        cat = analysis.get('category')
        sentiment = analysis.get('sentiment')
        method = analysis.get('method')
        pref = analysis.get('inferred_preference')
        
        if cat and cat != 'None' and sentiment != 'None':
            score_map = {'positive': 0.8, 'negative': 0.2, 'neutral': 0.5}
            score = score_map.get(sentiment, 0.5)
            self.memory.update_category(cat, score, sentiment)
            self.memory.add_sentence(user_message[:60], cat, sentiment)
        
        if method:
            effective = None
            if pref == 'like': effective = True
            elif pref == 'dislike': effective = False
            self.memory.update_method(method, cat or 'unknown', effective)
        
        if analysis.get('alternative_suggestion'):
            self.memory.add_inference(analysis)
        
        return self.memory.to_dict()
    
    def build_context(self, preferences: Dict) -> str:
        """构建偏好上下文注入prompt（含自学习协同）"""
        if not preferences or not preferences.get('categories'):
            return ''
        
        lines = ['【偏好学习引擎分析】']
        
        # 有明确倾向的分类
        cats = preferences.get('categories', {})
        disliked = [cat for cat, info in cats.items() if info.get('score', 0.5) < 0.35]
        liked = [cat for cat, info in cats.items() if info.get('score', 0.5) > 0.7]
        
        cat_names = {
            'relaxation': '放松类', 'routine': '作息类', 'environment': '环境类',
            'diet': '饮食类', 'exercise': '运动类', 'cognitive': '认知类',
            'medication': '药物类'
        }
        
        if disliked:
            names = [cat_names.get(c, c) for c in disliked]
            lines.append(f'  用户不太接受的策略方向: {", ".join(names)}')
            lines.append(f'  → 建议避免推荐这些方向')
        
        # 针对特定被拒类别给出已知的替代方案
        if 'relaxation' in disliked:
            lines.append(f'  替代建议: 可以推荐呼吸法、白噪音或轻音乐（不需要长期坚持）')
        if 'exercise' in disliked:
            lines.append(f'  替代建议: 可以推荐散步或简单拉伸')
        if 'cognitive' in disliked:
            lines.append(f'  替代建议: 可以推荐简单的情绪记录')
        if 'diet' in disliked:
            lines.append(f'  替代建议: 可以推荐调整摄入时间而非完全戒断')
        
        if liked:
            names = [cat_names.get(c, c) for c in liked]
            lines.append(f'  用户比较接受的策略方向: {", ".join(names)}')
        
        # 方法效果统计
        methods = preferences.get('methods', {})
        if methods:
            # 有效的方法
            effective_methods = {k: v for k, v in methods.items() if v.get('effective', 0) > v.get('ineffective', 0)}
            if effective_methods:
                top_eff = sorted(effective_methods.items(), key=lambda x: -x[1]['effective'])[:2]
                lines.append(f'  曾被报告有效的方法: {", ".join(k for k, v in top_eff)}')
            
            # 无效的方法
            ineffective_methods = {k: v for k, v in methods.items() if v.get('ineffective', 0) >= v.get('effective', 0) and v.get('tried', 0) > 0}
            if ineffective_methods:
                top_ineff = sorted(ineffective_methods.items(), key=lambda x: -x[1]['ineffective'])[:2]
                lines.append(f'  曾被报告无效的方法: {", ".join(k for k, v in top_ineff)}')
        
        # DeepSeek推断
        inferred = preferences.get('inferred', [])
        if inferred:
            last = inferred[-1]
            if last.get('alternative_suggestion'):
                lines.append(f'  AI推断: {last["alternative_suggestion"]}')
        
        # ===== 🌉 协同注入：群体校准数据 → 个体偏好 =====
        try:
            _cal_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'calibration.json')
            if os.path.exists(_cal_path):
                with open(_cal_path, 'r', encoding='utf-8') as f:
                    _cal = json.load(f)
                _declining = _cal.get('declining_prefs', [])
                _pref_note = _cal.get('pref_note', '')
                if _declining:
                    _dn = [cat_names.get(c, c) for c in _declining]
                    lines.append(f'  群体趋势: {", ".join(_dn)}方向普遍效果不佳')
                    # 对应用户喜欢的同类方法，自动给出替代锚点
                    for _c in _declining:
                        if _c in liked:
                            _alts = {
                                'relaxation': '（数字化方案可能更有效，如APP引导呼吸）',
                                'exercise': '（微运动策略：睡前5分钟拉伸）',
                                'cognitive': '（简化版：单句重构练习）',
                                'medication': '（非药物替代方案优先）',
                            }
                            lines.append(f'  注意: 偏好{cat_names.get(_c,_c)}与群体效果不佳方向重叠{_alts.get(_c,"")}')
                if _pref_note:
                    lines.append(f'  {_pref_note}')
        except:
            pass
        
        lines.append('')
        return '\n'.join(lines)
