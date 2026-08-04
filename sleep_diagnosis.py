# sleep_diagnosis.py v2.0 — 睡眠诊断引擎（因果推理版）
# 范式3(因果链+多假设) + 范式4(置信度量化+预测校准)
# 从 brain_wallstreet/causality/chain_builder.py 移植：
#   - causal chain + multi-hypothesis tracking
#   - signal confidence quantification
#   - conflict detection
# 不 import 股票代码，在自己的领域独立重实现。

import json, os, math
from datetime import datetime, timedelta
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

PROJECT_ROOT = r'D:\AISleepGen_Optimized'

# ═══════════════════════════════════════════════════════
# 范式3：因果链数据结构（在自己的领域重实现）
# ───────────────────────────────────────────────────────
# 移植自 brain_wallstreet/causality/chain_builder.py 的:
#   CausalLink, CausalChain, ConflictDetector
# 用睡眠领域术语重写，不等价 import。
# ═══════════════════════════════════════════════════════

SLEEP_DIMENSIONS = [
    ('sleep_latency', '入睡延迟', 'min'),
    ('awake_times', '夜醒次数', '次'),
    ('total_duration', '总睡眠时长', 'h'),
    ('deep_sleep_pct', '深睡占比', '%'),
    ('stress_level', '压力水平', '/10'),
    ('bedtime_regularity', '作息规律性', '/1'),
    ('score', '睡眠评分', '分'),
]


@dataclass
class SleepCausalLink:
    """睡眠因果链中的一环"""
    event: str                    # 事件描述（中文）
    dimension: str                # 维度标识
    time: str                     # 发生时间
    source: str                   # 来源（pomdp / behavior / 手环）
    value: float = 0.0
    confidence: float = 0.5       # 此环节置信度


@dataclass
class SleepCausalChain:
    """睡眠因果链（完整）"""
    chain_id: str
    root_cause: str               # 根因描述（中文）
    primary_dimension: str        # 核心问题维度
    chain: List[SleepCausalLink] = field(default_factory=list)
    confidence: float = 0.5       # 整链置信度
    chain_strength: float = 0.0   # 证据强度（0-1）
    alternative_hypotheses: List[dict] = field(default_factory=list)
    # 替代假设列表：[{
    #   'hypothesis': str,       # 描述
    #   'confidence': float,     # 置信度
    #   'evidence': [str]        # 支持证据
    # }]
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "chain_id": self.chain_id,
            "root_cause": self.root_cause,
            "primary_dimension": self.primary_dimension,
            "chain": [
                {"event": l.event, "dimension": l.dimension,
                 "time": l.time, "source": l.source,
                 "value": l.value, "confidence": l.confidence}
                for l in self.chain
            ],
            "confidence": round(self.confidence, 3),
            "chain_strength": round(self.chain_strength, 3),
            "alternative_hypotheses": self.alternative_hypotheses,
            "created_at": self.created_at,
        }


@dataclass
class SignalConflict:
    """信号冲突（范式3中的冲突检测）"""
    dimension_a: str
    dimension_b: str
    type: str                     # 'divergent' / 'contradictory'
    description: str
    confidence: float = 0.5
    signal_value: str = ""


