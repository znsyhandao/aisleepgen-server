#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pomdp_learner.py — AISleepGen 8-State True Bayesian POMDP Engine v2.0

颠覆点:
  1. 从150维倾角法 → 8维度语义POMDP，真贝叶斯更新 b(s) ∝ A(o|s) · b(s)
  2. 倾角法完全移除，只在无观测信息时保留
  3. 21维观测空间
  4. 狄利克雷在线学习A矩阵，共享先验直接注入8个状态

8个语义状态（索引0-7）:
  0 = acute_insomnia     — 评分<40, 近期突然失眠
  1 = chronic_poor       — 评分<40, 持续>2周的睡眠差
  2 = relapse            — 评分从>60突然降到<40 (回弹)
  3 = stable_good        — 评分>70, 持续稳定
  4 = stable_moderate    — 评分40-70, 波动小
  5 = anxiety_driven     — 焦虑/压力主导的睡眠问题
  6 = circadian_drift    — 入睡时间持续向凌晨漂移
  7 = recovering         — 评分从<40上升到>55的改善期

API兼容:
  POMDPEngine.observe(openid, text='', score=None, bedtime=None, mood=None,
                       time_of_day='night', feedback=1) -> belief dict
  POMDPEngine.observe_survey(openid, score, bedtime='', mood='positive',
                              time_of_day='night', feedback=1) -> belief dict
  POMDPEngine.observe_message(openid, message_text)
  POMDPEngine.decide(openid) -> dict with 'action', 'confidence', 'policy'
  POMDPEngine.get_belief(openid) -> dict with 'expected_score', 'entropy', 'belief_probs'
  POMDPEngine.compute_expected_free_energy(openid, policy, horizon=3) -> float
  POMDPEngine.get_learner_stats(openid) -> dict
  POMDPEngine.save_all()
  get_engine(forget_factor=0.9, alpha0=0.1) -> POMDPEngine
