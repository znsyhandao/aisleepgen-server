# sleep_siege_engine.py v1.0 — 睡前预测引擎
# 核心：在用户睡前30分钟预测今晚睡眠质量
# 输入：今日上下文 + 历史趋势 + 行为模式
# 输出：预测评分 + 置信区间 + 风险因子排名
#
# 集成点：
#   - behavior_predictor.predict_tonight()  — 基于历史趋势的基线预测
#   - working_memory.recent()               — 近期上下文（压力/活动/咖啡等）
#   - intent_engine.classify()              — 当日对话意图提取
#   - pomdp_learner.get_belief()            — 当前POMDP信念状态

import json, os, math
from datetime import datetime, timedelta
from collections import defaultdict

# ============ 上下文信号采集 ============

# 风险因子权重（可调整，后续可A/B测）
RISK_FACTORS = {
    'stress_high':        -15,   # 今天压力大
    'stress_low':          +5,   # 今天轻松
    'activity_low':        -8,   # 今天基本没动
    'activity_high':       +10,  # 今天运动充足
    'caffeine_late':       -12,  # 下午喝咖啡/茶
    'caffeine_none':        0,   # 没喝
    'sleep_debt':          -10,  # 连续睡眠不足
    'sleep_debt_severe':   -20,  # 严重睡眠债
    'anxiety_today':       -12,  # 今天有焦虑情绪
    'anxiety_mild':         -5,  # 轻微焦虑
    'mood_good':            +8,  # 情绪好
    'mood_flat':             0,  # 情绪平稳
    'bedtime_late_yesterday': -8, # 昨天睡得晚
    'wake_early_yesterday':   +5, # 昨天自然醒（可能说明睡眠充足）
    'nap_afternoon':          -5, # 下午补觉
    'nap_none':                0, # 没补觉
    'meal_late':              -6, # 晚饭太晚
    'meal_heavy':             -8, # 吃太饱
    'alcohol':               -15, # 喝酒了
    'workout_evening':        +5, # 晚上运动
    'workout_none':          -3,  # 今天完全没运动
    'monday':                 -5, # 周一综合症
    'weekend':                +8, # 周末（可能睡得更自由但也可能熬夜）
    'period_start':           -8, # 生理期（如果用户标记）
    'illness':               -20, # 生病
    'seasonal_spring':        0,
    'seasonal_winter':        -3,
}

# 风险因子名（中文说明）
RISK_LABELS = {
    'stress_high': '今天压力较大',
    'stress_low': '今天压力较小',
    'activity_low': '今天运动不足',
    'activity_high': '今天充分运动',
    'caffeine_late': '下午摄入了咖啡因',
    'sleep_debt': '已有睡眠债累积',
    'sleep_debt_severe': '严重睡眠债',
    'anxiety_today': '今天有焦虑情绪',
    'mood_good': '今天心情不错',
    'bedtime_late_yesterday': '昨天睡得晚',
    'wake_early_yesterday': '昨天自然醒',
    'nap_afternoon': '下午补过觉',
    'meal_late': '晚饭吃得太晚',
    'alcohol': '今天饮酒了',
    'monday': '周一',
    'weekend': '周末',
    'illness': '身体不适',
    'period_start': '生理期',
}