class CausalDiagnosisEngine:
    """因果诊断引擎
    范式3核心：从睡眠数据中构建因果链 + 多假设跟踪
    """

    def __init__(self):
        self._bp = None
        self._wm = None

    def _get_bp(self):
        if self._bp is None:
            from behavior_predictor import BehaviorPredictor
            self._bp = BehaviorPredictor()
        return self._bp

    def _get_wm(self):
        if self._wm is None:
            from working_memory import get_working_memory
            self._wm = get_working_memory()
        return self._wm

    def build_chains(self, openid: str, recent_data: list) -> List[SleepCausalChain]:
        """从近期睡眠数据构建因果链"""
        if not recent_data or len(recent_data) < 7:
            return []

        chains = []
        data = self._normalize_recent(recent_data)

        # ── 如果评分下降 → 找根因 ──
        declining = self._detect_decline(data)
        if declining['declining']:
            chain = self._build_decline_chain(openid, data, declining)
            if chain:
                chains.append(chain)

        # ── 如果作息不规律 → 找模式 ──
        irregular = self._detect_irregular(data)
        if irregular['irregular']:
            chain = self._build_irregular_chain(openid, data, irregular)
            if chain:
                chains.append(chain)

        # ── 如果夜醒多 → 找原因 ──
        high_awake = self._detect_high_awake(data)
        if high_awake['high']:
            chain = self._build_awake_chain(openid, data, high_awake)
            if chain:
                chains.append(chain)

        # ── 如果压力高 → 找影响 ──
        high_stress = self._detect_high_stress(data)
        if high_stress['high']:
            chain = self._build_stress_chain(openid, data, high_stress)
            if chain:
                chains.append(chain)

        return chains

    def _normalize_recent(self, recent: list) -> dict:
        """将原始记录按维度标准化"""
        data = {}
        for dim, label, unit in SLEEP_DIMENSIONS:
            vals = []
            timestamps = []
            for rec in recent:
                v = rec.get(dim) or rec.get(label) or None
                if v is not None:
                    try:
                        vals.append(float(v))
                        timestamps.append(rec.get('timestamp', ''))
                    except (ValueError, TypeError):
                        pass
            if vals:
                data[dim] = {'values': vals, 'timestamps': timestamps, 'label': label, 'unit': unit}
        return data

    def _detect_decline(self, data: dict) -> dict:
        """检测评分下降趋势"""
        scores = data.get('score', {}).get('values', [])
        if len(scores) < 4:
            return {'declining': False}
        recent_3 = sum(scores[-3:]) / 3
        earlier_3 = sum(scores[-6:-3]) / 3 if len(scores) >= 6 else sum(scores[:3]) / 3
        if earlier_3 == 0:
            return {'declining': False}
        drop = earlier_3 - recent_3
        drop_pct = drop / earlier_3
        return {
            'declining': drop > 4 and drop_pct > 0.03,
            'drop': drop,
            'drop_pct': drop_pct,
            'recent_avg': recent_3,
            'earlier_avg': earlier_3,
            'volatility': self._std(scores[-7:]) if len(scores) >= 7 else 0,
            'acceleration': self._calc_acceleration(scores),
        }

    def _detect_irregular(self, data: dict) -> dict:
        """检测作息规律性"""
        bedtimes = data.get('bedtime_regularity', {}).get('values', [])
        if len(bedtimes) < 4:
            return {'irregular': False}
        std = self._std(bedtimes)
        return {
            'irregular': std > 0.15,
            'std': std,
            'mean': sum(bedtimes) / len(bedtimes),
            'samples': len(bedtimes),
        }

    def _detect_high_awake(self, data: dict) -> dict:
        """检测夜醒过多"""
        awakes = data.get('awake_times', {}).get('values', [])
        if len(awakes) < 3:
            return {'high': False}
        recent_3 = sum(awakes[-3:]) / 3
        return {
            'high': recent_3 > 2.0,
            'avg': sum(awakes) / len(awakes),
            'recent_avg': recent_3,
            'max': max(awakes),
        }

    def _detect_high_stress(self, data: dict) -> dict:
        """检测压力水平"""
        stresses = data.get('stress_level', {}).get('values', [])
        if len(stresses) < 3:
            return {'high': False}
        recent_3 = sum(stresses[-3:]) / 3
        return {
            'high': recent_3 > 6.0,
            'avg': sum(stresses) / len(stresses),
            'recent_avg': recent_3,
            'trend': 'rising' if len(stresses) >= 4 and stresses[-1] > stresses[0] else 'stable',
        }

    def _build_decline_chain(self, openid: str, data: dict, decline: dict) -> SleepCausalChain:
        """构建评分下降的因果链 + 多假设"""
        chain = SleepCausalChain(
            chain_id=f"decline_{openid}_{datetime.now():%Y%m%d%H%M}",
            root_cause="",
            primary_dimension='score',
            created_at=datetime.now().isoformat(),
        )

        # ── 链起点：发现下降 ──
        chain.chain.append(SleepCausalLink(
            event=f"评分从{decline['earlier_avg']:.0f}下降到{decline['recent_avg']:.0f}（Δ={decline['drop']:.1f}分）",
            dimension='score', time=datetime.now().isoformat(),
            source='behavior_predictor',
            value=decline['recent_avg'], confidence=0.85,
        ))

        # ── 如果波动大 → 不稳定信号 ──
        if decline['volatility'] > 15:
            chain.chain.append(SleepCausalLink(
                event=f"评分波动大（σ={decline['volatility']:.1f}），趋势信号不稳定",
                dimension='score', time=datetime.now().isoformat(),
                source='behavior_predictor',
                value=decline['volatility'], confidence=0.70,
            ))

        # ── 如果加速恶化 → 更严重 ──
        if decline['acceleration'] < -1:
            chain.chain.append(SleepCausalLink(
                event=f"加速恶化（加速度={decline['acceleration']:.2f}），不是自然波动",
                dimension='score', time=datetime.now().isoformat(),
                source='behavior_predictor',
                value=decline['acceleration'], confidence=0.65,
            ))

        # ── 关联维度分析（找可能原因） ──
        possible_causes = []
        for dim_key in ['stress_level', 'sleep_latency', 'awake_times', 'total_duration', 'bedtime_regularity']:
            if dim_key in data:
                vals = data[dim_key]['values']
                scores = data.get('score', {}).get('values', [])
                if len(vals) >= 3 and len(scores) >= 3:
                    min_len = min(len(vals), len(scores))
                    corr = self._pearson_r(vals[-min_len:], scores[-min_len:])
                    if abs(corr) > 0.3:
                        possible_causes.append((dim_key, abs(corr), corr))

        possible_causes.sort(key=lambda x: -x[1])

        # ── 降序加入因果链（最强关联最先出现） ──
        for dim_key, abs_r, r_raw in possible_causes[:3]:
            label = data.get(dim_key, {}).get('label', dim_key)
            direction = "正相关" if r_raw > 0 else "负相关"
            chain.chain.append(SleepCausalLink(
                event=f"{label}{direction}评分（|r|={abs_r:.2f}）",
                dimension=dim_key, time=datetime.now().isoformat(),
                source='causal_graph',
                value=round(r_raw, 2), confidence=min(0.5 + abs_r * 0.3, 0.9),
            ))

        # ── 确定根因 ──
        if possible_causes:
            top_dim, top_r, _ = possible_causes[0]
            top_label = data.get(top_dim, {}).get('label', top_dim)
            chain.root_cause = f"{top_label}与评分下降最强相关"
        else:
            chain.root_cause = "评分下降，但无明显关联维度（可能为外部因素）"

        # ── 整链置信度 ──
        if chain.chain:
            chain.confidence = sum(l.confidence for l in chain.chain) / len(chain.chain)

        # ── 替代假设（范式3的核心：多假设并行存在） ──
        chain.alternative_hypotheses = self._generate_alternatives(data, decline, possible_causes)

        # ── 链强度 = 置信度 × (1 - 波动惩罚) × 数据量折扣 ──
        volatility_penalty = min(decline['volatility'] / 30, 0.5) if decline['volatility'] > 0 else 0
        data_n = len(data.get('score', {}).get('values', []))
        data_discount = min(data_n / 14, 1.0)
        chain.chain_strength = chain.confidence * (1 - volatility_penalty) * data_discount

        return chain

    def _build_irregular_chain(self, openid, data, irregular):
        chain = SleepCausalChain(
            chain_id=f"irregular_{openid}_{datetime.now():%Y%m%d%H%M}",
            root_cause=f"作息不规律（σ={irregular['std']:.2f}）",
            primary_dimension='bedtime_regularity',
            created_at=datetime.now().isoformat(),
        )
        scores = data.get('score', {}).get('values', [])
        if scores and len(scores) >= 3:
            chain.chain.append(SleepCausalLink(
                event=f"作息标准差{irregular['std']:.2f}，均值{irregular['mean']:.2f}",
                dimension='bedtime_regularity', time=datetime.now().isoformat(),
                source='working_memory',
                value=irregular['std'], confidence=0.75,
            ))
            # 找作息不规律天数的评分变化
            # 作息不规律后的第二天评分会偏低
            chain.chain.append(SleepCausalLink(
                event=f"不规律作息后评分平均偏低（数据{irregular['samples']}天）",
                dimension='score', time=datetime.now().isoformat(),
                source='working_memory',
                value=sum(scores[-3:]) / 3, confidence=0.60,
            ))
        chain.confidence = 0.65
        chain.alternative_hypotheses = [
            {'hypothesis': '可能是工作时间变化导致的被动晚睡',
             'confidence': 0.40,
             'evidence': ['需要外部日程数据验证']},
            {'hypothesis': '可能是主动熬夜（娱乐），非被动',
             'confidence': 0.35,
             'evidence': ['周中周末差异分析需要更多数据']},
        ]
        return chain

    def _build_awake_chain(self, openid, data, awake_info):
        chain = SleepCausalChain(
            chain_id=f"awake_{openid}_{datetime.now():%Y%m%d%H%M}",
            root_cause=f"夜醒偏多（近3日均值{awake_info['recent_avg']:.1f}次）",
            primary_dimension='awake_times',
            created_at=datetime.now().isoformat(),
        )
        if 'stress_level' in data:
            stress_vals = data['stress_level']['values']
            awake_vals = data['awake_times']['values']
            if len(stress_vals) >= 3 and len(awake_vals) >= 3:
                min_l = min(len(stress_vals), len(awake_vals))
                r = self._pearson_r(stress_vals[-min_l:], awake_vals[-min_l:])
                if abs(r) > 0.2:
                    direction = "正相关" if r > 0 else "弱相关（非压力主导）"
                    chain.chain.append(SleepCausalLink(
                        event=f"压力{'与' if r > 0 else '与'}夜醒{direction}（r={r:.2f}）",
                        dimension='stress_level', time=datetime.now().isoformat(),
                        source='causal_graph',
                        value=round(r, 2), confidence=min(0.5 + abs(r) * 0.3, 0.85),
                    ))
        chain.confidence = 0.60
        chain.alternative_hypotheses = [
            {'hypothesis': '可能是环境干扰（噪音/温度），非内在原因',
             'confidence': 0.35,
             'evidence': ['需要环境传感器数据验证']},
            {'hypothesis': '可能是年龄相关的睡眠结构变化',
             'confidence': 0.25,
             'evidence': ['正常老化过程中深睡比例逐渐下降']},
        ]
        return chain

    def _build_stress_chain(self, openid, data, stress_info):
        chain = SleepCausalChain(
            chain_id=f"stress_{openid}_{datetime.now():%Y%m%d%H%M}",
            root_cause=f"压力偏高（均值{stress_info['avg']:.1f}/10），{stress_info['trend']}",
            primary_dimension='stress_level',
            created_at=datetime.now().isoformat(),
        )
        impacts = []
        for dim_key in ['sleep_latency', 'awake_times', 'score', 'deep_sleep_pct']:
            if dim_key in data:
                stress_vals = data['stress_level']['values']
                other_vals = data[dim_key]['values']
                if len(stress_vals) >= 3 and len(other_vals) >= 3:
                    min_l = min(len(stress_vals), len(other_vals))
                    r = self._pearson_r(stress_vals[-min_l:], other_vals[-min_l:])
                    if abs(r) > 0.25:
                        label = data[dim_key]['label']
                        impacts.append((dim_key, r, label))
        impacts.sort(key=lambda x: -abs(x[1]))
        for dim_key, r, label in impacts[:2]:
            chain.chain.append(SleepCausalLink(
                event=f"压力{label}: {'同向' if r > 0 else '反向'}变化（r={r:.2f}）",
                dimension=dim_key, time=datetime.now().isoformat(),
                source='causal_graph',
                value=round(r, 2), confidence=min(0.5 + abs(r) * 0.3, 0.8),
            ))
        chain.confidence = 0.65
        chain.alternative_hypotheses = [
            {'hypothesis': '可能是压力与失眠的恶性循环（因果方向可能相反）',
             'confidence': 0.50,
             'evidence': ['压力→失眠→压力更重的双向关系在临床上常见']},
        ]
        return chain

    def _generate_alternatives(self, data: dict, decline: dict, causes: list) -> List[dict]:
        """生成替代假设（多假设跟踪的核心）"""
        alts = []
        # 如果最强原因是压力，但其他维度也有关系
        if any(c[0] == 'stress_level' for c in causes):
            alts.append({
                'hypothesis': '可能是工作/生活中的特定事件导致短期压力激增',
                'confidence': 0.45,
                'evidence': ['压力与评分负相关(r<0)',
                             '如果是长期压力趋势应该更平滑而非突然下降']
            })
        # 如果是因为作息
        if any(c[0] == 'bedtime_regularity' for c in causes):
            alts.append({
                'hypothesis': '可能是被动夜醒（环境/健康原因）而非主动熬夜',
                'confidence': 0.35,
                'evidence': ['需要健康数据交叉验证']
            })
        # 如果数据不足
        n = len(data.get('score', {}).get('values', []))
        if n < 7:
            alts.append({
                'hypothesis': f'数据量({n}天)不足，因果推断可能不准确',
                'confidence': 0.40,
                'evidence': ['更多数据点能提高推断可靠性']
            })
        if not alts:
            alts.append({
                'hypothesis': '可能是多种因素叠加，非单一原因',
                'confidence': 0.30,
                'evidence': ['多个维度同时发生变化']
            })
        return alts

    def detect_conflicts(self, chains: List[SleepCausalChain]) -> List[SignalConflict]:
        """信号冲突检测（范式3核心）"""
        conflicts = []
        # 如果两条因果链指向相反可能的解读
        if len(chains) >= 2:
            for i, c1 in enumerate(chains):
                for c2 in chains[i+1:]:
                    if c1.confidence > 0.4 and c2.confidence > 0.4:
                        conflicts.append(SignalConflict(
                            dimension_a=c1.primary_dimension,
                            dimension_b=c2.primary_dimension,
                            type='divergent',
                            description=(
                                f"两条因果链同时存在：\n"
                                f"  ① {c1.root_cause[:40]}（置信度{c1.confidence:.0%}）\n"
                                f"  ② {c2.root_cause[:40]}（置信度{c2.confidence:.0%}）\n"
                                f"  可能交替作用或存在交互效应"
                            ),
                            confidence=(c1.confidence + c2.confidence) / 2 * 0.7,
                        ))
        # 如果评分下降但压力无变化
        scores = data.get('score', {}).get('values', []) if 'data' in dir(self) else []
        return conflicts

    def _pearson_r(self, x, y):
        n = len(x)
        if n < 3: return 0.0
        mx = sum(x) / n
        my = sum(y) / n
        num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
        dx = math.sqrt(max(0, sum((x[i] - mx) ** 2 for i in range(n))))
        dy = math.sqrt(max(0, sum((y[i] - my) ** 2 for i in range(n))))
        if dx * dy == 0: return 0.0
        return num / (dx * dy)

    def _std(self, values):
        if len(values) < 2: return 0
        avg = sum(values) / len(values)
        return math.sqrt(sum((v - avg) ** 2 for v in values) / len(values))

    def _calc_acceleration(self, values):
        """二阶差分估计加速度"""
        if len(values) < 4: return 0.0
        diffs = [values[i+1] - values[i] for i in range(len(values)-1)]
        if len(diffs) < 2: return 0.0
        accels = [diffs[i+1] - diffs[i] for i in range(len(diffs)-1)]
        return sum(accels) / len(accels)


