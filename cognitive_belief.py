#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cognitive_belief.py — AGM 信念修正引擎 v2.1

演进：
  v1.0: 数值滑动窗口（4个0~1值，启发式加减）
  v2.0: AGM 命题信念集 + 贪心最小切除
  v2.1: ★ 独立本体库(belief_ontology.json) + 固筑度加权最小切除

核心机制：
  K = { "命题": 固筑度(0~1) }
  φ 与 K 矛盾 → 搜索固筑度总和最小的切除集 → 植入φ
  → 输出"可挑战点"供 AI prompt 使用

公开 API（兼容 v1.0/v2.0）：
  update(openid, score=None, mood=None, feedback=1, ...) -> dict
  profile_summary(openid) -> str
  summary_str(openid) -> str
"""

import os, json, math, time, re, itertools
from datetime import datetime
import logging
_log = logging.getLogger("cognitive_belief")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BELIEF_DIR = os.path.join(PROJECT_ROOT, 'user_pomdp')
ONTOLOGY_PATH = os.path.join(PROJECT_ROOT, 'belief_ontology.json')

# ========== 本体库加载 ==========

_ONTOLOGY = None


def _load_ontology():
    """加载信念本体库（独立配置文件）"""
    global _ONTOLOGY
    if _ONTOLOGY is not None:
        return _ONTOLOGY
    try:
        if os.path.exists(ONTOLOGY_PATH):
            with open(ONTOLOGY_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _ONTOLOGY = data
            _log.info("[AGM] 本体库加载: %d template dims, %d contradiction pairs, %d refutations",
                      len(data.get('belief_templates', {})),
                      len(data.get('contradiction_pairs', [])),
                      len(data.get('refutations', {})))
            return _ONTOLOGY
    except Exception as e:
        _log.warning("[AGM] 本体库加载失败: %s，使用硬编码默认值", e)
    # 硬编码默认值
    _ONTOLOGY = {
        "belief_templates": {
            "self_efficacy": [["我能睡好", 0.5], ["失眠会毁掉我", 0.3]],
            "catastrophic": [["今晚一定又失眠", 0.5], ["我永远也好不了", 0.2]],
            "trust": [["AI建议有用", 0.5], ["科技帮不了我", 0.3]],
            "effort": [["我必须努力睡着", 0.3], ["不睡着就躺着也行", 0.2]],
            "physical": [["身体累了自然睡", 0.6], ["年龄大了睡眠差正常", 0.4]],
        },
        "contradiction_pairs": [
            ["我能睡好", "今晚一定又失眠"],
            ["我可以信任它", "科技帮不了我"],
        ],
        "refutations": {
            "失眠会毁掉我": "偶尔失眠不影响长期健康",
            "今晚一定又失眠": "过去不代表未来",
        },
        "decay_params": {
            "daily_decay": 0.005,
            "positive_reinforce": 0.08,
            "negative_reinforce": 0.10,
            "trust_impact": 0.40,
        },
    }
    return _ONTOLOGY


def _get_belief_templates():
    return _load_ontology().get('belief_templates', {})


def _get_contradiction_pairs():
    return _load_ontology().get('contradiction_pairs', [])


def _get_refutations():
    return _load_ontology().get('refutations', {})


def _get_decay_params():
    return _load_ontology().get('decay_params', {})


def _build_contradiction_map():
    """从 contradiction_pairs 构建双向查找表"""
    m = {}
    for a, b in _get_contradiction_pairs():
        m[a] = b
        m[b] = a
    return m


def _build_refutation_map():
    return dict(_get_refutations())


# ========== 核心 AGM 系统 ==========

class BeliefSystem:
    """AGM 信念修正系统 v2.2——固筑度加权最小切除 + 隐式规则挖掘"""

    def __init__(self, openid):
        self.openid = openid
        self.K = {}  # {命题: 固筑度}
        self.history = []  # 信念变更日志
        self._cooldown = {}  # {命题: 最后切除时间} —— 防止信念震荡
        self._rules = {}  # ★ {信念: {"切除后改善": int, "切除后恶化": int}} —— 隐式规则
        self._contradictions = _build_contradiction_map()
        self._refutations = _build_refutation_map()
        self._candidate_log = []  # ★ 组合搜索路径日志（元认知原材料）
        self._load()

    def _load(self):
        """加载或初始化信念集"""
        path = os.path.join(BELIEF_DIR, f'{self.openid}_agm.json')
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # ★ Schema 版本检查（不可挽回死亡模式 3）
                _ver = data.get('__schema_version__', 0)
                if _ver < 1:
                    _log.info('[AGM] Schema v%s -> v1 upgrade for %s', _ver, openid[:8])
                self.K = data.get('K', {})
                self.history = data.get('history', [])
                self._cooldown = data.get('cooldown', {})
                self._rules = data.get('rules', {})
                self._ensure_templates()
                return
        except Exception as e:
            _log.warning("[AGM] load failed: %s", e)
        self._init_defaults()

    def _init_defaults(self):
        """用本体库模板初始化默认信念集
        固筑度初始值从 ontology.json 取，后续被行为信号修正"""
        self.K = {}
        for dim, beliefs in _get_belief_templates().items():
            taken = 0
            for prop, strength in beliefs:
                if taken < 2 and prop not in self.K:
                    self.K[prop] = strength
                    taken += 1
        self._save()

    def _estimate_entrenchment(self, prop, base_strength):
        """★ 从行为信号估算真实固筑度（心理学：ELM 固筑度理论）
        
        固筑度不是静态预设值，而是：
          1. 被切除次数（切除次数越多 = 修复固筑度越低 = 脆弱）
          2. 用户选择的持续时间（多次确认 = 固筑度高）
          3. 历史反馈的总体趋势（稳定上升 = 固筑度高）
        
        返回 0~1 的估算值。
        """
        # 基础值来自 ontology 预设
        est = float(base_strength)
        
        # 切除历史修正：每切一次，固筑度降 15%
        rule = self._rules.get(prop, {})
        cuts = rule.get('cuts', 0)
        if cuts > 0:
            est *= max(0.3, 1.0 - (cuts * 0.15))
        
        # history 中的趋势修正
        recent = [h for h in self.history[-20:]
                  if h.get('type') == 'strengthen' and prop in str(h)]
        if len(recent) >= 3:
            # 连续强化 → 固筑度上升
            est = min(1.0, est + min(0.3, len(recent) * 0.05))
        
        # 冷却期中 → 固筑度临时降低（可挑战性高）
        if prop in self._cooldown:
            elapsed = time.time() - self._cooldown[prop]
            if elapsed < 3600:
                est *= 0.7  # 冷却期内固筑度临时降低
            elif elapsed < 7200:
                est *= 0.85  # 冷却期后1小时内仍偏低
        
        return round(max(0.01, min(1.0, est)), 2)

    def _ensure_templates(self):
        """确保每个模板维度至少有一个信念"""
        changed = False
        seen_dims = set()
        for prop in list(self.K.keys()):
            for dim, beliefs in _get_belief_templates().items():
                if any(prop == b[0] for b in beliefs):
                    seen_dims.add(dim)
                    break
        for dim, beliefs in _get_belief_templates().items():
            if dim not in seen_dims:
                for prop, strength in beliefs[:2]:
                    if prop not in self.K:
                        self.K[prop] = strength
                        changed = True
                    seen_dims.add(dim)
                    break
        if changed:
            self._save()

    def _save(self):
        """持久化"""
        try:
            os.makedirs(BELIEF_DIR, exist_ok=True)
            path = os.path.join(BELIEF_DIR, f'{self.openid}_agm.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({
                    '__schema_version__': 1,  # 数据 schema 版本
                    'K': self.K,
                    'history': self.history[-50:],
                    'cooldown': self._cooldown,
                    'rules': self._rules,
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log.warning("[AGM] save failed: %s", e)

    def _is_contradiction(self, a, b):
        """两个命题是否矛盾（含语义近似检测）"""
        if a == b:
            return False
        # 直接矛盾对（来自本体库）
        if self._contradictions.get(a) == b:
            return True
        if self._contradictions.get(b) == a:
            return True
        # 否定前缀
        if len(a) > 1 and a[0] == '不' and a[1:] == b:
            return True
        if len(b) > 1 and b[0] == '不' and b[1:] == a:
            return True
        # ★ 语义近似：同义词/反义词自动检测（不依赖外部语料库）
        _antonym_pairs = [
            ('好', '坏'), ('能', '不能'), ('会', '不会'),
            ('可以', '不可以'), ('有用', '没用'), ('有帮助', '没帮助'),
            ('睡得着', '睡不着'), ('睡得', '睡不了'),
            ('轻松', '紧张'), ('放松', '焦虑'),
            ('适应', '抗拒'), ('接受', '排斥'),
            ('正常', '异常'), ('没事', '有事'),
        ]
        for pos, neg in _antonym_pairs:
            if pos in a and (neg in b or (neg not in b and a != b and
                any(kw in a for kw in ['不' + neg, neg + '不']))):
                # 精确检查是否真正相反
                if (pos in a and neg in b) or (neg in a and pos in b):
                    return True
        # 否定词检测：一个含有否定词且另一个是它的肯定形式
        _neg_words = ['不', '没', '无', '非', '莫', '勿']
        for nw in _neg_words:
            if a.startswith(nw) and a[len(nw):] == b:
                return True
            if b.startswith(nw) and b[len(nw):] == a:
                return True
        return False

    def _find_minimal_remove_set(self, phi):
        """★ 固筑度加权最小切除（v2.1 核心算法）

        搜索与 φ 矛盾的信念子集，找出固筑度总和最小的切除集。
        使用 BFS 剪枝——优先切除固筑度最低的信念。

        Args:
            phi: 要植入的新命题

        Returns:
            minimal_remove: 固筑度总和最小的切除集（list of str）
        """
        props = list(self.K.keys())
        contradictors = [p for p in props if self._is_contradiction(p, phi)]

        if not contradictors:
            return []

        # 按固筑度升序排列（最弱的排前面）
        contradictors.sort(key=lambda p: self.K[p])

        # ★ 规则加权的有效固筑度：改善率 > 60% 的信念翻倍（更容易被优先切除）
        def _effective_strength(p):
            s = self.K[p]
            if hasattr(self, '_rules') and p in self._rules:
                r = self._rules[p]
                total = r.get('effective_decay', 0) + r.get('ineffective_cuts', 0)
                if total >= 3:
                    effective_rate = r.get('effective_decay', 0) / total
                    if effective_rate > 0.6:
                        return s * 0.5  # 更低的"有效固筑度"→优先切除
            return s

        # 尝试各级别的切除量
        best_remove = list(contradictors)  # 兜底：全切
        best_cost = sum(_effective_strength(p) for p in contradictors)

        # ★ 加权搜索：尝试切除固筑度最低的 1~n 个
        for k in range(1, len(contradictors) + 1):
            for combo in itertools.combinations(contradictors, k):
                cost = sum(_effective_strength(p) for p in combo)
                if cost >= best_cost:
                    continue
                # 检查切除后是否仍有矛盾
                remaining = [p for p in props if p not in combo]
                still_conflict = any(self._is_contradiction(p, phi) for p in remaining)
                if not still_conflict and cost < best_cost:
                    best_cost = cost
                    best_remove = list(combo)

        # ★ 候选日志：记录搜索路径和次优选择（不可挽回——组合路径一旦丢弃不可重建）
        self._candidate_log.append({
            't': time.time(),
            'phi': phi,
            'contradictors': contradictors,
            'candidates_evaluated': len(contradictors),
            'chosen': list(best_remove),
            'chosen_cost': round(best_cost, 3),
            'chosen_effective_strengths': {p: round(_effective_strength(p), 3) for p in best_remove},
        })
        # 只保留最近 200 条候选日志，防止内存泄漏
        if len(self._candidate_log) > 200:
            self._candidate_log = self._candidate_log[-200:]

        return best_remove

    def revise(self, phi, phi_strength=0.7):
        """AGM 修正：K * φ

        ★ v2.1 使用固筑度加权最小切除，不再用贪心

        Args:
            phi: 新信念命题
            phi_strength: 初始固筑度

        Returns:
            (removed, added): (被切除的信念列表, 新增的信念列表)
        """
        if phi in self.K:
            # 已存在，只更新固筑度
            old = self.K[phi]
            self.K[phi] = max(self.K[phi], phi_strength)
            self.history.append({
                't': time.time(),
                'type': 'strengthen',
                'prop': phi,
                'from': round(old, 3),
                'to': round(self.K[phi], 3),
            })
            self._save()
            return [], [phi]

        removed = self._find_minimal_remove_set(phi)

        # ★ 冷却期检查：被切除的命题 1 小时内不再切（防止震荡）
        now = time.time()
        if removed:
            # 检查冷却期
            cooled_removed = [r for r in removed
                              if r not in self._cooldown
                              or now - self._cooldown[r] > 3600]
            if len(cooled_removed) != len(removed):
                # 部分冷却中，记录并跳过
                _log.info('[AGM] Cooldown active for %s, skipping some removes',
                          [r for r in removed if r not in cooled_removed])

            for r in cooled_removed:
                del self.K[r]
                self._cooldown[r] = now  # 设置冷却期
                # ★ 隐式规则挖掘：记录这个信念被切除
                if r not in self._rules:
                    self._rules[r] = {'cuts': 0, 'effective_decay': 0, 'ineffective_cuts': 0}
                self._rules[r]['cuts'] += 1
            self.history.append({
                't': time.time(),
                'type': 'retract',
                'removed': removed,
                'added': phi,
            })

        self.K[phi] = phi_strength
        self.history.append({
            't': time.time(),
            'type': 'insert',
            'prop': phi,
            'strength': phi_strength,
        })
        self._save()
        return removed, [phi]

    def get_challenge_point(self):
        """返回最可挑战的信念（固筑度估算值最低的可反驳信念）
        
        用 _estimate_entrenchment 取代直接读取 K 中的预设值。
        心理学依据：固筑度越低→越容易挑战→越值得优先干预。
        """
        best = None
        best_cost = float('inf')
        for prop, strength in self.K.items():
            if prop in self._refutations:
                est = self._estimate_entrenchment(prop, strength)
                if est < best_cost:
                    best_cost = est
                    best = (prop, est, self._refutations[prop])
        return best

    def get_challenge_points(self, limit=3):
        """返回 top-N 可挑战点（按动态固筑度排序）"""
        candidates = [(p, self._estimate_entrenchment(p, s), self._refutations[p])
                      for p, s in self.K.items() if p in self._refutations]
        candidates.sort(key=lambda x: x[1])
        return candidates[:limit]

    def decay(self, factor=None):
        """所有信念自然衰减（模拟遗忘）"""
        if factor is None:
            factor = _get_decay_params().get('daily_decay', 0.005)
        changed = False
        for prop in list(self.K.keys()):
            old = self.K[prop]
            new = max(0.01, old - factor)
            if new != old:
                self.K[prop] = new
                changed = True
        if changed:
            self._save()

    def nudge(self, prop, target_strength=0.3, iterations=3):
        """★ 渐进式干预——每次只削一点固筑度，多次后达到目标
        
        与 revise() 的关键区别：
        - 不移除信念，只降低固筑度
        - 分多次执行，模拟自然认知重构过程
        - 每次调用后记录 nudge 历史
        
        Args:
            prop: 目标信念
            target_strength: 目标固筑度（默认 0.3）
            iterations: 计划分几次完成 (默认 3)
        
        Returns:
            True 如果本轮执行了削除
        """
        if prop not in self.K:
            return False
        current = self.K[prop]
        if current <= target_strength:
            return False  # 已经达到目标
        
        reduction = (current - target_strength) / max(1, iterations)
        new_val = max(target_strength, current - reduction)
        old_val = self.K[prop]
        self.K[prop] = new_val
        
        self.history.append({
            't': time.time(),
            'type': 'nudge',
            'prop': prop,
            'from': round(old_val, 3),
            'to': round(new_val, 3),
            'remaining_iterations': iterations - 1,
        })
        self._save()
        _log.info('[AGM] Nudge %s: %.0f%% → %.0f%% (target %.0f%% in %d steps)',
                  prop, old_val * 100, new_val * 100, target_strength * 100, iterations)
        return True

    def to_legacy_numeric(self):
        """转换为 v1.0 兼容的数值格式"""
        legacy = {'self_efficacy': 0.5, 'catastrophic_expect': 0.5,
                  'treatment_trust': 0.5, 'sleep_effort': 0.3}
        for prop, strength in self.K.items():
            if prop in ("我能睡好", "身体累了自然睡", "我值得睡个好觉"):
                legacy['self_efficacy'] = min(1.0, legacy['self_efficacy'] + strength * 0.3)
            elif prop in ("失眠会毁掉我", "我永远也好不了", "一次失眠等于一周白睡"):
                legacy['self_efficacy'] = max(0.0, legacy['self_efficacy'] - strength * 0.3)
            if prop in ("今晚一定又失眠", "我永远也好不了", "睡不着明天就完了"):
                legacy['catastrophic_expect'] = min(1.0, legacy['catastrophic_expect'] + strength * 0.3)
            elif prop in ("我能睡好", "身体累了自然睡"):
                legacy['catastrophic_expect'] = max(0.0, legacy['catastrophic_expect'] - strength * 0.2)
            if prop == "AI建议有用":
                legacy['treatment_trust'] = min(1.0, legacy['treatment_trust'] + strength * _get_decay_params().get('trust_impact', 0.4))
            elif prop == "科技帮不了我":
                legacy['treatment_trust'] = max(0.0, legacy['treatment_trust'] - strength * _get_decay_params().get('trust_impact', 0.4))
            if prop == "我必须努力睡着":
                legacy['sleep_effort'] = min(1.0, legacy['sleep_effort'] + strength * 0.5)
            elif prop == "不睡着就躺着也行":
                legacy['sleep_effort'] = max(0.0, legacy['sleep_effort'] - strength * 0.4)
        for k in legacy:
            legacy[k] = max(0.0, min(1.0, legacy[k]))
        return legacy

    def get_band_baseline(self, openid):
        """★ 手环个人基线（不可挽回缺口 16）
        
        从活动日志中解析 band_data 记录，计算每人独立的正常范围。
        活动日志是异步写入的，不在主路径同步写文件。
        
        Returns:
            dict: {hrv: {mean, std, count}, spo2: ...} 或 None
        """
        import os, json, re
        _log_dir = os.path.join(os.path.dirname(__file__) or '.', 'data', 'activity_logs')
        if not os.path.isdir(_log_dir):
            return None
        from collections import defaultdict
        _fields = {'hrv': [], 'spo2': [], 'hr': []}
        _safe_oid = __import__('hashlib').sha256(str(openid).encode()).hexdigest()[:16]
        try:
            for _fname in sorted(os.listdir(_log_dir))[-30:]:  # 最近30天
                if not _fname.endswith('.jsonl'):
                    continue
                with open(os.path.join(_log_dir, _fname), 'r', encoding='utf-8') as _lf:
                    for _line in _lf:
                        _row = json.loads(_line.strip())
                        if _row.get('openid', '') != _safe_oid:
                            continue
                        if _row.get('action') != 'band_data':
                            continue
                        _detail = _row.get('detail', '')
                        for _f in _fields:
                            _m = re.search(r'%s=([\d.]+)' % _f.upper(), _detail)
                            if _m:
                                _fields[_f].append(float(_m.group(1)))
            _result = {}
            for _f, _vals in _fields.items():
                if len(_vals) >= 3:
                    _mean = sum(_vals) / len(_vals)
                    _var = sum((x - _mean) ** 2 for x in _vals) / len(_vals)
                    _result[_f] = {
                        'mean': round(_mean, 1),
                        'std': round(_var ** 0.5, 2),
                        'count': len(_vals),
                    }
            return _result if _result else None
        except Exception:
            return None


    def _predict_next_session(self):
        """★ 信念熵趋势预测——2027 跨会话模式分析的历史基线
        
        不看绝对值，看趋势方向：
        - 信念熵连续 3 次下降 → 认知固化 → 输出 risk_score 上升
        - 信念熵趋势不要求模型，它只是一个 if-else 判断
        
        Returns:
            dict: {risk_score: 0~5, trend: 'solidifying'|'stable'|'improving', entropy_history: [...]}
        """
        if len(self.history) < 5:
            return {'risk_score': 0, 'trend': 'stable', 'entropy_history': []}
        
        # 计算近 15 次交互的"信念熵"：固筑度分布均匀度（越低→越固化）
        # 用 history 的 insert 事件来采样
        _inserts = [h for h in self.history[-30:] if h.get('type') in ('insert', 'nudge')]
        _entropy_samples = []
        for h in _inserts[-10:]:
            prop = h.get('prop', '')
            if prop and prop in self.K:
                s = self.K[prop]
                # 简单熵近似：远离 0.5 的值越多→熵越低→越固化
                _entropy_samples.append(1.0 - abs(s - 0.5) * 2)  # 0.5→1.0(高熵), 0.0/1.0→0.0(低熵)
        
        if len(_entropy_samples) < 3:
            return {'risk_score': 0, 'trend': 'stable', 'entropy_history': _entropy_samples}
        
        # 看最后 3 个采样的趋势
        _recent = _entropy_samples[-3:]
        _trend = sum(1 for i in range(1, len(_recent)) if _recent[i] < _recent[i-1])
        
        risk = 0
        trend = 'stable'
        if _trend >= 2:
            # 连续下降 = 认知固化
            risk = min(5, int(sum(_recent) * 5))
            trend = 'solidifying'
        elif _trend == 0 and _recent[-1] > _recent[0]:
            trend = 'improving'
        
        return {
            'risk_score': risk,
            'trend': trend,
            'entropy_history': [round(x, 3) for x in _entropy_samples[-10:]],
            # ★ 周级行为一致性（死亡模式 7）
            'weekly_pattern': self._get_weekly_pattern(),
        }

    def _get_weekly_pattern(self):
        """按周切片聚合行为一致性——不存新数据，只做周切片分析"""
        import time as _wt
        _weeks = {}
        for h in self.history[-100:]:
            _t = h.get('t', 0)
            if not _t:
                continue
            _wk = _wt.localtime(_t).tm_yday // 7
            _type = h.get('type', '')
            if _type not in _weeks.setdefault(_wk, {}):
                _weeks[_wk][_type] = 0
            _weeks[_wk][_type] = _weeks[_wk].get(_type, 0) + 1
        if len(_weeks) < 2:
            return {'available_weeks': len(_weeks)}
        # 看最近 2 周的 insert 变化
        _wk_keys = sorted(_weeks.keys())[-2:]
        if len(_wk_keys) < 2:
            return {'available_weeks': len(_weeks)}
        _w1 = sum(_weeks[_wk_keys[-2]].values())
        _w2 = sum(_weeks[_wk_keys[-1]].values())
        return {
            'available_weeks': len(_weeks),
            'last_week_events': _w1,
            'this_week_events': _w2,
            'trend': 'up' if _w2 > _w1 else ('down' if _w2 < _w1 else 'stable'),
        }

    def challenge_text(self):
        """生成可嵌入 prompt 的挑战建议"""
        cp = self.get_challenge_point()
        if cp:
            return f'可挑战信念: "{cp[0]}" (固筑度{cp[1]:.0%}) → 可植入: "{cp[2]}"'
        return ''

    def challenge_text_extended(self):
        """生成完整的信念状态文本（供 prompt 注入）"""
        parts = []
        legacy = self.to_legacy_numeric()
        if legacy['self_efficacy'] < 0.3:
            parts.append('用户明显缺乏睡眠信心')
        elif legacy['self_efficacy'] > 0.7:
            parts.append('用户对睡眠有较高自信')
        if legacy['catastrophic_expect'] > 0.6:
            parts.append('存在灾难化预期倾向')
        if legacy['treatment_trust'] < 0.3:
            parts.append('用户对AI建议信任度偏低')
        elif legacy['treatment_trust'] > 0.7:
            parts.append('用户对AI建议接受度良好')
        if legacy['sleep_effort'] > 0.7:
            parts.append('用户存在过度努力睡眠的问题')

        # AGM 扩展：系统可以挑战的信念点
        challenge_text = ''
        cps = self.get_challenge_points(limit=3)
        if cps:
            items = [f'"{p}"({s:.0%})→"{r}"' for p, s, r in cps]
            challenge_text = f'可挑战顺序: {"; ".join(items)}'

        if parts or challenge_text:
            result = '认知信念: ' + '；'.join(parts)
            if challenge_text:
                result += '。' + challenge_text
            return result
        return ''


# ========== 公开 API（兼容 v1.0/v2.0） ==========

_systems = {}  # {openid: BeliefSystem}


def _get(openid):
    """获取或创建信念系统"""
    if openid not in _systems:
        _systems[openid] = BeliefSystem(openid)
    return _systems[openid]



def update(openid, score=None, mood=None, feedback=1, effect=None,
           score_change=0, follow_up=False, extracted_beliefs=None,
           behavior_signal=None):
    """更新认知信念（公开 API，兼容 v1.0 签名）

    v2.1 增强：从 belief_ontology.json 读取 decay params
    """
    bs = _get(openid)
    decay_params = _get_decay_params()

    # 0. ★ 从对话中提取的信念直接注入 AGM 系统（颠覆式改进）
    if extracted_beliefs:
        # ★ 信念同一性归并（不可挽回缺口 4）：防止同一语义的信念因措辞差异产生多条
        _existing_props = list(bs.K.keys())
        for b in extracted_beliefs:
            text = b.get('text', '').strip()
            strength = float(b.get('strength', 0.5))
            if not (text and len(text) > 2):
                continue
            
            # 检查是否与已有信念语义相似
            _merged = False
            for _ep in _existing_props:
                # 简单文本重叠检测：共享 >= 50% 字符即为相似
                _shared = len(set(text) & set(_ep))
                _min_len = min(len(text), len(_ep))
                if _min_len > 0 and _shared / _min_len > 0.5:
                    # 相似信念：合并强度（取 max），不增加新 key
                    bs.K[_ep] = max(bs.K[_ep], strength)
                    bs.history.append({
                        't': time.time(),
                        'type': 'merge',
                        'from': text,
                        'into': _ep,
                        'strength': bs.K[_ep],
                    })
                    _merged = True
                    break
            
            if not _merged:
                # 用 AGM 修正植入实时信念（会触发最小切除）
                bs.revise(text, strength)

    # ★ 时态监控器：检测信念链的时间模式（心理学：认知三角延迟效应）
    try:
        _catastrophic_candidates = ['今晚一定又失眠', '失眠会毁掉我', '睡不着明天就完了',
                                    '睡不好白天一定完蛋', '失眠会毁掉白天']
        for _cat in _catastrophic_candidates:
            if _cat in bs.K:
                # 检查近5次history中这个信念被提取的频率
                _recent_mentions = sum(1 for h in bs.history[-15:]
                                       if h.get('type') == 'insert' and h.get('prop', '') == _cat)
                if _recent_mentions >= 3:
                    # 连续3次出现同一灾难化信念 → 强度加重（认知固化的信号）
                    _log.info('[AGM] Temporal monitor: %s reinforced %d/5 → entrenchment signal', _cat, _recent_mentions)
                    # 记录强化但不自动加速衰减——让园丁（AI）看到趋势后决定挑战策略
                    if 'AI预测:%s' % _cat not in bs.K:
                        bs.K['AI预测:%s' % _cat] = 0.8  # 存储预测标记
    except Exception:
        pass

    # ★ 规则回填：用时间延迟一致性检测替代即时 feedback（认知三角理论纠正）
    # Beck (1979): 认知重构效果延迟 3-7 天。不用单次 feedback 做因果归因。
    if bs._rules:
        for rprop, rdata in bs._rules.items():
            if rdata.get('cuts', 0) > 0:
                _now = time.time()
                _last_cut = max([
                    h.get('t', 0) for h in bs.history
                    if h.get('type') == 'retract' and rprop in h.get('removed', [])
                ], default=0)
                # 只在切除后经过足够时间（>3次交互）才做有效性判断
                _interactions_since = sum(1 for h in bs.history[-30:]
                                          if h.get('t', 0) > _last_cut)
                if _last_cut > 0 and _interactions_since >= 3:
                    # 有效性检测：切除后同类信念固筑度是否自然衰减
                    _now_strength = bs.K.get(rprop, 0)
                    # 找到切除前该信念的固筑度
                    _before_strength = 0.5  # 默认
                    for h in reversed(bs.history):
                        if h.get('type') == 'retract' and rprop in h.get('removed', []):
                            _before_strength = bs.K.get(rprop, 0.5) or 0.5  # 用当前值近似
                            break
                    _decay_ratio = 1 - (_now_strength / max(0.01, _before_strength)) if _now_strength < _before_strength else 0
                    if _decay_ratio > 0.2:
                        # 固筑度下降了 >20% → 切除确实有效
                        rdata['effective_decay'] = rdata.get('effective_decay', 0) + 1
                        _log.info('[AGM] Rule: cut %s effective, decay %.0f%% (%d cum)',
                                 rprop, _decay_ratio * 100, rdata.get('effective_decay', 1))
                    else:
                        rdata['ineffective_cuts'] = rdata.get('ineffective_cuts', 0) + 1
                # ★ 规则影响切除优先级：有效比率 > 60% → 优先
                _total_eff = rdata.get('effective_decay', 0) + rdata.get('ineffective_cuts', 0)
                if _total_eff >= 3:
                    effective_rate = rdata.get('effective_decay', 0) / max(1, _total_eff)
                    if effective_rate > 0.6:
                        _log.info('[AGM] Rule matured: cut %s effective %.0f%% (%d samples)',
                                 rprop, effective_rate * 100, _total_eff)

    # ★ 行为信号 → 自动信念注入（第三刀）
    if behavior_signal:
        for sig in behavior_signal:
            sig_type = sig.get('type', '')
            sig_count = sig.get('count', 0)
            if sig_type == 'use_breathing' and sig_count >= 3:
                bs.revise('4-7-8 呼吸法有效', 0.7)
                _log.info('[AGM] Behavior signal: breathing used %d times → auto-belief', sig_count)
            elif sig_type == 'use_meditation' and sig_count >= 3:
                bs.revise('冥想帮助我放松', 0.7)
            elif sig_type == 'abandon_session' and sig_count >= 2:
                # 连续放弃会话 → 用户可能缺乏耐心
                if '我必须努力睡着' in bs.K:
                    bs.K['我必须努力睡着'] = min(1.0, bs.K['我必须努力睡着'] + 0.1)
            elif sig_type == 'consecutive_absent' and sig_count >= 3:
                # 连续 3 天不打开 → 治疗信赖度自动衰减
                if 'AI建议有用' in bs.K:
                    bs.K['AI建议有用'] = max(0.0, bs.K['AI建议有用'] - 0.1)
                _log.info('[AGM] Behavior signal: %d days absent → trust decay', sig_count)


    # 1. AGM 修正：反馈驱动的信念调整
    if feedback > 0:
        bs.revise("AI建议有用", 0.7)
        if "我能睡好" in bs.K:
            bs.K["我能睡好"] = min(1.0, bs.K["我能睡好"] + decay_params.get('positive_reinforce', 0.08))
        for neg_prop in _get_refutations().keys():
            if neg_prop in bs.K and bs.K[neg_prop] > 0.3:
                ref = _get_refutations().get(neg_prop)
                if ref:
                    bs.revise(ref, 0.2)
    elif feedback < 0:
        bs.revise("科技帮不了我", 0.6)
        if "今晚一定又失眠" in bs.K:
            bs.K["今晚一定又失眠"] = min(1.0, bs.K["今晚一定又失眠"] + decay_params.get('negative_reinforce', 0.1))

    # 2. 评分更新
    if score is not None:
        score_norm = score / 100.0
        if score_norm > 0.6:
            if "我能睡好" in bs.K:
                bs.K["我能睡好"] = min(1.0, bs.K["我能睡好"] + 0.12)
            for prop in ["今晚一定又失眠", "我永远也好不了", "一次失眠等于一周白睡"]:
                if prop in bs.K:
                    bs.K[prop] = max(0.0, bs.K[prop] - 0.1)
        elif score_norm < 0.4:
            bs.revise("今晚一定又失眠", 0.6)
            bs.revise("我必须努力睡着", 0.5)

    # 3. 自然衰减
    bs.decay()

    # ★ 流失模式快照（不可挽回缺口 5）：每次 AGM 更新存一条快照
    try:
        _snap_path = os.path.join(os.path.dirname(__file__) or '.', 'data', 'engagement_snapshot.jsonl')
        with open(_snap_path, 'a', encoding='utf-8') as _sf:
            import json as _sj
            _pred = bs._predict_next_session()
            _sf.write(_sj.dumps({
                't': time.time(),
                'v': __import__('version').VERSION,  # 系统版本号
                'openid': openid[:16],
                'belief_count': len(bs.K),
                'belief_entropy': round(sum(_pred.get('entropy_history', [0.5])) / max(1, len(_pred.get('entropy_history', [0.5]))), 3),
                'risk_score': _pred.get('risk_score', 0),
                'trend': _pred.get('trend', 'stable'),
                'weekly': _pred.get('weekly_pattern', {}).get('trend', '?'),
            }, ensure_ascii=False) + '\n')
    except Exception:
        pass  # 非关键路径

    bs._save()
    return bs.to_legacy_numeric()


# ========== 认知工具：AI 可调用的认知推理接口 ==========

def cognitive_analyze(openid, user_message='', history=None):
    """认知三角推理工具（AI 工具调用接口，function calling 兼容）

    接收用户消息 + 信念上下文 → 返回认知三角分析结果。
    AI 可以直接调用此函数代替等待 AGM 被动更新。

    Args:
        openid: 用户标识
        user_message: 用户最新一条消息（可选）
        history: 最近对话历史（可选，list of str）

    Returns:
        dict: 认知三角分析结果
    """
    bs = _get(openid)
    result = {
        'knowledge_level': '2.2.0',
        'analyzed_at': time.time(),
        'belief_count': len(bs.K),
        'top_beliefs': sorted(bs.K.items(), key=lambda x: -x[1])[:5],
        'contradiction_count': len(bs._find_contradictions()),
    }

    # 认知三角状态
    legacy = bs.to_legacy_numeric()
    triangle = []
    if legacy.get('self_efficacy', 0.5) < 0.3:
        triangle.append('认知断裂：自我效能低，用户不相信自己能改善')
    if legacy.get('catastrophic_expect', 0.3) > 0.6:
        triangle.append('认知断裂：灾难化预期，用户夸大失眠后果')
    if legacy.get('treatment_trust', 0.5) < 0.3:
        triangle.append('行为断裂：治疗信赖低，用户可能不会坚持干预')
    if legacy.get('sleep_effort', 0.5) > 0.7:
        triangle.append('行为断裂：过度努力睡眠，保持清醒焦虑')
    if not triangle:
        triangle.append('认知三角当前平衡')
    result['cognitive_triangle'] = triangle

    # 如果提供了用户消息，做实时分析
    if user_message:
        # 简单情绪-信念关联检测
        _neg_words = ['失眠', '睡不着', '痛苦', '焦虑', '害怕', '崩溃', '完了', '不行', '难受', '累死']
        _pos_shift_words = ['好些了', '好点', '睡了', '有效', '有用', '改善了', '进步了', '试试']
        _neg_count = sum(1 for w in _neg_words if w in user_message)
        _pos_count = sum(1 for w in _pos_shift_words if w in user_message)
        result['message_analysis'] = {
            'negative_intensity': min(1.0, _neg_count * 0.2),
            'positive_indicator': _pos_count > 0,
            'likely_focus': '情绪' if _neg_count > 2 else '行为' if '做' in user_message else '认知',
        }

    # 挑战建议
    cps = bs.get_challenge_points(limit=3)
    if cps:
        result['challenge_suggestions'] = [
            {'belief': p, 'strength': round(s, 2), 'reframe': r}
            for p, s, r in cps
        ]

    return result


def cognitive_tool_schema():
    """返回 AGM 认知分析工具的 function calling schema

    AI 可以直接将此 schema 注册为可用工具。
    """
    return {
        'type': 'function',
        'function': {
            'name': 'cognitive_analyze',
            'description': '分析用户的认知三角状态（想法→情绪→行为），'
                          '检测认知断裂点，返回挑战建议。'
                          '在用户表达睡眠焦虑、失眠困扰时调用。',
            'parameters': {
                'type': 'object',
                'properties': {
                    'openid': {
                        'type': 'string',
                        'description': '用户标识'
                    },
                    'user_message': {
                        'type': 'string',
                        'description': '用户最新一条消息，用于实时的情绪-信念关联分析'
                    },
                },
                'required': ['openid']
            }
        }
    }


def profile_summary(openid):
    """供 dp_router 调用的文本摘要（兼容 v1.0/v2.0）"""
    bs = _get(openid)
    text = bs.challenge_text_extended()
    return text + '。' if text and not text.endswith('。') else text


def summary_str(openid):
    """返回可读摘要（兼容 v1.0）"""
    bs = _get(openid)
    legacy = bs.to_legacy_numeric()
    lines = [
        f'自我效能感: {legacy["self_efficacy"]:.0%}',
        f'灾难化预期: {legacy["catastrophic_expect"]:.0%}',
        f'治疗信赖度: {legacy["treatment_trust"]:.0%}',
        f'睡眠努力度: {legacy["sleep_effort"]:.0%}',
    ]
    cps = bs.get_challenge_points(limit=2)
    for p, s, r in cps:
        lines.append(f'可挑战: "{p}"({s:.0%}) → "{r}"')
    return ' | '.join(lines)


# ========== v1.0 兼容的 load/save（备用） ==========

def load(openid):
    """兼容 v1.0 load"""
    return _get(openid).to_legacy_numeric()


def save(openid, beliefs):
    """兼容 v1.0 save"""
    bs = _get(openid)
    for k, v in beliefs.items():
        if k == 'self_efficacy' and v < 0.4 and '我能睡好' in bs.K:
            bs.K['我能睡好'] = v
        elif k == 'catastrophic_expect' and v > 0.6 and '今晚一定又失眠' in bs.K:
            bs.K['今晚一定又失眠'] = v
    bs._save()


def ontology_stats():
    """返回本体库统计信息"""
    onto = _load_ontology()
    return {
        'template_dims': len(onto.get('belief_templates', {})),
        'total_beliefs': sum(len(v) for v in onto.get('belief_templates', {}).values()),
        'contradiction_pairs': len(onto.get('contradiction_pairs', [])),
        'refutations': len(onto.get('refutations', {})),
    }


# ========== 自测 ==========
if __name__ == '__main__':
    print('=== AGM v2.1 固筑度加权最小切除 Self-Test ===\n')

    import os as _os
    _test_path = _os.path.join(BELIEF_DIR, 'test_agm_v21_agm.json')
    if _os.path.exists(_test_path):
        _os.remove(_test_path)

    print(f'本体库: {json.dumps(ontology_stats(), ensure_ascii=False)}')

    # 1. 新用户初始化
    bs = BeliefSystem('test_agm_v21')
    print(f'\n1. Default K ({len(bs.K)} beliefs):')
    for p, s in sorted(bs.K.items()):
        print(f'   "{p}": {s:.0%}')

    # 2. 加权最小切除验证
    # 植入一个矛盾命题，应该切除固筑度最低的
    print('\n2. 加权最小切除测试:')
    print('   尝试植入 "过去不代表未来" (矛盾于"今晚一定又失眠")')
    removed, added = bs.revise("过去不代表未来", 0.7)
    print(f'   切除: {removed}')
    print(f'   新增: {added}')
    remaining_contradictions = any(
        bs._is_contradiction(p, "过去不代表未来")
        for p in bs.K.keys()
    )
    print(f'   剩余矛盾: {remaining_contradictions}')

    # 3. 多次交互后的信念演化
    print('\n3. 连续交互测试（模拟一个焦虑用户的恢复过程）:')
    for turn in range(5):
        if turn < 2:
            update('test_agm_v21', score=30, feedback=-1, mood='焦虑')
            print(f'   T{turn}: 差评 → catastropic={bs.K.get("今晚一定又失眠",0):.0%}')
        else:
            update('test_agm_v21', score=75, feedback=1)
            print(f'   T{turn}: 好评 → self_efficacy={bs.K.get("我能睡好",0):.0%}')

    # 4. 挑战点列表
    print(f'\n4. Top-3 可挑战点:')
    for p, s, r in bs.get_challenge_points(3):
        print(f'   "{p}" ({s:.0%}) → "{r}"')

    # 5. 兼容性验证
    legacy = bs.to_legacy_numeric()
    print(f'\n5. Legacy numeric: {legacy}')
    assert all(0 <= v <= 1 for v in legacy.values())

    summary = summary_str('test_agm_v21')
    print(f'\n6. summary_str: {summary}')

    profile = profile_summary('test_agm_v21')
    print(f'7. profile_summary: {profile}')
    assert '可挑战' in profile, 'AGM challenge text should be present'

    # 8. 验证本体库独立扩展性
    onto = _load_ontology()
    assert len(onto['belief_templates']) >= 7, '本体库应包含 7+ 维度'
    assert len(onto['refutations']) >= 11, '本体库应包含 11+ 反驳命题'

    # 清理
    if _os.path.exists(_test_path):
        _os.remove(_test_path)

    print('\n=== All AGM v2.1 tests PASS! ===')