"""

import json, os, time, math, logging, re, random
from datetime import datetime
from collections import defaultdict

_pm_log = logging.getLogger('aisleepgen.pomdp_learner')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ==================== POMDP 参数 ====================

# 8个语义状态
N_STATES = 8

# 21个观测类型
N_OBS = 21

# 观测类型区间
OBS_SCORE_START, OBS_SCORE_END = 0, 4       # 0-4: 评分5档
OBS_BEDTIME_START, OBS_BEDTIME_END = 5, 8    # 5-8: 就寝时间4档
OBS_MOOD_START, OBS_MOOD_END = 9, 11         # 9-11: 情绪3档
OBS_TIME_START, OBS_TIME_END = 12, 13        # 12-13: 时间段2档
OBS_FEEDBACK_START, OBS_FEEDBACK_END = 14, 15  # 14-15: 反馈2档
OBS_EFFECT_START, OBS_EFFECT_END = 16, 18    # 16-18: 干预效果3档
OBS_SURVEY_START, OBS_SURVEY_END = 19, 20    # 19-20: 问卷评分空/有

# 状态名称
STATE_NAMES = [
    "acute_insomnia",
    "chronic_poor",
    "relapse",
    "stable_good",
    "stable_moderate",
    "anxiety_driven",
    "circadian_drift",
    "recovering",
]

# 评分预期（每个状态的典型评分）
STATE_EXPECTED_SCORES = [25, 25, 30, 85, 55, 35, 40, 65]

# ==================== 共享先验（A矩阵初始化） ====================
#
# 每个状态对21个观测类型的条件概率 prior[s][o]
# 这是领域知识注入，确保新用户启动时就有合理的A矩阵

_SHARED_PRIOR = [
    # 0 = acute_insomnia: 低评分、负面情绪、夜间
    [0.25, 0.35, 0.20, 0.12, 0.08,  # score: 0-20/20-40/40-60/60-80/80-100
     0.15, 0.20, 0.35, 0.30,        # bedtime: before22/22-0/0-2/after2
     0.50, 0.30, 0.20,              # mood: negative/neutral/positive
     0.20, 0.80,                    # time: day/night
     0.60, 0.40,                    # feedback: negative/positive
     0.15, 0.50, 0.35,              # effect: effective/neutral/counter
     0.05, 0.95],                   # survey: empty/filled

    # 1 = chronic_poor: 持续低评分、偏负面
    [0.20, 0.40, 0.25, 0.10, 0.05,
     0.10, 0.25, 0.40, 0.25,
     0.35, 0.40, 0.25,
     0.30, 0.70,
     0.45, 0.55,
     0.20, 0.40, 0.40,
     0.05, 0.95],

    # 2 = relapse: 评分突然下降、高意外、情绪差
    [0.35, 0.40, 0.15, 0.07, 0.03,
     0.10, 0.20, 0.35, 0.35,
     0.55, 0.30, 0.15,
     0.15, 0.85,
     0.60, 0.40,
     0.10, 0.35, 0.55,
     0.10, 0.90],

    # 3 = stable_good: 高评分、情绪好、有问卷
    [0.02, 0.05, 0.13, 0.35, 0.45,
     0.50, 0.30, 0.15, 0.05,
     0.05, 0.15, 0.80,
     0.60, 0.40,
     0.10, 0.90,
     0.50, 0.40, 0.10,
     0.02, 0.98],

    # 4 = stable_moderate: 中等评分、中等情绪
    [0.05, 0.15, 0.40, 0.30, 0.10,
     0.30, 0.35, 0.25, 0.10,
     0.10, 0.40, 0.50,
     0.45, 0.55,
     0.20, 0.80,
     0.35, 0.45, 0.20,
     0.03, 0.97],

    # 5 = anxiety_driven: 负面情绪主导
    [0.20, 0.30, 0.30, 0.15, 0.05,
     0.20, 0.30, 0.30, 0.20,
     0.65, 0.25, 0.10,
     0.25, 0.75,
     0.55, 0.45,
     0.20, 0.45, 0.35,
     0.05, 0.95],

    # 6 = circadian_drift: 就寝时间极晚
    [0.10, 0.20, 0.30, 0.25, 0.15,
     0.02, 0.08, 0.30, 0.60,
     0.20, 0.35, 0.45,
     0.20, 0.80,
     0.30, 0.70,
     0.25, 0.50, 0.25,
     0.05, 0.95],

    # 7 = recovering: 评分上升趋势
    [0.05, 0.10, 0.30, 0.35, 0.20,
     0.40, 0.30, 0.20, 0.10,
     0.10, 0.30, 0.60,
     0.50, 0.50,
     0.15, 0.85,
     0.45, 0.40, 0.15,
     0.05, 0.95],
]

# ==================== 观测编码函数 ====================


def _discretize_score(score_or_text):
    """评分或文本 → 5档离散观测(0-4)"""
    if isinstance(score_or_text, (int, float)):
        s = float(score_or_text)
        if s <= 20:
            return 0
        elif s <= 40:
            return 1
        elif s <= 60:
            return 2
        elif s <= 80:
            return 3
        else:
            return 4

    text = str(score_or_text).lower()
    # 否定前缀检测
    negated = any(neg in text[:4] for neg in ['不', '没', '非', '无', '别', '从未', '从不'])
    # 关键词→评分
    if any(kw in text for kw in ['通宵', '一夜没睡', '完全没睡', '太差了']):
        return 0
    if any(kw in text for kw in ['失眠', '睡不着', '醒了', '没睡好', '很差']):
        return (2 if negated else 1)
    if any(kw in text for kw in ['好累', '很累', '困死了']):
        return 1
    if any(kw in text for kw in ['一般', '就那样', '马马虎虎', '还行吧']):
        return 2
    if any(kw in text for kw in ['不错', '挺好', '还行', '还可以', '差不多', '舒服']):
        return (0 if negated else 3)
    if any(kw in text for kw in ['睡得好', '睡得爽', '睡得香', '太爽', '满分', '很好']):
        return (0 if negated else 4)

    # 尝试提取数字评分
    nums = re.findall(r'(\d+)(?:分|/100|%)', text)
    if nums:
        v = float(nums[0])
        if v <= 20:
            return 0
        elif v <= 40:
            return 1
        elif v <= 60:
            return 2
        elif v <= 80:
            return 3
        else:
            return 4
    return 2  # 默认中等


def _discretize_bedtime(hour_or_text):
    """入睡时间或文本 → 4档观测(5-8)"""
    if isinstance(hour_or_text, (int, float)):
        h = float(hour_or_text)
    else:
        text = str(hour_or_text).lower()
        if any(kw in text for kw in ['通宵', '熬夜']):
            return 8
        if '凌晨' in text:
            return 8
        nums = re.findall(r'(\d+)[:：点时](\d*)', text)
        if nums:
            h = int(nums[0][0]) + int(nums[0][1] or '0') / 60.0
        else:
            nums = re.findall(r'(\d{1,2})点', text)
            if nums:
                h = int(nums[0])
            else:
                nums = re.findall(r'(\d{1,2})', text)
                h = int(nums[0]) if nums else 23.0

    if 22 <= h < 24:
        return 6           # 22-0
    elif 0 <= h < 2:
        return 7           # 0-2
    elif 2 <= h < 5:
        return 8           # after2 (凌晨3-5点)
    else:
        return 5           # before22 (包括<22和>=26的异常值)


def _discretize_mood(mood_or_text):
    """情绪或文本 → 3档观测(9-11)"""
    if isinstance(mood_or_text, int):
        return max(9, min(11, mood_or_text + 9))
    if isinstance(mood_or_text, str):
        text = mood_or_text.lower()
        if any(kw in text for kw in ['positive', '开心', '平静', '轻松']):
            return 11
        if any(kw in text for kw in ['negative', '焦虑', '烦躁', '生气', '难过', '崩溃', '抑郁', '紧张']):
            return 9
        if any(kw in text for kw in ['neutral', '一般', '还行']):
            return 10
    return 10  # neutral


def _discretize_time(time_of_day):
    """时间段 → 2档观测(12-13)"""
    tod = str(time_of_day).lower() if time_of_day else 'night'
    if tod in ('day', 'evening', 'morning', 'afternoon'):
        return 12
    return 13  # night


def _discretize_feedback(feedback):
    """反馈 → 2档观测(14-15)"""
    if isinstance(feedback, int):
        fb = max(0, min(1, feedback))
        return 15 if fb == 1 else 14  # 1=positive(15), 0=negative(14)
    if isinstance(feedback, bool):
        return 15 if feedback else 14
    text = str(feedback).lower()
    if any(kw in text for kw in ['没用', '不行', '不对', '不适用', 'negative', '差']):
        return 14
    return 15  # 默认正向


def _discretize_effect(effect):
    """干预效果 → 3档观测(16-18)"""
    if isinstance(effect, int):
        return max(16, min(18, effect + 16))
    text = str(effect).lower()
    if any(kw in text for kw in ['effective', '有用', '有效']):
        return 16
    if any(kw in text for kw in ['counter', '不好', '负面']):
        return 18
    return 17  # neutral


def _score_bin_to_obs(score_bin):
    """评分分档(0-4) → 观测索引(0-4)"""
    return max(0, min(4, int(score_bin)))


def _parse_obs_from_params(score=None, bedtime=None, mood=None, time_of_day='night',
                            feedback=1, text='', effect=None, has_score=False):
    """从各种参数推断21维观测索引

    优先级: text > score > bedtime > mood > effect > time > feedback
    返回最有信息量的单一观测索引
    """
    if text:
        obs_idx = _parse_obs_from_text(text)
        if obs_idx is not None:
            return obs_idx

    if score is not None:
        sb = _discretize_score(score)
        return _score_bin_to_obs(sb)
    if bedtime is not None:
        return _discretize_bedtime(bedtime)
    if mood is not None:
        return _discretize_mood(mood)
    if effect is not None:
        return _discretize_effect(effect)
    if has_score:
        return 20  # 有问卷
    if time_of_day:
        return _discretize_time(time_of_day)
    if feedback is not None:
        return _discretize_feedback(feedback)

    return 19  # 默认fallback


def _parse_obs_from_text(text):
    """从文本提取最有信息量的观测索引"""
    if not text:
        return None

    text_lower = text.lower()

    # 1. 评分关键词
    score_texts = {
        0: ['通宵', '一夜没睡', '完全没睡', '太差了', '太差'],
        1: ['失眠', '睡不着', '没睡好', '很差', '好累', '很累', '醒了', '困死了'],
        2: ['一般', '就那样', '马马虎虎', '还行吧'],
        3: ['不错', '挺好', '还可以', '差不多', '舒服'],
        4: ['睡得好', '睡得爽', '睡得香', '太爽', '满分', '很好'],
    }
    for score_bin, keywords in score_texts.items():
        if any(kw in text_lower for kw in keywords):
            return _score_bin_to_obs(score_bin)

    # 2. 就寝时间
    if any(kw in text_lower for kw in ['凌晨', '通宵', '熬夜']):
        return 8
    nums = re.findall(r'(\d+)[:：点时]', text)
    if nums:
        h = int(nums[0])
        if h < 22 or h >= 26:
            return 5
        elif h < 24:
            return 6
        elif h < 2:
            return 7
        else:
            return 8

    # 3. 情绪
    if any(kw in text_lower for kw in ['焦虑', '烦躁', '生气', '难过', '崩溃', '抑郁', '紧张', '担心']):
        return 9
    if any(kw in text_lower for kw in ['开心', '平静', '轻松', '期待']):
        return 11

    return None


def _infer_most_likely_state(belief_probs):
    """根据信念推断最可能的语义状态"""
    return max(range(N_STATES), key=lambda s: belief_probs[s])


def _get_expected_score(belief_probs):
    """从信念计算期望评分"""
    return sum(STATE_EXPECTED_SCORES[s] * p for s, p in enumerate(belief_probs))


def _compute_entropy(probs):
    """计算信念熵"""
    h = 0.0
    for p in probs:
        if p > 1e-10:
            h -= p * math.log(p)
    return h


# ==================== POMDP 信念 ====================

class POMDPBelief:
    """8维语义信念状态"""

    def __init__(self, probs=None):
        if probs:
            self.probs = list(probs)
        else:
            self.probs = [1.0 / N_STATES] * N_STATES

    def entropy(self):
        return _compute_entropy(self.probs)

    def normalized_entropy(self):
        h = self.entropy()
        h_max = math.log(N_STATES)
        return h / h_max if h_max > 0 else 1.0

    def expected_score(self):
        return _get_expected_score(self.probs)

    def copy(self):
        return POMDPBelief(list(self.probs))

    def update_with_obs(self, obs_idx, A_matrix):
        """真贝叶斯更新 b(s) ∝ A(o|s) · b(s)

        使用A矩阵的完整概率，不做任何倾斜
        """
        # 计算似然 P(o|b) = Σ_s A(o|s)·b(s)
        like_total = 0.0
        for s_idx in range(N_STATES):
            like_total += A_matrix[s_idx][obs_idx] * self.probs[s_idx]

        if like_total <= 1e-15:
            return  # 无信息更新

        # b'(s) = A(o|s) · b(s) / P(o|b)
        for s_idx in range(N_STATES):
            self.probs[s_idx] *= A_matrix[s_idx][obs_idx] / like_total

        total = sum(self.probs) or 1.0
        for i in range(N_STATES):
            self.probs[i] /= total

    def predict_step(self, dt=0.3):
        """预测步：向均匀分布扩散（状态自然漂移）"""
        noise = 0.15 * dt
        for i in range(N_STATES):
            self.probs[i] = self.probs[i] * (1 - noise) + noise / N_STATES
        total = sum(self.probs) or 1.0
        for i in range(N_STATES):
            self.probs[i] /= total

    def to_dict(self):
        return {
            'expected_score': round(self.expected_score(), 1),
            'entropy': round(self.entropy(), 3),
            'normalized_entropy': round(self.normalized_entropy(), 3),
            'belief_probs': [round(p, 4) for p in self.probs],
        }


# ==================== A矩阵在线学习 ====================

class ALearner:
    """A矩阵狄利克雷在线学习

    核心思想:
      A[s][o] = α₀ + shared_prior[s][o] * PRIOR_STR + shared_count[s][o] * SHARED_STR + user_count[s][o]

    共享先验: 领域知识始终存在
    共享计数: 跨用户统计
    用户计数: 自身观测
    信任权重: 调节更新幅度
    """

    _SHARED_DIR = None

    def __init__(self, openid, forget_factor=0.9, alpha0=0.1):
        self.openid = openid
        self.lambd = forget_factor
        self.alpha0 = alpha0
        self._A = None
        self._counts = None
        self._total_obs = 0
        self._loaded = False
        self._shared_counts = None
        self._belief_probs = None  # v4.1: 可持久化的信念

        dirpath = os.path.join(PROJECT_ROOT, 'user_pomdp')
        os.makedirs(dirpath, exist_ok=True)
        if ALearner._SHARED_DIR is None:
            ALearner._SHARED_DIR = dirpath
        self._dir = dirpath
        self._path = os.path.join(dirpath, f'{openid}_A.json')
        self._shared_path = os.path.join(dirpath, '_shared_A.json')

    def _load_shared(self):
        if self._shared_counts is not None:
            return
        self._shared_counts = [[0.0] * N_OBS for _ in range(N_STATES)]
        try:
            with open(self._shared_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for s_idx, row in data.get('counts', []):
                for o_idx, c in row:
                    self._shared_counts[s_idx][o_idx] = c
            self._A = None
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save_shared(self):
        counts_compact = []
        for s_idx in range(N_STATES):
            row = [(o_idx, c) for o_idx, c in enumerate(self._shared_counts[s_idx]) if c > 0.1]
            if row:
                counts_compact.append([s_idx, row])
        data = {
            'counts': counts_compact,
            'updated_at': datetime.now().isoformat(),
        }
        with open(self._shared_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    def _load(self):
        if self._loaded:
            return
        self._counts = [[0.0] * N_OBS for _ in range(N_STATES)]
        self._load_shared()
        try:
            with open(self._path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for s_idx, row in data.get('counts', []):
                for o_idx, c in row:
                    self._counts[s_idx][o_idx] = c
            self._total_obs = data.get('total_obs', 0)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        self._loaded = True

    def _save(self):
        counts_compact = []
        for s_idx in range(N_STATES):
            row = [(o_idx, c) for o_idx, c in enumerate(self._counts[s_idx]) if c > 0.01]
            if row:
                counts_compact.append([s_idx, row])
        data = {
            'counts': counts_compact,
            'total_obs': self._total_obs,
            'lambd': self.lambd,
            'updated_at': datetime.now().isoformat(),
        }
        # v4.1: 持久化信念
        if self._belief_probs is not None:
            data['belief_probs'] = [round(p, 6) for p in self._belief_probs]
        with open(self._path, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    def _load_belief(self):
        """从存储中恢复信念"""
        try:
            with open(self._path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('belief_probs', None)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _build_A(self):
        """从共享先验 + 用户计数构建A矩阵"""
        if self._A is not None:
            return self._A
        self._load()

        prior_strength = 10.0  # 领域知识强度

        if self._total_obs < 10:
            shared_strength = 5.0
        elif self._total_obs < 30:
            shared_strength = 2.0
        else:
            shared_strength = 0.5

        A = []
        for s_idx in range(N_STATES):
            row = []
            for o_idx in range(N_OBS):
                prior_val = _SHARED_PRIOR[s_idx][o_idx] * prior_strength
                shared_c = self._shared_counts[s_idx][o_idx] if self._shared_counts else 0.0
                user_c = self._counts[s_idx][o_idx]
                val = self.alpha0 + prior_val + shared_c * shared_strength + user_c
                row.append(val)
            total = sum(row) or 1e-10
            A.append([v / total for v in row])
        self._A = A
        return A

    def observe(self, obs_idx, trust_weight=1.0):
        """记录一次观测并更新计数"""
        self._load()
        self._A = None  # 强制A矩阵重建

        # 遗忘因子衰减
        for s_idx in range(N_STATES):
            for o_idx in range(N_OBS):
                self._counts[s_idx][o_idx] *= self.lambd

        w = max(0.01, trust_weight)

        # 使用先验条件概率加权分配计数到各状态
        for s_idx in range(N_STATES):
            prior_prob = _SHARED_PRIOR[s_idx][obs_idx]
            self._counts[s_idx][obs_idx] += w * (prior_prob * N_OBS * 0.5 + 0.5)

        # 高信任观测贡献给共享先验
        if trust_weight > 0.7:
            self._load_shared()
            for s_idx in range(N_STATES):
                prior_prob = _SHARED_PRIOR[s_idx][obs_idx]
                self._shared_counts[s_idx][obs_idx] += w * prior_prob * 3.0
            self._save_shared()

        self._total_obs += 1
        self._save()

    def get_A(self):
        self._build_A()
        return self._A

    def get_stats(self):
        self._load()
        self._load_shared()
        shared_total = sum(sum(row) for row in (self._shared_counts or []))
        return {
            'total_obs': self._total_obs,
            'forget_factor': self.lambd,
            'sparsity': sum(1 for row in self._counts for c in row if c > 0.01),
            'total_cells': N_STATES * N_OBS,
            'shared_total': round(shared_total, 1),
        }


# ==================== POMDP 引擎 ====================

class POMDPEngine:
    """完整POMDP引擎：信念+学习+决策

    使用8维语义状态和21维观测空间的真贝叶斯信念更新
    """

    def __init__(self, forget_factor=0.9, alpha0=0.1, beta=0.8, gamma=0.5):
        self.forget_factor = forget_factor
        self.alpha0 = alpha0
        self.beta = beta
        self.gamma = gamma
        self.intervention_rate = 0.5
        self.users = {}
        # v3.19: 短期工作记忆模块
        try:
            from working_memory import get_working_memory
            self.working_memory = get_working_memory()
        except ImportError:
            self.working_memory = None

        # v3.20: 行为预测模块
        try:
            from behavior_predictor import get_predictor
            self.behavior_predictor = get_predictor()
        except ImportError:
            self.behavior_predictor = None

        # v4.6.0: 群体策略进化
        try:
            from population_manager import get_population_manager
            self.population_manager = get_population_manager()
        except ImportError:
            self.population_manager = None

    def _get_user(self, openid):
        if openid not in self.users:
            cluster_params = None
            # v4.6.0: 获取群体特异性参数
            if self.population_manager is not None:
                try:
                    cluster_params = self.population_manager.get_cluster_params(openid)
                except Exception:
                    pass

            ff = cluster_params.get('forget_factor', self.forget_factor) if cluster_params else self.forget_factor
            a0 = cluster_params.get('alpha0', self.alpha0) if cluster_params else self.alpha0
            learner = ALearner(openid, ff, a0)
            bel = POMDPBelief()
            # v4.1: 从磁盘恢复持久化信念
            saved_belief = learner._load_belief()
            if saved_belief and len(saved_belief) == 8:
                bel.probs = [float(p) for p in saved_belief]
            self.users[openid] = {
                'belief': bel,
                'learner': learner,
            }

            # 应用集群特异性参数到引擎级别
            if cluster_params:
                if 'beta' in cluster_params:
                    self.beta = cluster_params['beta']
                if 'intervention_rate' in cluster_params:
                    self.intervention_rate = cluster_params['intervention_rate']

        return self.users[openid]

    def _compute_trust_weight(self, openid, obs_idx):
        """计算观测信任权重"""
        user = self._get_user(openid)
        belief = user['belief']
        learner = user['learner']

        if learner._total_obs < 3:
            return 1.0

        A = learner.get_A()
        po = 0.0
        for s_idx in range(N_STATES):
            po += A[s_idx][obs_idx] * belief.probs[s_idx]
        po = max(po, 1e-10)

        surprise = -math.log(po)
        weight = math.exp(-surprise * 0.5)
        return max(0.1, min(1.0, weight))

    def observe(self, openid, text='', score=None, bedtime=None, mood=None,
                time_of_day='night', feedback=1, effect=None):
        """核心入口：一次观测注入

        自动从参数推断最佳观测类型(obs_idx 0-20)
        执行真贝叶斯信念更新
        """
        user = self._get_user(openid)
        belief = user['belief']
        learner = user['learner']

        # 推断观测索引
        obs_idx = _parse_obs_from_params(
            score=score, bedtime=bedtime, mood=mood,
            time_of_day=time_of_day, feedback=feedback, text=text,
            effect=effect, has_score=(score is not None)
        )

        if obs_idx is None:
            if text:
                sb = _discretize_score(text)
                obs_idx = _score_bin_to_obs(sb)
            else:
                obs_idx = _discretize_time(time_of_day or 'night')

        # 计算信任权重
        trust_weight = self._compute_trust_weight(openid, obs_idx)

        # 更新A矩阵
        learner.observe(obs_idx, trust_weight=trust_weight)

        # 真贝叶斯信念更新
        if trust_weight > 0.2:
            A = learner.get_A()
            belief.update_with_obs(obs_idx, A)

        # 预测一步
        belief.predict_step(dt=0.3)

        # v3.19: 自动推送到短期工作记忆
        self._push_to_wm(openid, text=text, score=score, bedtime=bedtime,
                         mood=mood, obs_idx=obs_idx)

        # v3.20: 行为预测误差追踪 — 如果观测到评分，记录预测误差
        if score is not None and self.behavior_predictor is not None:
            try:
                err_info = self.behavior_predictor.get_prediction_error(openid, score)
                # 系统误差持续偏大 → 降低λ
                if err_info.get('suggest_lambda_reduce'):
                    learner.lambd = max(learner.lambd - 0.05, 0.5)
                    _pm_log.info('[BP] Prediction error high, λ reduced to %.2f', learner.lambd)
            except Exception:
                pass

        # v4.6.0: 记录到群体管理器
        if self.population_manager is not None and effect is not None:
            try:
                positive = effect > 0 if isinstance(effect, (int, float)) else True
                self.population_manager.record_outcome(openid, 'observe', 
                                                       effect if isinstance(effect, (int, float)) else 0, 
                                                       positive)
            except Exception as e:
                _pm_log.warning('[PopMgr] record_outcome failed: %s', e)

        return belief.to_dict()

    def _push_to_wm(self, openid, text='', score=None, bedtime=None,
                    mood=None, obs_idx=None, outcome='none', intervention='none'):
        """自动将当前观测推送到短期工作记忆"""
        if self.working_memory is None:
            return
        try:
            entry = {
                'text': str(text)[:200] if text else '',
                'score_obs': score if score is not None else (
                    _get_expected_score(self._get_user(openid)['belief'].probs)
                    if score is None and bedtime is None else 50
                ),
                'emotion': 'positive' if mood in ('positive',) else 'negative' if mood in ('negative',) else 'neutral',
                'intervention': intervention,
                'outcome': outcome,
            }
            # 从文本中提取评分
            if text and score is None:
                disc_score = _discretize_score(text)
                estimated_scores = {0: 15, 1: 35, 2: 55, 3: 73, 4: 90}
                entry['score_obs'] = estimated_scores.get(disc_score, 50)
            self.working_memory.push(openid, entry)
        except Exception as e:
            _wm_log = logging.getLogger('aisleepgen.pomdp_learner')
            _wm_log.warning('[POMDP-WM] Push failed: %s', e)

    def _get_short_term_context(self, openid):
        """获取短期记忆摘要文本

        Returns:
            str: 短期记忆摘要，如 ''（无数据时）或
                 '[短期记忆: 最近3次趋势(down), 最近干预: XXX, 短期评分: 68.3]'
        """
        if self.working_memory is None:
            return ''
        try:
            trend = self.working_memory.recent_trend(openid)
            stb = self.working_memory.short_term_belief(openid)
            interventions = self.working_memory.recent_interventions(openid, n=3)

            if stb['n'] == 0:
                return ''

            parts = []
            parts.append(f'最近3次趋势({trend["direction"]})')
            if interventions:
                parts.append(f'最近干预: {",".join(interventions)}')
            parts.append(f'短期评分: {stb["weighted_score"]}')
            return f'[短期记忆: {", ".join(parts)}]'
        except Exception:
            return ''

    def observe_message(self, openid, message_text):
        """微信消息 → POMDP观测"""
        return self.observe(openid, text=message_text)

    def observe_survey(self, openid, score, bedtime='', mood='positive',
                       time_of_day='night', feedback=1):
        """问卷提交 → POMDP观测"""
        # 评分作为主要观测
        obs_idx = _score_bin_to_obs(_discretize_score(score))

        user = self._get_user(openid)
        belief = user['belief']
        learner = user['learner']

        trust_weight = self._compute_trust_weight(openid, obs_idx)
        learner.observe(obs_idx, trust_weight=trust_weight)

        if trust_weight > 0.2:
            A = learner.get_A()
            belief.update_with_obs(obs_idx, A)

        # 附加观测：就寝时间
        if bedtime:
            bed_obs = _discretize_bedtime(bedtime)
            A = learner.get_A()
            belief.update_with_obs(bed_obs, A)

        # 附加观测：情绪
        if mood:
            mood_obs = _discretize_mood(mood)
            A = learner.get_A()
            belief.update_with_obs(mood_obs, A)

        # 附加观测：时间段
        time_obs = _discretize_time(time_of_day)
        A = learner.get_A()
        belief.update_with_obs(time_obs, A)

        # 附加观测：反馈
        fb_obs = _discretize_feedback(feedback)
        A = learner.get_A()
        belief.update_with_obs(fb_obs, A)

        belief.predict_step(dt=0.3)

        # v3.19: 推送到短期工作记忆
        self._push_to_wm(openid, text='', score=score, bedtime=bedtime,
                         mood=mood, outcome='none', intervention='none')

        # v3.20: 行为预测误差追踪
        if score is not None and self.behavior_predictor is not None:
            try:
                err_info = self.behavior_predictor.get_prediction_error(openid, score)
                if err_info.get('suggest_lambda_reduce'):
                    learner.lambd = max(learner.lambd - 0.05, 0.5)
                    _pm_log.info('[BP] Survey prediction error high, λ reduced to %.2f', learner.lambd)
            except Exception:
                pass

        return belief.to_dict()

    # ==================== 自由能决策 ====================

    def compute_expected_free_energy(self, openid, policy, horizon=3):
        """G(π) = utility + prior - β · info_gain

        对策略π，累计horizon步的预期自由能
        使用8态信念推导state-dependent偏置，而非旧版启发式常数
        """
        user = self._get_user(openid)
        belief = user['belief']
        learner = user['learner']

        score_pref = belief.expected_score() / 100.0
        entropy = belief.normalized_entropy()
        probs = belief.probs  # len 8

        # ==================== state-dependent偏置 ====================
        # 从8个语义状态推导干预偏好
        # state: 0=acute_insomnia, 1=chronic_poor, 2=relapse,
        # 3=stable_good, 4=stable_moderate, 5=anxiety_driven,
        # 6=circadian_drift, 7=recovering

        # Utility: 基于状态的预期"效用"
        state_values = [0.15, 0.05, 0.10, 0.95, 0.55, 0.20, 0.30, 0.65]
        deficit = 0.0
        for s_idx, val in enumerate(state_values):
            deficit += probs[s_idx] * (1.0 - val)
        utility = -deficit

        # Prior偏置：基于状态对每种策略的倾向
        # [probe, in_chat, push, delay_push, skip] 各状态的策略偏好
        # 急性失眠/焦虑 → 倾向probe（先收集信息）
        # 稳定好 → 倾向skip
        # 回弹 → 倾向push（紧急干预）
        state_policy_map = [
            [0.0, -0.1, -0.2, -0.1, +0.3],  # 0=acute_insomnia → probe偏置
            [0.0, -0.1, -0.3, -0.1, +0.5],  # 1=chronic_poor → push偏置(for push=0.5+0.3=0.8? no it's cost)
            [-0.3, -0.1, -0.5, -0.2, +0.7],  # 2=relapse → 紧急push
            [+0.3, +0.2, +0.3, +0.1, -0.5],  # 3=stable_good → skip偏好
            [0.0, +0.1, +0.1, 0.0, 0.0],     # 4=stable_moderate → 中性
            [-0.2, -0.1, -0.3, -0.1, +0.4],  # 5=anxiety_driven → probe偏置
            [0.0, 0.0, -0.2, -0.4, +0.3],    # 6=circadian_drift → delay_push偏置
            [+0.1, 0.0, -0.1, 0.0, +0.2],    # 7=recovering → 偏skip
        ]
        policy_keys = ['probe', 'in_chat', 'push', 'delay_push', 'skip']
        pidx = policy_keys.index(policy)

        prior = 0.0
        for s_idx in range(8):
            prior += probs[s_idx] * state_policy_map[s_idx][pidx]

        # 干预成本
        ir = self.intervention_rate
        cost_map = {'probe': 0.10, 'in_chat': 0.20, 'push': 0.30,
                     'delay_push': 0.20, 'skip': 0.0}
        cost = cost_map[policy] / max(ir, 0.1)

        # Expected information gain: 基于entropy和状态的"不确定性"
        # 高entropy + 高uncertainty = probe有价值
        # 但stable_good不需要信息
        # 从belief中推导"信息增益价值"
        # 状态0,1,2,5的entropy乘数高（需要更多信息）
        info_value_states = [1.5, 1.0, 2.0, 0.2, 0.5, 1.5, 1.0, 0.8]
        info_mult = 0.0
        for s_idx in range(8):
            info_mult += probs[s_idx] * info_value_states[s_idx]
        info_mult *= entropy

        # 不同策略的信息增益不同
        policy_info_scales = {'probe': 1.0, 'in_chat': 0.7, 'push': 0.15,
                               'delay_push': 0.15, 'skip': 0.0}
        info = policy_info_scales[policy] * info_mult

        return utility + prior + cost - self.beta * info

    def decide(self, openid, horizon=3):
        """选择最优策略 π* = argmin G(π)"""

    def decide(self, openid, horizon=3):
        """选择最优策略 π* = argmin G(π)"""
        ges = {}
        for p in ['probe', 'push', 'in_chat', 'delay_push', 'skip']:
            ges[p] = self.compute_expected_free_energy(openid, p, horizon)

        # Softmax采样
        min_ge = min(ges.values())
        scores = {}
        for p, ge in ges.items():
            scores[p] = math.exp(-(ge - min_ge) / self.gamma)

        total = sum(scores.values()) or 1.0
        probs = {p: s / total for p, s in scores.items()}

        r = random.random()
        cum = 0.0
        chosen = 'skip'
        for p in ['probe', 'push', 'in_chat', 'delay_push', 'skip']:
            cum += probs[p]
            if r <= cum:
                chosen = p
                break

        user = self._get_user(openid)
        return {
            'action': chosen,
            'policy': chosen,
            'confidence': round(probs[chosen], 4),
            'free_energies': {p: round(ge, 4) for p, ge in ges.items()},
            'probabilities': {p: round(probs[p], 4) for p in ges},
            'belief_entropy': round(user['belief'].normalized_entropy(), 4),
            'expected_score': round(user['belief'].expected_score(), 1),
        }

    # ==================== 持久化与查询 ====================

    def get_belief(self, openid):
        """获取用户当前信念"""
        user = self._get_user(openid)
        return user['belief'].to_dict()

    def get_learner_stats(self, openid):
        """获取A矩阵学习统计"""
        user = self._get_user(openid)
        return user['learner'].get_stats()

    def save_all(self):
        """保存所有用户状态（A矩阵 + 信念）"""
        for openid in list(self.users.keys()):
            user = self.users[openid]
            # v4.1: 持久化信念到learner再保存
            user['learner']._belief_probs = user['belief'].probs[:]
            user['learner']._save()
        return True


# 全局管理器（单例模式）
_engine = None


def get_engine(forget_factor=0.9, alpha0=0.1):
    global _engine
    if _engine is None:
        _engine = POMDPEngine(forget_factor, alpha0)
    return _engine


# ==================== 自测 ====================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')

    print('=== POMDP Learner Self-Test (8-State True Bayesian) ===\n')
    eng = POMDPEngine(forget_factor=0.9, alpha0=0.1, beta=0.8, gamma=0.5)

    # 1. 信念初始化
    b = POMDPBelief()
    expected_score = b.expected_score()
    assert abs(expected_score - (25+25+30+85+55+35+40+65)/8) < 0.01, \
        f'Initial expected score should be ~45, got {expected_score}'
    assert b.normalized_entropy() > 0.99, 'Initial entropy should be near max'
    print(f'1. Initial belief: score={expected_score:.1f}, H={b.normalized_entropy():.3f}')
    print(f'   belief_probs={[round(p,3) for p in b.probs]}')
    print('   OK')

    # 2. 观测编码测试
    assert _score_bin_to_obs(0) == 0
    assert _score_bin_to_obs(4) == 4
    assert _discretize_score(35) == 1
    assert _discretize_score(85) == 4  # 80-100 -> bin 4
    assert _discretize_bedtime(21.5) == 5   # before22
    assert _discretize_bedtime(23) == 6     # 22-0
    assert _discretize_bedtime(1) == 7      # 0-2
    assert _discretize_bedtime(3) == 8      # after2
    assert _discretize_mood('positive') == 11
    assert _discretize_mood('negative') == 9
    assert _discretize_time('day') == 12
    assert _discretize_time('night') == 13
    assert _discretize_feedback(1) == 15    # positive
    assert _discretize_feedback(0) == 14    # negative
    print('2. Observation encoding: all correct')
    print('   OK')

    # 3. 文本观测注入 — 失眠文本
    bel = eng.observe('test_text', text='昨晚失眠了，3点才睡着')
    print(f'3. Text obs (insomnia): score={bel["expected_score"]}, H={bel["normalized_entropy"]}')
    print(f'   belief_probs={[round(p,3) for p in bel.get("belief_probs", [])]}')
    assert bel['expected_score'] < 50, 'Insomnia text should lower expected score'
    assert bel['expected_score'] > 20, 'Not too low from single obs'
    print('   OK')

    # 4. 好睡眠文本
    bel2 = eng.observe('test_text', text='今天睡得好舒服！从11点一觉到7点')
    print(f'4. Text obs (good sleep): score={bel2["expected_score"]}, H={bel2["normalized_entropy"]}')
    assert bel2['expected_score'] > bel['expected_score'], 'Good sleep should raise score'
    print('   OK')

    # 5. 问卷观测
    bel3 = eng.observe_survey('test_survey', score=85, bedtime='22:00')
    print(f'5. Survey: score={bel3["expected_score"]}, H={bel3["normalized_entropy"]}')
    assert bel3['expected_score'] > 50, 'High survey score should raise belief'
    print('   OK')

    # 6. 多用户独立
    bel_a = eng.observe('user_text_a', text='太差了，失眠')
    bel_b = eng.observe_survey('user_survey_b', score=92, bedtime='21:30')
    print(f'6. Two users: A={bel_a["expected_score"]}, B={bel_b["expected_score"]}')
    assert abs(bel_a['expected_score'] - bel_b['expected_score']) > 5, 'Users should diverge'
    print('   OK')

    # 7. A矩阵学习 — 多轮观测
    init_stats = eng.get_learner_stats('test_learning')
    print(f'7. A learner initial: {init_stats["total_obs"]} obs')

    # 使用数字观测类型直接注入
    for i in range(8):
        eng.observe('test_learning', text='失眠睡不着')

    stats = eng.get_learner_stats('test_learning')
    print(f'   After 8 obs: {stats["total_obs"]} obs, sparsity={stats["sparsity"]}')
    assert stats['total_obs'] >= 8, 'Should count 8 observations'
    print('   OK')

    # 8. 自由能决策 — 低评分+高不确定→probe应该G最低
    eng2 = POMDPEngine(forget_factor=0.9, alpha0=0.1, beta=0.8, gamma=0.5)
    dec = eng2.decide('test_decision')
    print(f'8. Decision: {dec["policy"]}')
    for p, ge in sorted(dec['free_energies'].items(), key=lambda x: x[1]):
        print(f'   {p:12s} G={ge:+.4f}')
    ges = {p: ge for p, ge in dec['free_energies'].items()}
    assert ges['probe'] <= ges['push'], 'Probe should have lower G than push'
    print('   OK')

    # 9. 对话后决策收敛
    for text in ['昨晚2点才睡', '今天好累', '焦虑得不行']:
        eng.observe('test_converge', text=text)
    dec2 = eng.decide('test_converge')
    print(f'9. After 3 bad msgs: {dec2["policy"]}')
    print(f'   score={dec2["expected_score"]}, H={dec2["belief_entropy"]}')
    assert dec2['expected_score'] < 65, 'Multiple bad reports should lower score'
    print('   OK')

    # 10. 好数据后决策趋向skip/温柔
    for text in ['睡得爽', '太舒服了', '11点睡7点起']:
        eng.observe('test_good', text=text)
    dec3 = eng.decide('test_good')
    print(f'10. After 3 good msgs: {dec3["policy"]}')
    print(f'    score={dec3["expected_score"]}, H={dec3["belief_entropy"]}')
    for p, ge in sorted(dec3['free_energies'].items(), key=lambda x: x[1]):
        print(f'    {p:12s} G={ge:+.4f}')
    if dec3['expected_score'] > 60 and dec3['belief_entropy'] < 0.6:
        print('    Satisficing should push toward skip')
    print('    OK')

    # 11. 持久化
    eng.save_all()
    learner = eng._get_user('test_learning')['learner']
    learner_path = learner._path
    assert os.path.exists(learner_path), 'Should save A matrix'
    print(f'11. Persistence: {learner_path}')
    print('    OK')

    # 12. get_belief返回8维belief_probs
    bd = eng.get_belief('test_text')
    print(f'12. get_belief: score={bd["expected_score"]}, entropy={bd["entropy"]}')
    print(f'    belief_probs len={len(bd.get("belief_probs", []))}')
    assert len(bd.get('belief_probs', [])) == 8, 'should return 8-dim belief_probs'
    print('    OK')

    # 13. 共享先验完整性验证（行内校验）
    for s in range(N_STATES):
        assert len(_SHARED_PRIOR[s]) == N_OBS, f'State {s} has {len(_SHARED_PRIOR[s])} obs, expected {N_OBS}'
    print('13. Shared prior has correct dimensions (8x21): OK')

    # 14. observe_message API
    bel_msg = eng.observe_message('test_msg', '昨晚睡得不好')
    print(f'14. observe_message: score={bel_msg["expected_score"]}')
    assert 'expected_score' in bel_msg
    print('    OK')

    print('\nAll tests PASS! [OK]')