class SiegePredictor:
    """睡前线报预测引擎（Siege = 睡眠围城）"""

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

    def collect_context(self, openid: str) -> dict:
        """采集当日上下文特征"""
        ctx = {
            'stress': 5,
            'activity': 'medium',
            'caffeine': 'none',
            'mood': 'flat',
            'anxiety': 0,
            'meal_time': 'normal',
            'alcohol': False,
            'nap': False,
            'illness': False,
            'period': False,
            'workout': 'none',
        }

        # 1. 从working_memory获取近几日数据
        wm = self._get_wm()
        if wm:
            try:
                recent = wm.recent(openid, n=7)
                if recent:
                    latest = recent[-1] if recent else {}
                    ctx['stress'] = latest.get('stress', 5)
                    ctx['mood'] = latest.get('mood', 'flat')
                    ctx['anxiety'] = latest.get('anxiety', 0)
                    ctx['alcohol'] = latest.get('alcohol', False)
                    ctx['illness'] = latest.get('illness', False)
                    ctx['workout'] = latest.get('workout', 'none')
                    ctx['caffeine'] = latest.get('caffeine', 'none')
                    ctx['activity'] = latest.get('activity', 'medium')
                    ctx['nap'] = latest.get('nap', False)
            except Exception:
                pass

        # 2. 从state_context获取时序状态
        if wm:
            try:
                sig = wm.temporal_signature(openid)
                ctx['sleep_debt'] = sig.get('volatility', 0) > 15
                ctx['velocity'] = sig.get('velocity', 0)
            except Exception:
                ctx['sleep_debt'] = False

        # 3. 推断当日时间因素
        now = datetime.now()
        ctx['is_monday'] = now.weekday() == 0
        ctx['is_weekend'] = now.weekday() >= 5

        # 4. 获取POMDP信念（如果有）
        try:
            from pomdp_learner import get_pomdp
            pomdp = get_pomdp()
            if pomdp:
                belief = pomdp.get_belief(openid)
                if isinstance(belief, dict):
                    ctx['pomdp_score'] = belief.get('expected_score', 50)
                    ctx['pomdp_entropy'] = belief.get('entropy', 0.5)
        except Exception:
            pass

        return ctx

    def compute_risk_factors(self, context: dict) -> list:
        """根据上下文计算风险因子列表（带权重和说明）"""
        factors = []

        # 压力
        s = context.get('stress', 5)
        if s >= 8:
            factors.append(('stress_high', RISK_FACTORS['stress_high'], RISK_LABELS['stress_high']))
        elif s <= 3:
            factors.append(('stress_low', RISK_FACTORS['stress_low'], RISK_LABELS['stress_low']))

        # 运动
        act = context.get('activity', 'medium')
        if act == 'low':
            factors.append(('activity_low', RISK_FACTORS['activity_low'], RISK_LABELS['activity_low']))
        elif act == 'high':
            factors.append(('activity_high', RISK_FACTORS['activity_high'], RISK_LABELS['activity_high']))

        # 咖啡因
        caf = context.get('caffeine', 'none')
        if caf in ('late_afternoon', 'evening', 'yes'):
            factors.append(('caffeine_late', RISK_FACTORS['caffeine_late'], RISK_LABELS['caffeine_late']))

        # 情绪
        mood = context.get('mood', 'flat')
        if mood == 'good':
            factors.append(('mood_good', RISK_FACTORS['mood_good'], RISK_LABELS['mood_good']))

        # 焦虑
        anxiety = context.get('anxiety', 0)
        if anxiety >= 7:
            factors.append(('anxiety_today', RISK_FACTORS['anxiety_today'], RISK_LABELS['anxiety_today']))
        elif anxiety >= 4:
            factors.append(('anxiety_mild', RISK_FACTORS['anxiety_mild'], '轻微焦虑'))

        # 日期因素
        if context.get('is_monday'):
            factors.append(('monday', RISK_FACTORS['monday'], RISK_LABELS['monday']))
        if context.get('is_weekend'):
            factors.append(('weekend', RISK_FACTORS['weekend'], RISK_LABELS['weekend']))

        # 睡眠债
        if context.get('sleep_debt'):
            vol = context.get('velocity', 0)
            if vol < -10:
                factors.append(('sleep_debt_severe', RISK_FACTORS['sleep_debt_severe'], RISK_LABELS['sleep_debt_severe']))
            else:
                factors.append(('sleep_debt', RISK_FACTORS['sleep_debt'], RISK_LABELS['sleep_debt']))

        # 饮酒
        if context.get('alcohol'):
            factors.append(('alcohol', RISK_FACTORS['alcohol'], RISK_LABELS['alcohol']))

        # 补觉
        if context.get('nap'):
            factors.append(('nap_afternoon', RISK_FACTORS['nap_afternoon'], RISK_LABELS['nap_afternoon']))

        # 生病
        if context.get('illness'):
            factors.append(('illness', RISK_FACTORS['illness'], RISK_LABELS['illness']))

        # 锻炼
        workout = context.get('workout', 'none')
        if workout in ('evening', 'yes'):
            factors.append(('workout_evening', RISK_FACTORS['workout_evening'], '晚上运动了'))
        elif workout == 'none':
            factors.append(('workout_none', RISK_FACTORS['workout_none'], '今天没运动'))

        return factors

    def predict(self, openid: str) -> dict:
        """执行睡前预测"""
        bp = self._get_bp()

        # 1. 基线预测（仅基于历史趋势）
        baseline = bp.predict_tonight(openid)
        trend = bp.predict_trend(openid)

        # 2. 采集当日上下文
        context = self.collect_context(openid)

        # 3. 计算风险因子
        risk_factors = self.compute_risk_factors(context)

        # 4. 修正预测：基线 + 风险因子调整
        adjustment = sum(w for _, w, _ in risk_factors)
        adjusted_score = baseline['score'] + adjustment
        adjusted_score = max(10, min(100, adjusted_score))

        # 5. 置信度修正：信源越多越自信
        n_signals = len(risk_factors)
        data_boost = min(0.25, n_signals * 0.03)
        confidence = min(1.0, baseline['confidence'] + data_boost)

        # 6. 确定预警级别
        if adjusted_score < 35:
            alert_level = 'red'       # 红色预警
        elif adjusted_score < 50:
            alert_level = 'yellow'    # 黄色警示
        elif adjusted_score < 65:
            alert_level = 'green'     # 绿色正常
        else:
            alert_level = 'blue'      # 蓝色优秀

        # 7. 风险因子排名（绝对值从大到小）
        risk_factors.sort(key=lambda x: -abs(x[1]))

        # 8. 推荐干预
        interventions = []
        if alert_level in ('red', 'yellow'):
            for key, _, label in risk_factors:
                if key == 'stress_high':
                    interventions.append({'type': 'breathing', 'reason': f'{label}，推荐呼吸训练'})
                elif key == 'anxiety_today' or key == 'anxiety_mild':
                    interventions.append({'type': 'meditation', 'reason': f'{label}，推荐冥想'})
                elif key == 'caffeine_late':
                    interventions.append({'type': 'hydrate', 'reason': f'{label}，多喝水加速代谢'})
                elif key == 'sleep_debt' or key == 'sleep_debt_severe':
                    interventions.append({'type': 'early_bed', 'reason': f'{label}，建议提前30分钟上床'})
                elif key == 'alcohol':
                    interventions.append({'type': 'hydrate', 'reason': f'{label}，睡前多喝水'})
                elif key == 'activity_low':
                    interventions.append({'type': 'gentle_stretch', 'reason': f'{label}，睡前做5分钟拉伸'})
                elif key == 'monday':
                    interventions.append({'type': 'wind_down', 'reason': '周一综合症，提前30分钟放下手机'})
            # 最多3条建议
            interventions = interventions[:3]

        now = datetime.now()
        bedtime_default = '23:00'
        if adjusted_score < 40:
            bedtime_default = '22:30'

        result = {
            'score': round(adjusted_score, 1),
            'baseline_score': baseline['score'],
            'adjustment': round(adjustment, 1),
            'confidence': confidence,
            'alert_level': alert_level,
            'direction': trend['direction'],
            'risk_factors': [{'key': k, 'weight': w, 'label': l} for k, w, l in risk_factors],
            'interventions': interventions,
            'suggested_bedtime': bedtime_default,
            'context': context,
            'generated_at': now.isoformat(),
            'version': '1.0',
        }

        return result


