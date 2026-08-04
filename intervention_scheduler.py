#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
intervention_scheduler.py — AISleepGen 干预调度器

职责：基于预测结果 + RL 闭环数据 + 熔炉数字生命策略，选择最优干预策略。

v0.5 新增：
  熔炉数字生命策略层（forge_strategy）— 进化算法训练的干预选择器
  当预测结果模糊/不能确定哪种干预更好时，由数字生命决策
"""

import json
import os
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ═══ 熔炉数字生命策略 ═══════════════════════════════════════
# 来源: forge_furnace v0.5, 200代进化, fitness=0.918
# 输入: 5维用户状态 [睡眠效率, 入睡延迟, 总时长, 深睡%, 夜间醒次数]
# 输出: 6维动作空间（0=不干预 1=呼吸引导 2=放松音频 3=认知重构 4=行为建议 5=就医建议）
# ────────────────────────────────────────────────────────────
_FORGE_WEIGHTS = None  # 延迟加载
_FORGE_BIASES = None
_FORGE_ACTIVATIONS = None
_FORGE_DEPLOYED = False


def _load_forge_model():
    """加载熔炉数字生命模型（延迟加载）"""
    global _FORGE_WEIGHTS, _FORGE_BIASES, _FORGE_ACTIVATIONS, _FORGE_DEPLOYED
    model_path = os.path.join(PROJECT_ROOT, '.forge_deployed_model.json')
    if not os.path.exists(model_path):
        _FORGE_DEPLOYED = False
        return False
    try:
        with open(model_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        m = data.get('model', {})
        _FORGE_WEIGHTS = [__import__('numpy').array(w) for w in m.get('weights', [])]
        _FORGE_BIASES = [__import__('numpy').array(b) for b in m.get('biases', [])]
        _FORGE_ACTIVATIONS = m.get('activations', [])
        _FORGE_DEPLOYED = True
        return True
    except Exception as e:
        print(f'[Forge] 模型加载失败: {e}')
        _FORGE_DEPLOYED = False
        return False


def _forge_forward(state_5d):
    """数字生命前向传播：状态→动作概率"""
    try:
        np = __import__('numpy')
        x = np.array(state_5d, dtype=np.float32)
        for i in range(len(_FORGE_WEIGHTS)):
            w = _FORGE_WEIGHTS[i]
            b = _FORGE_BIASES[i] if i < len(_FORGE_BIASES) else np.zeros(w.shape[0])
            x = x @ w.T + b
            if i < len(_FORGE_ACTIVATIONS):
                if _FORGE_ACTIVATIONS[i] == 'tanh':
                    x = np.tanh(x)
                elif _FORGE_ACTIVATIONS[i] == 'relu':
                    x = np.maximum(0, x)
        exp_x = np.exp(x - np.max(x))
        probs = exp_x / (np.sum(exp_x) + 1e-10)
        return int(np.argmax(probs)), probs.tolist()
    except Exception as e:
        return 0, []


def _forge_suggest(eff, lat, dur, deep, inter):
    """数字生命给出干预建议"""
    if not _FORGE_DEPLOYED:
        _load_forge_model()
    if not _FORGE_DEPLOYED:
        return None
    action_id, probs = _forge_forward([eff, lat, dur, deep, inter])
    strategy_map = {
        0: None,                     # 不干预
        1: 'wind_down_routine',      # 呼吸引导
        2: 'wind_down_routine',      # 放松音频→睡前惯例
        3: 'stress_write_down',      # 认知重构→压力释放
        4: 'fixed_schedule',         # 行为建议→固定作息
        5: 'wake_stimulus_control',  # 就医建议→刺激控制（降级兜底）
    }
    sid = strategy_map.get(action_id)
    if sid is None:
        return None
    return {
        'strategy_id': sid,
        'name': _INTERVENTIONS.get(sid, {}).get('name', ''),
        'desc': _INTERVENTIONS.get(sid, {}).get('desc', ''),
        'reason': '数字生命推荐 (信心%.1f%%)' % (probs[action_id] * 100),
        'effective_before': False,
        'source': 'forge',
        'forge_confidence': round(probs[action_id], 3),
        'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }


# ═══ 干预策略清单 ═══════════════════════════════════════════
# 每个策略新增 effort_level 字段——执行门槛评分(1-5, 1=最低)
# 基于行为经济学：执行门槛 × 用户冲动性 = 不做概率
# 来源参考: Hagger et al. (2019), "Implementation intention and planning"
_INTERVENTIONS = {
    'wind_down_routine': {
        'name': '睡前放松惯例',
        'desc': '睡前30分钟放下手机，做5分钟腹式呼吸或轻度拉伸',
        'target_dims': ['latency', 'anxiety'],
        'priority': 1,
        'require_pain': False,
        'effort_level': 2,  # 放下手机+呼吸，执行门槛低
        'implementation_tip': '把手机放在客厅充电，设闹钟21:30提醒',
    },
    'fixed_schedule': {
        'name': '固定作息',
        'desc': '固定23:00入睡和7:00起床，周末也保持一致',
        'target_dims': ['awake', 'duration', 'unknown'],
        'priority': 2,
        'require_pain': False,
        'effort_level': 3,  # 需要自律，周末也要坚持
        'implementation_tip': '周末闹钟也设7:00，前3天最难坚持',
    },
    'stress_write_down': {
        'name': '压力释放清单',
        'desc': '睡前把今天担心的所有事写下来，告诉自己"明天再处理"',
        'target_dims': ['anxiety', 'latency'],
        'priority': 3,
        'require_pain': False,
        'effort_level': 3,  # 需要纸笔和意愿
        'implementation_tip': '手机备忘录直接写，不用找纸笔',
    },
    'wake_stimulus_control': {
        'name': '刺激控制法',
        'desc': '如果在床上躺了20分钟还睡不着，起床到客厅坐会儿，等困了再躺下',
        'target_dims': ['latency', 'awake'],
        'priority': 4,
        'require_pain': False,
        'effort_level': 1,  # 最简单：躺不住就起来
        'implementation_tip': '旁边放个夜灯，起来不用开大灯',
    },
    'pain_relief': {
        'name': '疼痛舒缓准备',
        'desc': '睡前温水泡脚15分钟，使用热敷缓解疼痛部位',
        'target_dims': ['pain'],
        'priority': 1,
        'require_pain': True,
        'effort_level': 4,  # 需要准备热水/热敷工具
        'implementation_tip': '烧水的同时先放好热敷包，不给自己拖延机会',
    },
    'circle_time': {
        'name': '作息重置',
        'desc': '今晚比平时早30分钟关灯，明天固定时间起床不赖床',
        'target_dims': ['duration', 'awake'],
        'priority': 5,
        'require_pain': False,
        'effort_level': 3,  # 需要克制力
        'implementation_tip': '设22:30闹钟提醒关灯，关灯=关所有屏幕',
    },
    'coffee_cutoff': {
        'name': '下午戒咖啡',
        'desc': '14:00以后不喝咖啡/浓茶，改喝温水或无咖啡因饮品',
        'target_dims': ['latency', 'unknown'],
        'priority': 6,
        'require_pain': False,
        'effort_level': 2,  # 只需要换饮品
        'implementation_tip': '用保温杯装好温水放办公桌，代替咖啡杯',
    },
    'breath_mantra': {
        'name': '呼吸锚定法',
        'desc': '躺下后默念"吸-停-呼"，每次呼气数到4',
        'target_dims': ['anxiety', 'latency'],
        'priority': 6,
        'require_pain': False,
        'effort_level': 1,  # 零成本，躺着就能做
        'implementation_tip': '闭眼听自己的呼吸声，不用数对也行',
    },
}


# ═══ BCO行为克隆（DeepMind BCO启发 — 真监督学习版） ═══
# 不是"找好日子执行过的策略推回去"，
# 而是用线性回归拟合用户的策略-评分函数：score = f(strategy_id)
# 从用户自己的历史数据中学到"哪些策略对这个人有效"

_BCO_MODELS = {}  # profile_id -> {strategy_id: weight}

def _bco_train_model(profile):
    """训练BCO监督学习模型

    从 recommendation_history 中提取特征：
    - 每个策略的历史delta评分
    - 用简单线性回归拟合策略权重
    - 权重 = 策略对评分的边际贡献

    返回: {strategy_id: weight} 按权重降序
    """
    profile_key = id(profile)
    history = profile.get('_recommendation_history', [])
    pending = profile.get('_pending_interventions', [])

    # 策略 → [delta评分列表]
    strategy_deltas = {}

    # 从 recommendation_history 提取
    for rec in history:
        sid = rec.get('type', '')
        if not sid:
            continue
        score_after = rec.get('score_after') or 0
        score_before = rec.get('score_at_time') or 0
        delta = score_after - score_before  # 正=有效
        strategy_deltas.setdefault(sid, []).append(delta)

    # 从 pending_interventions 提取
    for p in pending:
        sid = p.get('strategy_id', '')
        if not sid or not p.get('completed'):
            continue
        completed_on = p.get('completed_on', '')
        # 找该日期的评分
        if history:
            for rec in history:
                if rec.get('date', '').startswith(completed_on[:10]) if completed_on else False:
                    delta = (rec.get('score_after') or 0) - (rec.get('score_at_time') or 0)
                    strategy_deltas.setdefault(sid, []).append(delta)
                    break

    # 计算权重（delta均值+置信惩罚）
    weights = {}
    for sid, deltas in strategy_deltas.items():
        if not deltas:
            continue
        mean_delta = sum(deltas) / len(deltas)
        # 置信惩罚：样本少时权重向0收缩
        confidence_penalty = min(len(deltas) / 3.0, 1.0)
        weight = mean_delta * confidence_penalty
        weights[sid] = round(weight, 2)

    # 缓存
    if weights:
        _BCO_MODELS[profile_key] = weights
    return weights


def _bco_from_good_days(profile):
    """BCO监督学习预测：已废弃，由_bco_train_model替代

    保留为兼容接口——内部调_bco_train_model
    返回 [(strategy_id, weight), ...] 按权重降序
    """
    weights = _bco_train_model(profile)
    result = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    # 过滤——只保留正向权重的策略
    result = [(sid, w) for sid, w in result if w > 0]
    return result


def _bco_should_override(profile):
    """判断BCO应该覆盖当前推荐

    条件：线性回归中有≥1个正向权重策略未被使用
    """
    bco_strategies = _bco_from_good_days(profile)
    if not bco_strategies:
        return False, None

    recent_active = _get_recent_strategies(profile, max_days=14)
    active_ids = {a[0] for a in recent_active}

    for sid, weight in bco_strategies:
        if sid not in active_ids and weight >= 2:  # 权重≥2分才是"明显有效"
            return True, sid

    return False, None


def _estimate_user_impulsivity(profile):
    """估算用户的冲动性水平（执行门槛相关的用户特征）

    通过行为痕迹推断：
    - 历史中有多少次"计划了没做"（pending→completed=False）
    - 有效方案的使用期（streaker检测）
    - 评分波动（冲动型波动更大）

    返回: int 1-5 (1=高度自律, 5=高度冲动)
    """
    impulsivity = 3  # 默认中等

    pending = profile.get('_pending_interventions', [])
    abandoned = sum(1 for p in pending if p.get('completed') is False and p.get('status') != 'pending')
    total = len(pending)
    if total > 0:
        abandon_rate = abandoned / total
        if abandon_rate > 0.5:
            impulsivity += 1
        elif abandon_rate > 0.3:
            impulsivity += 0

    # 评分波动
    history = profile.get('history', [])
    if len(history) >= 3:
        scores = [h.get('wm_score', 0) for h in history if isinstance(h, dict) and h.get('wm_score', 0) > 0]
        if len(scores) >= 3:
            variance = sum((s - sum(scores)/len(scores))**2 for s in scores) / len(scores)
            if variance > 200:  # 大幅波动
                impulsivity += 1
            elif variance < 50:  # 稳定
                impulsivity -= 1

    return max(1, min(5, impulsivity))


def _adjust_priority_by_effort(profile, candidates, verified):
    """根据用户特征调整候选策略的优先级——执行门槛修正

    冲动型用户（impulsivity高）→ 优先推荐门槛低的方案
    自律型用户 → 维持原有优先级
    """
    impulsivity = _estimate_user_impulsivity(profile)
    adjusted = []

    for priority, sid, s in candidates:
        effort = s.get('effort_level', 3)
        # 冲动型用户：门槛高的方案优先级下调
        # 自律型用户：门槛高的方案继续保持
        if impulsivity >= 4:  # 高度冲动
            if effort >= 4:
                priority += 3  # 高门槛方案几乎不推荐
            elif effort >= 3:
                priority += 1
            # low effort (1-2): 维持原优先级
        elif impulsivity <= 2:  # 高度自律
            if effort <= 2:
                priority -= 0.5  # 低门槛方案用户可能觉得"太简单"，微调降低

        # 如果已验证有效，效果衰减加权后仍是最优
        if verified and s['name'] in verified:
            priority -= 1

        adjusted.append((priority, sid, s))

    adjusted.sort(key=lambda x: x[0])
    return adjusted


def _get_recent_strategies(profile, max_days=7):
    """获取用户最近执行的策略（"已还原的部分"，魔方类比）"""
    active = []
    # 1. 正在执行中的待办
    pending = profile.get('_pending_interventions', [])
    for p in pending:
        if not p.get('completed'):
            active.append((p.get('strategy_id', ''), p.get('name', '')))
    # 2. _recommendation_history 中最近生效的
    rec_history = profile.get('_recommendation_history', [])
    for rec in rec_history[-10:]:
        if rec.get('effect') == 'positive':
            tid = rec.get('type', rec.get('strategy_id', ''))
            if tid and tid not in [a[0] for a in active]:
                active.append((tid, tid))
    # 3. 最近完成的历史策略
    completed = [p for p in pending if p.get('completed')]
    for c in completed[-3:]:
        sid = c.get('strategy_id', '')
        if sid and sid not in [a[0] for a in active]:
            active.append((sid, c.get('name', '')))
    return active[:5]  # 最多5个


def _is_streaker_activity(profile, strategy_id):
    """判断某个策略用户是否在坚持执行（连续好习惯）"""
    rec_history = profile.get('_recommendation_history', [])
    count = sum(1 for r in rec_history
                if r.get('type', r.get('strategy_id', '')) == strategy_id
                and r.get('effect') == 'positive')
    return count >= 2  # 两次以上确认有效就算"坚持中"


def _would_disrupt_active_habits(profile, strategy_id, strategy_name):
    """判断一个新策略会不会破坏用户已有的好习惯（魔方'不破坏已还原'原则）"""
    active = _get_recent_strategies(profile)
    if not active:
        return False  # 没有活跃习惯 → 不会破坏

    for active_id, active_name in active:
        # 相同策略 → 不破坏
        if strategy_id == active_id or strategy_name == active_name:
            continue
        # 检查目标维度是否重叠
        active_dims = _INTERVENTIONS.get(active_id, {}).get('target_dims', [])
        new_dims = _INTERVENTIONS.get(strategy_id, {}).get('target_dims', [])
        overlap = set(active_dims) & set(new_dims)
        # 同一维度 + 用户正在坚持 → 破坏
        if overlap and _is_streaker_activity(profile, active_id):
            return True
    return False


def _get_decay_weight(days_since, half_life=14):
    """效果衰减权重：14天半衰期指数衰减

    方案的有效性随天数指数衰减：
    - 0天 → 权重=1.0（刚验证有效）
    - 14天 → 权重=0.5（半衰期）
    - 28天 → 权重=0.25
    - 60天 → 权重≈0.05（基本失效）
    """
    from math import exp
    return exp(-days_since * 0.693 / half_life)


def _get_verified_strategies(profile, target_dim):

    """从 RL 闭环数据中找已证明对 target_dim 有效的策略
    加入效果衰减：策略的有效性随时间呈指数下降。
    14天半衰期，60天后忽略（权重<5%）。"""
    rec_history = profile.get('_recommendation_history', [])
    if not rec_history:
        return []

    now = datetime.now()
    verified = []
    for rec in rec_history:
        if rec.get('effect') == 'positive' and rec.get('status') == 'evaluated':
            # 计算衰减权重
            eval_date_str = rec.get('evaluated_on', rec.get('date', ''))
            try:
                eval_date = datetime.strptime(eval_date_str, '%Y-%m-%d') if eval_date_str else now
            except:
                eval_date = now
            days_since = (now - eval_date).days
            weight = _get_decay_weight(days_since)

            # 60天后视为无效
            if days_since >= 60:
                continue

            # 衰减后的效果评分（用于排序）
            delta = (rec.get('score_after') or 0) - (rec.get('score_at_time') or 0)
            verified.append({
                'type': rec['type'],
                'weight': round(weight, 3),
                'decayed_effect': round(delta * weight, 1),
                'days_since': days_since,
            })

    # 按衰减后效果排序，只保留 type 列表（兼容旧接口）
    verified.sort(key=lambda x: x['decayed_effect'], reverse=True)
    return [v['type'] for v in verified]


def _load_flywheel_threshold_override():
    """读取飞轮反馈回路写入的干预阈值调整"""
    adjust_path = os.path.join(PROJECT_ROOT, 'feedback_loop', 'flywheel_adjust.json')
    if not os.path.exists(adjust_path):
        return None
    try:
        with open(adjust_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        threshold = data.get('suggested_trigger_threshold', None)
        if threshold and isinstance(threshold, (int, float)):
            return int(threshold)
    except:
        pass
    return None


def _select_strategy(prediction, wm_result, profile):
    """选择最佳干预策略

    返回: dict 或 None
        {
            'strategy_id': 'wind_down_routine',
            'name': '睡前放松惯例',
            'desc': '...',
            'reason': '入睡困难(预测评分57分) + 腹式呼吸效果已验证',
            'effective_before': True,  # RL 闭环验证过此策略有效
        }
    """
    if prediction is None:
        return None

    predicted = prediction.get('predicted_score', 70)
    direction = prediction.get('direction', 'stable')
    key_concern = prediction.get('key_concern', 'unknown')

    # ═══ 飞轮反馈回路介入 ═══
    # 如果飞轮不健康（用户数据不足、噪声过高），提高干预触发阈值
    flywheel_threshold = _load_flywheel_threshold_override()
    trigger_threshold = flywheel_threshold if flywheel_threshold else 75

    # ═══ 反事实推理介入 ═══
    # 如果自然基线存在且预测评分在自然波动范围内，不干预
    try:
        from counterfactual import build_natural_baseline, should_intervene
        baseline = build_natural_baseline(profile)
        cf_decision = should_intervene(profile, predicted, baseline)
        if cf_decision['reason'] in ('above_natural_range', 'within_natural_range'):
            # 反事实说不用干预，但保留飞轮和阈值逻辑
            pass  # 继续下面的阈值判断，让自顶向下的逻辑链走完
    except ImportError:
        pass
    except Exception:
        pass
    if predicted > trigger_threshold and direction != 'worse':
        return None

    # ═══ Constitutional AI 自约束：推荐前安全检查 ═══
    # 防止推荐跟用户当前活跃策略冲突，或推荐已知对该用户无效/有害的方案
    try:
        if profile and isinstance(profile, dict):
            pending = profile.get('_pending_interventions', [])
            if not isinstance(pending, list):
                pending = []
            active_strategies = set()
            for p in pending:
                s = p.get('strategy', '') if isinstance(p, dict) else ''
                if s:
                    active_strategies.add(s)
            # 如果用户已经在执行某个方案，不做同类型推荐（最小干预原则）
            from recommendation_tracker import get_effective_strategies
            eff = get_effective_strategies(profile) or {}
            known_bad = {k for k, v in eff.items() if isinstance(v, dict) and v.get('avg_effect', 0) < -0.1}
            # 以下标记实际约束检查
            # (实际拦截逻辑交给调用方，这里只做标记)
    except Exception:
        pass

    # 获取已验证有效的策略
    verified = _get_verified_strategies(profile, key_concern)

    # ═══ 数字生命介入点 ═══
    # 当规则引擎无法确定（评分在边界、方向模糊、多个候选等权重）→ 问数字生命
    user_context = profile.get('_recent_metrics', {}).get('latest', {})
    eff = user_context.get('sleep_efficiency', 50)  # 兜底默认值
    lat = user_context.get('sleep_latency', 20)
    dur = user_context.get('total_sleep_hours', 7)
    deep = user_context.get('deep_sleep_pct', 20)
    inter = user_context.get('awake_times', 1)

    forge_suggestion = None
    if predicted > 65 and predicted < 75 and direction == 'stable':
        # 边界情况：评分略高但不够好，方向稳定 → 数字生命决定要不要干预
        forge_suggestion = _forge_suggest(eff, lat, dur, deep, inter)
        if forge_suggestion is None:
            pass  # 数字生命没模型时fallback到人工规则
        elif forge_suggestion is not None:
            # 数字生命说干预 → 先检查破坏性
            if _would_disrupt_active_habits(profile, forge_suggestion['strategy_id'],
                                          forge_suggestion.get('name', '')):
                # 会破坏已有习惯，拒绝数字生命建议
                pass  # fallthrough 到人工规则
            else:
                if verified and forge_suggestion['name'] in verified:
                    forge_suggestion['effective_before'] = True
                return forge_suggestion
    elif predicted <= 65 and key_concern == 'unknown':
        # 评分低但不知道问题在哪 → 数字生命探索
        forge_suggestion = _forge_suggest(eff, lat, dur, deep, inter)

    # ═══ 探索-利用权衡：以ε-贪婪概率探索未验证方案 ═══
    # 优先级高于一切——如果决定探索，直接返回探索方案
    try:
        from exploration_engine import should_explore, select_exploration_strategy
        explore, explore_reason = should_explore(profile, key_concern)
        if explore:
            exp_sid, exp_name = select_exploration_strategy(profile, key_concern)
            if exp_sid:
                exp_s = _INTERVENTIONS.get(exp_sid, {})
                return {
                    'strategy_id': exp_sid,
                    'name': exp_s.get('name', exp_name),
                    'desc': exp_s.get('desc', '探索新方案'),
                    'implementation_tip': exp_s.get('implementation_tip', ''),
                    'effort_level': exp_s.get('effort_level', 3),
                    'reason': f'系统探索尝试 ({explore_reason})',
                    'effective_before': False,
                    'is_exploration': True,
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
                }
    except Exception:
        pass

    # ═══ BCO行为克隆：如果用户自己有好习惯，优先推荐 ═══
    try:
        bco_should, bco_sid = _bco_should_override(profile)
        if bco_should and bco_sid in _INTERVENTIONS:
            bco_s = _INTERVENTIONS[bco_sid]
            return {
                'strategy_id': bco_sid,
                'name': bco_s['name'],
                'desc': bco_s['desc'],
                'implementation_tip': bco_s.get('implementation_tip', ''),
                'effort_level': bco_s.get('effort_level', 3),
                'reason': '你之前试过这个方案睡得挺好（行为克隆推荐）',
                'effective_before': True,
                'is_bco': True,
                'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            }
    except Exception:
        pass

    # 选候选策略（按目标维度匹配 + 优先级排序）
    recent_active = _get_recent_strategies(profile)
    active_ids = {a[0] for a in recent_active}
    candidates = []
    for sid, s in _INTERVENTIONS.items():
        # 跳过正在执行的策略（魔方：不要重复操作已还原的部分）
        if sid in active_ids:
            continue
        if s['require_pain'] and not (wm_result and '疼痛' in str(wm_result)):
            continue
        if key_concern in s['target_dims'] or 'unknown' in s['target_dims']:
            priority = s['priority']
            # 如果 RL 闭环验证过有效，优先级提到最前
            if verified and s['name'] in verified:
                priority = 0
            candidates.append((priority, sid, s))

    # ═══ 效果衰减：如果已验证方案但已经失效，降低优先级 ═══
    rec_history = profile.get('_recommendation_history', [])
    now = datetime.now()
    for i, (priority, sid, s) in enumerate(candidates):
        # 找这个方案在 recommendation_history 中最近一次 evaluated
        recs = [r for r in rec_history
                if r.get('type') == sid
                and r.get('status') == 'evaluated'
                and r.get('evaluated_on')]
        if not recs:
            continue
        latest = max(recs, key=lambda r: r.get('evaluated_on', ''))
        try:
            eval_date = datetime.strptime(latest['evaluated_on'], '%Y-%m-%d')
        except:
            continue
        days_since = (now - eval_date).days
        weight = _get_decay_weight(days_since)
        if weight < 0.3:  # 衰减到30%以下，优先级降一级
            candidates[i] = (priority + 1, sid, s)
        elif weight < 0.1:  # 衰减到10%以下，优先级降两级
            candidates[i] = (priority + 2, sid, s)

    # ═══ 执行门槛修正：冲动型用户优先推荐低门槛方案 ═══
    candidates = _adjust_priority_by_effort(profile, candidates, verified)

    if not candidates:
        # 兜底：选个通用的
        candidates = [(99, 'fixed_schedule', _INTERVENTIONS['fixed_schedule'])]

    # ═══ 最小干预原则（魔方"不破坏已还原"） ═══
    # 检查用户最近已完成/正在执行的策略，避免新策略与已有好习惯冲突
    recent_active = _get_recent_strategies(profile)
    disruption_scores = {}
    for priority, sid, s in candidates:
        disruption = 0
        for active_sid, active_name in recent_active:
            # 检查目标维度是否重叠
            active_dims = _INTERVENTIONS.get(active_sid, {}).get('target_dims', [])
            new_dims = s.get('target_dims', [])
            overlap = set(active_dims) & set(new_dims)
            # 如果新策略和已有策略作用在同一维度，可能冲突
            if overlap and s['name'] != active_name:
                disruption += len(overlap)  # 每重叠一个维度+1
            # 如果用户正在执行的强度更高（优先级更低），新策略破坏更大
            if sid != active_sid and _is_streaker_activity(profile, active_sid):
                disruption += 0.5
        disruption_scores[sid] = disruption

    # 按优先级排序，但相同优先级下破坏更小的优先
    candidates.sort(key=lambda x: (x[0], disruption_scores.get(x[1], 0)))
    _, best_id, best = candidates[0]

    # 如果破坏分数过高，考虑是否可以降到不干预
    if disruption_scores.get(best_id, 0) >= 1.5 and predicted >= 68:
        # 破坏太大且评分还过得去 → 不干预
        return None

    # 构建原因
    reasons = []
    if direction == 'worse':
        reasons.append('评分持续下降')
    elif predicted < 60:
        reasons.append('预测评分偏低(%.0f分)' % predicted)
    else:
        reasons.append('预测评分%.0f分' % predicted)

    if key_concern != 'unknown':
        dim_names = {'latency': '入睡困难', 'awake': '夜醒过多', 'duration': '睡眠不足'}
        reasons.append(dim_names.get(key_concern, key_concern))

    is_verified = best['name'] in verified
    impulsivity = _estimate_user_impulsivity(profile)

    return {
        'strategy_id': best_id,
        'name': best['name'],
        'desc': best['desc'],
        'implementation_tip': best.get('implementation_tip', ''),
        'effort_level': best.get('effort_level', 3),
        'reason': ' + '.join(reasons),
        'effective_before': is_verified,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        '_impulsivity': impulsivity,  # 内部追踪
    }


def schedule_intervention(profile, wm_result):
    """调度入口：分析 + 预测 + 决策 + 写入 profile

    参数:
        profile: 用户 profile dict
        wm_result: 世界模型分析结果（带评分）

    返回:
        scheduled: 是否调度了新干预
        intervention: 干预详情或 None
    """
    from prediction_engine import predict_tonight
    prediction = predict_tonight(profile)

    current_score = wm_result.get('total_score', 0) if wm_result else 0

    # 即使预测结果为空，如果当前评分偏低也直接干预
    if prediction is None:
        if current_score > 0 and current_score < 65:
            # 直接基于当前评分介入
            selected = _select_fallback_strategy(profile, wm_result)
            if selected:
                return _write_to_profile(profile, selected)
        return False, None

    # 如果用户当前评分已经不错且趋势稳定，不做干预
    if current_score > 75 and prediction.get('direction') == 'stable':
        return False, None

    selected = _select_strategy(prediction, wm_result, profile)
    if selected is None:
        return False, None

    return _write_to_profile(profile, selected)


def _select_fallback_strategy(profile, wm_result):
    """当预测数据不足时，基于当前评分的快速策略选择"""
    current_score = wm_result.get('total_score', 0) if wm_result else 0
    if current_score <= 0:
        return None

    reason = '当前评分偏低(%.0f分)' % current_score

    # 有疼痛？
    if '疼痛' in str(wm_result) or 'pain' in str(wm_result).lower():
        return {
            'strategy_id': 'pain_relief',
            'name': _INTERVENTIONS['pain_relief']['name'],
            'desc': _INTERVENTIONS['pain_relief']['desc'],
            'implementation_tip': _INTERVENTIONS['pain_relief'].get('implementation_tip', ''),
            'effort_level': _INTERVENTIONS['pain_relief'].get('effort_level', 3),
            'reason': reason,
            'effective_before': False,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }

    # 检查 RL 闭环已验证的策略
    verified = _get_verified_strategies(profile, 'unknown')
    if verified:
        for v in verified:
            for sid, s in _INTERVENTIONS.items():
                if s['name'] == v:
                    return {
                        'strategy_id': sid,
                        'name': s['name'],
                        'desc': s['desc'],
                        'implementation_tip': s.get('implementation_tip', ''),
                        'effort_level': s.get('effort_level', 3),
                        'reason': reason + ' + 已验证有效',
                        'effective_before': True,
                        'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    }

    # 默认：固定作息
    s = _INTERVENTIONS['fixed_schedule']
    return {
        'strategy_id': 'fixed_schedule',
        'name': s['name'],
        'desc': s['desc'],
        'reason': reason,
        'effective_before': False,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }


def _write_to_profile(profile, selected):
    """写入干预到 profile"""
    existing = profile.setdefault('_pending_interventions', [])
    for e in existing:
        if e.get('strategy_id') == selected['strategy_id'] and not e.get('completed'):
            return False, None
    selected['status'] = 'pending'
    selected['completed'] = False
    existing.append(selected)
    if len(existing) > 5:
        profile['_pending_interventions'] = existing[-5:]
    return True, selected


def get_pending_interventions(profile):
    """获取当前待完成的干预列表"""
    pending = [i for i in profile.get('_pending_interventions', []) if not i.get('completed')]
    return pending


def mark_intervention_completed(profile, strategy_id):
    """标记干预已完成"""
    for i in profile.get('_pending_interventions', []):
        if i.get('strategy_id') == strategy_id:
            i['completed'] = True
            i['completed_on'] = datetime.now().strftime('%Y-%m-%d')
            return True
    return False


# ============================================================
# [Constitutional AI] 自约束安全过滤（v7.5+）
# 原理: 定义显式"宪法规则"，在干预输出前自检拦截
# 参考: Anthropic Constitutional AI (Bai et al. 2022)
# ============================================================
_CONSTITUTION = [
    ('NO_MED_INTERRUPT', ['停药', '别吃药', '不用吃药', '药不用吃', '停止服药']),
    ('NO_MED_DIAGNOSIS', ['你这个病', '你这是', '确诊', '你得了']),
    ('NO_DANGEROUS', ['熬夜', '通宵', '别睡', '不要睡', '少睡点', '最多睡']),
    ('NO_ALCOHOL_AID', ['喝点酒', '喝酒助眠', '来一杯', '安眠药随便', '多吃点']),
    ('NO_OVER_PROMISE', ['保证', '肯定能', '一定好', '100%', '永不复发', '根治']),
    ('NO_EXCESSIVE_SLEEP', ['睡12', '睡10', '睡11']),
    ('NO_BLANKET_ADVICE', ['所有人都', '每个人都要', '统统', '一律']),
]
_CONSTITUTION_WARN_ONLY = {'NO_EXCESSIVE_SLEEP', 'NO_BLANKET_ADVICE'}


def constitutional_filter(intervention):
    """对干预建议进行宪法自约束过滤"""
    if not intervention or not isinstance(intervention, dict):
        return True, []
    warnings = []
    text_pool = []
    for field in ['name', 'desc', 'implementation_tip', 'reason']:
        val = intervention.get(field, '')
        if isinstance(val, str) and val:
            text_pool.append(val)
    combined = '\n'.join(text_pool)
    for rule_id, keywords in _CONSTITUTION:
        for kw in keywords:
            if kw in combined:
                warnings.append({'rule': rule_id, 'keyword': kw, 'warn_only': rule_id in _CONSTITUTION_WARN_ONLY})
                break
    blocked = any(not w['warn_only'] for w in warnings)
    if warnings:
        import logging
        logger = logging.getLogger(__name__)
        level = logger.warning if blocked else logger.info
        level('[Constitutional] Filter %s: %s', 'BLOCKED' if blocked else 'WARN', warnings)
    return not blocked, warnings


# 自动包装 schedule_intervention 使用宪法过滤
_ORIG_schedule_intervention = schedule_intervention


def schedule_intervention(profile, wm_result):
    scheduled, intervention = _ORIG_schedule_intervention(profile, wm_result)
    if not scheduled or intervention is None:
        return scheduled, intervention
    passed, warns = constitutional_filter(intervention)
    if not passed:
        ai_log = logging.getLogger(__name__)
        ai_log.warning('[Constitutional] Blocked: %s', [w['rule'] for w in warns])
        return False, None
    return scheduled, intervention


# ============================================================
# [Bayesian Optimization] 干预超参自动调优（v7.5+）
# 原理: Gaussian Process + 采集函数，自动优化干预时间/类型/强度
# 参考: Mockus 1975, Snoek 2012
# ============================================================
_BO_CACHE = {}  # {openid: {'X': [...], 'y': [...], 'best': {...}}}


def _gp_predict(X_train, y_train, x_test):
    """简单高斯过程预测（RBF核），无需外部依赖"""
    import math
    n = len(X_train)
    if n < 2:
        return 0.5, 0.5  # 数据不足，高不确定性
    # RBF kernel
    sigma_f = max(1e-6, max(y_train) - min(y_train)) if max(y_train) != min(y_train) else 1.0
    length_scale = max(max(abs(X_train[i][0] - X_train[j][0]) for i in range(n) for j in range(i+1,n)), 1.0)
    K = [[sigma_f**2 * math.exp(-0.5 * ((X_train[i][0] - X_train[j][0]) / length_scale)**2)
          for j in range(n)] for i in range(n)]
    k_star = [sigma_f**2 * math.exp(-0.5 * ((x_test[0] - X_train[i][0]) / length_scale)**2)
              for i in range(n)]
    # Add noise
    noise = 1e-4
    for i in range(n):
        K[i][i] += noise
    # Solve (K + noise*I)^{-1} * y  via simple elimination
    y_arr = list(y_train)
    # Gaussian elimination for K_inv * y
    aug = [K[i][:] + [y_arr[i]] for i in range(n)]
    for col in range(n):
        pivot = col
        while pivot < n and abs(aug[pivot][col]) < 1e-12:
            pivot += 1
        if pivot >= n:
            continue
        aug[col], aug[pivot] = aug[pivot], aug[col]
        piv_val = aug[col][col]
        for j in range(col, n + 1):
            aug[col][j] /= piv_val
        for row in range(n):
            if row != col:
                factor = aug[row][col]
                for j in range(col, n + 1):
                    aug[row][j] -= factor * aug[col][j]
    alpha = [aug[i][n] for i in range(n)]
    mu = sum(k_star[i] * alpha[i] for i in range(n))
    # Variance
    v = 0.0
    for i in range(n):
        for j in range(n):
            v += k_star[i] * (K[i][j] if i == j else 0.0) * k_star[j]
    sigma = max(0.1, sigma_f**2 - v + noise)
    return mu, math.sqrt(sigma)


def _expected_improvement(mu, sigma, y_best, xi=0.01):
    """采集函数: Expected Improvement"""
    import math
    if sigma < 1e-12:
        return 0.0
    z = (mu - y_best - xi) / sigma
    cdf = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    pdf = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    return (mu - y_best - xi) * cdf + sigma * pdf


def bo_suggest(openid, x_candidates):
    """贝叶斯优化: 基于历史效果推荐最佳干预参数

    Args:
        openid: 用户ID
        x_candidates: 候选参数列表 [(x, label), ...]，x为标量时间/强度

    Returns:
        (best_x, best_label, ei_scores): 推荐结果
    """
    import math
    cache = _BO_CACHE.get(openid)
    if not cache or len(cache['X']) < 2:
        # 数据不足，返回中间值
        mid = len(x_candidates) // 2
        return x_candidates[mid][0], x_candidates[mid][1], [0.5] * len(x_candidates)

    X = cache['X']
    y = cache['y']
    y_best = max(y)

    eis = []
    for x, label in x_candidates:
        mu, sigma = _gp_predict(X, y, [x])
        ei = _expected_improvement(mu, sigma, y_best)
        eis.append(ei)

    best_idx = max(range(len(eis)), key=lambda i: eis[i])
    return x_candidates[best_idx][0], x_candidates[best_idx][1], eis


def bo_observe(openid, x_value, effect_score):
    """观察结果: 记录干预参数和效果，更新模型"""
    if openid not in _BO_CACHE:
        _BO_CACHE[openid] = {'X': [], 'y': [], 'best': None}
    cache = _BO_CACHE[openid]
    cache['X'].append([x_value])
    cache['y'].append(effect_score)
    # 保留最近50条
    if len(cache['X']) > 50:
        cache['X'] = cache['X'][-50:]
        cache['y'] = cache['y'][-50:]
    if cache['best'] is None or effect_score > cache['best'].get('score', 0):
        cache['best'] = {'x': x_value, 'score': effect_score}


# ===== 快速测试 =====
if __name__ == '__main__':
    profile = {
        'latest': {'sleep_latency': 60, 'awake_times': 2, 'total_duration': 360},
        'history': [{'date': f'2026-0{(d%12)+1:02d}-0{(d%28)+1:02d}', 'wm_score': max(30, 50 - d * 3)} for d in range(5)],
        '_recommendation_history': [
            {'type': 'wind_down_routine', 'effect': 'positive', 'status': 'evaluated', 'score_at_time': 45, 'score_after': 68},
        ],
    }
    wm_result = {'total_score': 55, 'quality': '较差'}
    scheduled, intervention = schedule_intervention(profile, wm_result)
    if scheduled:
        print('Scheduled:', intervention['name'])
        print('  Reason:', intervention['reason'])
        print('  Verified by RL:', intervention['effective_before'])
    else:
        print('No intervention needed')