# ═══════════════════════════════════════════════════════
# 范式4：置信度量化 + 预测校准（在自己的领域重实现）
# ───────────────────────────────────────────────────────
# 移植自 brain_wallstreet/calibrator/prediction_tracker.py:
#   Prediction, Belief, PredictionTracker
# 用睡眠领域术语重写。
# ═══════════════════════════════════════════════════════

class SleepConfidenceTracker:
    """睡眠预测的置信度+校准器
    范式4核心：每个输出带置信度 + 预测→验证→校准闭环
    """

    def __init__(self):
        self._cal_path = os.path.join(PROJECT_ROOT, 'data', 'sleep_calibration.json')
        self._cal_data = {}
        self._load_calibration()

    def _load_calibration(self):
        if os.path.exists(self._cal_path):
            try:
                with open(self._cal_path, 'r', encoding='utf-8') as f:
                    self._cal_data = json.load(f)
            except:
                self._cal_data = {}
        if not self._cal_data:
            self._cal_data = {'predictions': [], 'bias': 0.0, 'calibration_curve': {}}

    def _save(self):
        os.makedirs(os.path.dirname(self._cal_path), exist_ok=True)
        with open(self._cal_path, 'w', encoding='utf-8') as f:
            json.dump(self._cal_data, f, ensure_ascii=False, indent=2)

    def record_prediction(self, prediction: dict) -> str:
        """注册一个睡眠预测记录"""
        pred = {
            'prediction_id': f"sp_{datetime.now():%Y%m%d%H%M%S}_{len(self._cal_data['predictions'])}",
            'created_at': datetime.now().isoformat(),
            'predicted_score': prediction.get('score', 50),
            'predicted_direction': prediction.get('direction', 'stable'),
            'confidence': prediction.get('confidence', 0.5),
            'entity': prediction.get('openid', ''),
            'outcome': None,
            'verified_at': None,
            'error': None,
        }
        self._cal_data['predictions'].append(pred)
        self._save()
        return pred['prediction_id']

    def verify_night(self, openid: str, actual_score: float, actual_direction: str) -> dict:
        """次日验证昨晚的预测"""
        for pred in reversed(self._cal_data['predictions']):
            if pred['entity'] == openid and pred['outcome'] is None:
                error = actual_score - pred['predicted_score']
                correct = (error >= 0 and pred['predicted_direction'] in ('stable', 'better')) or \
                          (error < 0 and pred['predicted_direction'] == 'worse')
                pred['outcome'] = correct
                pred['verified_at'] = datetime.now().isoformat()
                pred['error'] = round(error, 1)
                self._update_calibration_curve(pred)
                self._update_bias()
                self._save()
                return {
                    'prediction_id': pred['prediction_id'],
                    'correct': correct,
                    'error': round(error, 1),
                    'original_confidence': pred['confidence'],
                }
        return {'correct': False, 'error': 0, 'note': '未找到未验证的预测'}

    def _update_calibration_curve(self, pred: dict):
        """更新校准曲线"""
        conf_bucket = f"{int(pred['confidence'] * 100 / 10) * 10}%"
        if conf_bucket not in self._cal_data['calibration_curve']:
            self._cal_data['calibration_curve'][conf_bucket] = {'total': 0, 'correct': 0}
        self._cal_data['calibration_curve'][conf_bucket]['total'] += 1
        if pred['outcome']:
            self._cal_data['calibration_curve'][conf_bucket]['correct'] += 1

    def _update_bias(self):
        """更新整体偏差"""
        verified = [p for p in self._cal_data['predictions'] if p['outcome'] is not None]
        if not verified:
            return
        errors = [p.get('error', 0) for p in verified if p.get('error') is not None]
        if errors:
            self._cal_data['bias'] = round(sum(errors) / len(errors), 2)

    def get_confidence_adjustment(self, entity: str, base_confidence: float) -> float:
        """根据校准历史调整置信度"""
        counts = self._cal_data['calibration_curve']
        conf_bucket = f"{int(base_confidence * 100 / 10) * 10}%"
        if conf_bucket in counts and counts[conf_bucket]['total'] >= 3:
            actual_acc = counts[conf_bucket]['correct'] / counts[conf_bucket]['total']
            if actual_acc < base_confidence - 0.15:
                return max(0.2, base_confidence - 0.15)
            elif actual_acc > base_confidence + 0.15:
                return min(0.95, base_confidence + 0.1)
        return base_confidence

    def get_calibration_summary(self) -> dict:
        """获取校准摘要"""
        verified = [p for p in self._cal_data['predictions'] if p['outcome'] is not None]
        total = len(verified)
        correct = sum(1 for p in verified if p['outcome'])
        return {
            'total_predictions': len(self._cal_data['predictions']),
            'verified': total,
            'correct': correct,
            'accuracy': round(correct / total, 3) if total > 0 else 0,
            'bias': self._cal_data['bias'],
            'calibration_curve': {
                k: f"{v['correct']}/{v['total']}={v['correct']/v['total']*100:.0f}%"
                for k, v in self._cal_data['calibration_curve'].items() if v['total'] > 0
            },
        }