# ============ 预判报告格式化 ============

def format_siege_report(prediction: dict) -> str:
    """将预测结果格式化为自然语言文本（供LLM注入/微信推送）"""
    level = prediction['alert_level']
    score = prediction['score']
    confidence = prediction['confidence']
    direction = prediction['direction']

    emojis = {'red': '🔴', 'yellow': '🟡', 'green': '🟢', 'blue': '🔵'}
    emoji = emojis.get(level, '⚪')

    if direction == 'improving':
        dir_text = '（近期趋势向好）'
    elif direction == 'declining':
        dir_text = '（近期趋势下降）'
    else:
        dir_text = ''

    lines = [
        f'🌙 今晚睡眠预判',
        f'━━━━━━━━━━━━━━━',
        f'{emoji} 预测评分: {score}/100 (置信度{confidence:.0%}){dir_text}',
    ]

    if prediction['risk_factors']:
        lines.append(f'\n📊 影响因素（前3）:')
        for i, f in enumerate(prediction['risk_factors'][:3], 1):
            sign = '+' if f['weight'] > 0 else ''
            lines.append(f'  {i}. {f["label"]} ({sign}{f["weight"]}分)')

    if prediction['interventions']:
        lines.append(f'\n💡 建议:')
        for intv in prediction['interventions']:
            lines.append(f'  · {intv["reason"]}')

    lines.append(f'\n⏰ 建议就寝: {prediction["suggested_bedtime"]}')
    lines.append(f'━━━━━━━━━━━━━━━')

    return '\n'.join(lines)