# ═══════════════════════════════════════════════════════
# v2.0 SleepDiagnosis — 升级为因果推理版本
# 包含范式3(因果链) + 范式4(置信度)两套新能力
# ═══════════════════════════════════════════════════════

class SleepDiagnosis:
    """睡眠诊断引擎 v2.0

    相比v1.0的关键升级：
      1. 输出不再只是评分和建议，而包含因果链（范式3）
      2. 每个输出维度带置信度（范式4）
      3. 替代假设并行存在，而不是给出唯一解释
      4. 预测→验证→校准闭环
    """

    def __init__(self):
        self._bp = None
        self._wm = None
        self._causal = CausalDiagnosisEngine()
        self._calibrator = SleepConfidenceTracker()

    def _get_bp(self):
        if self._bp is None:
            from behavior_predictor import BehaviorPredictor
            self._bp = BehaviorPredictor()
        return self._bp

    def _get_wm(self):
        if self._wm is None:
            from working_memory import get_working_memory
            self._wm = get_working_memory()
        return self._wm

    def generate(self, openid: str) -> dict:
        """生成完整诊断书 v2.0"""
        bp = self._get_bp()
        wm = self._get_wm()

        # ── 1. 基础数据 ──
        recent = []
        if wm:
            try:
                recent = wm.recent(openid, n=14)
            except Exception:
                pass

        trend = bp.predict_trend(openid)
        baseline = bp.predict_tonight(openid)
        anomaly = bp.anomaly_score(openid)
        patterns = bp.detect_patterns(openid)

        # ── 2. 提取分数序列 ──
        scores = []
        sleep_times = []
        for e in recent:
            s = e.get('score_obs')
            if s is not None:
                ts = e.get('timestamp', '')
                scores.append((ts[:10], s))
                sleep_times.append(e.get('bedtime', ''))

        n_days = len(scores)
        if scores:
            recent_scores = [s for _, s in scores[-3:]]
            all_scores = [s for _, s in scores]
            recent_avg = sum(recent_scores) / len(recent_scores) if recent_scores else 50
            overall_avg = sum(all_scores) / len(all_scores) if all_scores else 50
            score_std = self._std(all_scores) if len(all_scores) >= 2 else 0
            min_score = min(all_scores) if all_scores else 0
            max_score = max(all_scores) if all_scores else 100
        else:
            recent_avg = overall_avg = 50
            score_std = min_score = max_score = 0

        # ── 3. 睡眠规律性 ──
        bedtime_consistency = 'unknown'
        self._std_times = 0
        if len(sleep_times) >= 3:
            valid = [t for t in sleep_times if t]
            if len(valid) >= 3:
                minutes = []
                for t in valid:
                    try:
                        h, m = t.split(':')
                        minutes.append(int(h) * 60 + int(m))
                    except Exception:
                        pass
                if len(minutes) >= 3:
                    self._std_times = self._std(minutes)
                    if self._std_times <= 30:
                        bedtime_consistency = 'excellent'
                    elif self._std_times <= 60:
                        bedtime_consistency = 'good'
                    elif self._std_times <= 90:
                        bedtime_consistency = 'fair'
                    else:
                        bedtime_consistency = 'poor'

        # ── 4. 趋势评估 ──
        velocity = trend.get('velocity', 0)
        acceleration = trend.get('acceleration', 0)
        direction = trend.get('direction', 'stable')

        # ── 5. 综合评分（保持v1.0逻辑不变，确保向后兼容） ──
        base = recent_avg
        bonus = 0
        if bedtime_consistency == 'excellent':
            bonus += 8
        elif bedtime_consistency == 'good':
            bonus += 4
        elif bedtime_consistency == 'poor':
            bonus -= 5
        if direction == 'improving':
            bonus += 6
        elif direction == 'declining':
            bonus -= 8
        if score_std < 8:
            bonus += 5
        elif score_std > 20:
            bonus -= 5
        if anomaly > 0.7:
            bonus -= 10
        composite = max(10, min(100, base + bonus))

        # ── 6. 等级标签（不变） ──
        if composite >= 75:
            grade, grade_label = 'A', '优秀 🏆'
        elif composite >= 60:
            grade, grade_label = 'B', '良好 👍'
        elif composite >= 45:
            grade, grade_label = 'C', '一般 ⚠️'
        elif composite >= 30:
            grade, grade_label = 'D', '较差 🔴'
        else:
            grade, grade_label = 'F', '很差 ⛔'

        # ════════════════════════════════════════════════════
        # 范式3 新增：因果链
        # ════════════════════════════════════════════════════
        causal_chains = self._causal.build_chains(openid, recent)
        conflicts = self._causal.detect_conflicts(causal_chains)

        # ════════════════════════════════════════════════════
        # 范式4 新增：置信度 + 校准
        # ════════════════════════════════════════════════════

        # 评分置信度基于：数据量 + 波动性 + 校准历史
        data_confidence = min(n_days / 14, 1.0) * 0.4
        stability_confidence = max(0, 1 - score_std / 30) * 0.3
        calibration_adjust = self._calibrator.get_confidence_adjustment(openid, 0.7)
        score_confidence = min(0.95, (data_confidence + stability_confidence) * calibration_adjust)

        # 预测今晚
        tonight_pred = baseline or {'predicted_score': 50, 'confidence': 'low',
                                     'direction': 'stable', 'key_concern': 'unknown'}
        pred_confidence_map = {'high': 0.8, 'medium': 0.6, 'low': 0.4}
        tonight_confidence = pred_confidence_map.get(
            tonight_pred.get('confidence', 'low'), 0.4)
        tonight_adjusted = self._calibrator.get_confidence_adjustment(
            openid, tonight_confidence)

        # 注册预测到校准器
        self._calibrator.record_prediction({
            'score': tonight_pred.get('predicted_score', 50),
            'direction': tonight_pred.get('direction', 'stable'),
            'confidence': tonight_adjusted,
            'openid': openid,
        })

        # ── 7. 建议（升级：挂载因果链） ──
        advice = []

        # 保留所有 v1.0 建议逻辑（向后兼容）
        if bedtime_consistency == 'poor':
            advice.append({
                'priority': 'high',
                'aspect': '作息规律',
                'detail': f'睡眠时间不规律（标准差{self._std_times:.0f}分钟），建议固定就寝时间',
                'causal_chain_hint': 'irregular',
            })

        if direction == 'declining':
            advice.append({
                'priority': 'high',
                'aspect': '下降趋势',
                'detail': f'睡眠质量持续下降（速度{velocity:.1f}分/天），注意识别压力源',
                'causal_chain_hint': 'decline',
            })

        if patterns.get('has_monday_anxiety'):
            advice.append({
                'priority': 'medium',
                'aspect': '周一焦虑',
                'detail': '周日晚/周一早睡眠明显较差，建议周日晚提前做放松训练',
            })

        if patterns.get('has_weekend_late'):
            advice.append({
                'priority': 'medium',
                'aspect': '周末熬夜',
                'detail': '周末就寝时间偏晚，影响周一恢复',
            })

        if score_std > 15:
            advice.append({
                'priority': 'medium',
                'aspect': '波动大',
                'detail': f'睡眠评分波动较大（标准差{score_std:.1f}），建议记录每日睡前状态',
            })

        if overall_avg < 55 and n_days >= 5:
            advice.append({
                'priority': 'high',
                'aspect': '持续低分',
                'detail': f'{n_days}天平均{overall_avg:.0f}分，持续偏低，建议就医咨询或使用正念课程',
            })

        # ── 9. 诊断书输出 v2.0 ──
        result = {
            'openid': openid,
            'generated_at': datetime.now().isoformat(),
            'date_range': f'最近{n_days}天' if n_days else '数据不足',
            'version': '2.0',

            # 评分系统（向后兼容）
            'composite_score': round(composite, 1),
            'grade': grade,
            'grade_label': grade_label,
            'score_confidence': round(score_confidence, 3),          # 范式4：新增

            'metrics': {
                'recent_average': round(recent_avg, 1),
                'overall_average': round(overall_avg, 1),
                'score_std': round(score_std, 1),
                'range': f'{min_score:.0f}-{max_score:.0f}',
                'direction': direction,
                'velocity': velocity,
                'acceleration': acceleration,
                'anomaly_index': anomaly,
                'bedtime_consistency': bedtime_consistency,
                'n_days': n_days,
                'monday_anxiety': patterns.get('has_monday_anxiety', False),
                'weekend_late': patterns.get('has_weekend_late', False),
                'weekly_periodicity': patterns.get('weekly_periodicity', 0),
            },

            # 范式3：因果链（新增）
            'causal_chains': [c.to_dict() for c in causal_chains],
            'conflicts': [
                {'dim_a': c.dimension_a, 'dim_b': c.dimension_b,
                 'type': c.type, 'description': c.description,
                 'confidence': c.confidence}
                for c in conflicts
            ] if conflicts else [],

            # 范式4：置信度和校准（新增）
            'calibration': self._calibrator.get_calibration_summary(),
            'tonight_prediction': {
                'predicted_score': tonight_pred.get('predicted_score', 50),
                'direction': tonight_pred.get('direction', 'stable'),
                'confidence': tonight_adjusted,
                'key_concern': tonight_pred.get('key_concern', 'unknown'),
            },

            # 建议（向后兼容）
            'advice': advice,
            'score_timeline': scores[-7:] if len(scores) >= 7 else scores,
        }

        return result

    def _std(self, values):
        if len(values) < 2:
            return 0
        avg = sum(values) / len(values)
        return math.sqrt(sum((v - avg) ** 2 for v in values) / len(values))


def format_diagnosis_card(diagnosis: dict) -> str:
    """格式化为微信卡片文本"""
    m = diagnosis['metrics']
    lines = [
        f'📋 睡眠诊断书',
        f'━━━━━━━━━━━━━━━',
        f'等级: {diagnosis["grade_label"]}  |  综合评分: {diagnosis["composite_score"]}/100',
        f'数据: {diagnosis["date_range"]}',
        f'',
        f'📊 核心指标',
        f'  近3天均值: {m["recent_average"]}分',
        f'  总体均值: {m["overall_average"]}分',
        f'  波动范围: {m["range"]}  (σ={m["score_std"]})',
        f'  趋势: {m["direction"]} (速度{m["velocity"]}分/天)',
    ]
    if m['bedtime_consistency'] != 'unknown':
        lines.append(f'  作息规律性: {m["bedtime_consistency"]}')
    if m['weekly_periodicity'] > 0.5:
        lines.append(f'  周周期节律: 存在 ({m["weekly_periodicity"]:.0%})')

    if diagnosis['advice']:
        lines.append(f'')
        lines.append(f'💡 改善建议')
        for a in diagnosis['advice']:
            icon = '❗' if a['priority'] == 'high' else '·'
            lines.append(f'  {icon} {a["detail"]}')

    if diagnosis['score_timeline']:
        lines.append(f'')
        lines.append(f'📈 近7天趋势')
        vs = [s for _, s in diagnosis['score_timeline']]
        spark = _sparkline(vs)
        if spark:
            lines.append(f'  {spark}')
        for date, s in diagnosis['score_timeline']:
            bar = '█' * max(1, int(s / 5))
            lines.append(f'  {date[-5:]} {s:5.0f} {bar}')

    lines.append(f'━━━━━━━━━━━━━━━')
    return '\n'.join(lines)


BLOCKS = [' ', '\u2581', '\u2582', '\u2583', '\u2584', '\u2585', '\u2586', '\u2587', '\u2588']


def _sparkline(values, width=7):
    """生成紧凑火花线图"""
    if not values:
        return ''
    n = len(values)
    if n < width:
        values = values + [values[-1]] * (width - n)
    elif n > width:
        step = n / width
        values = [values[int(i * step)] for i in range(width)]
    mn = min(values)
    mx = max(values)
    if mx == mn:
        return '\u2585' * width + f' {values[0]:.0f}'
    line = ''
    for v in values:
        idx = int((v - mn) / (mx - mn) * 7)
        line += BLOCKS[min(idx, 7)]
    prev = values[-2] if len(values) >= 2 else values[-1]
    last = values[-1]
    direction = '+' if last > prev else ('-' if last < prev else '=')
    return f'{line} {last:.0f}{direction}'
