"""
tier_recommender.py — 专业版会员推荐引擎

设计原则:
1. RFM用户分群（Recency/频次/评分值）
2. 用户生命周期阶段判断
3. 动态定价（基于用户价值和付费意愿）
4. A/B测试框架（记录变体+转化）
5. 冷却机制（不重复骚扰）

实践依据:
- 订阅制DTC定价: Recharge/Chargebee 最佳实践
- 用户分群: 参照电商RFM模型改造为睡眠场景
- 动态定价: 2024+ 行业标准（Stripe Billing 动态定价模式）
"""

import json, os, math, random
from datetime import datetime, timedelta

# ========== 定价配置（公开，前端也同步） ==========
PRICING = {
    'pro': {
        'name': '专业版',
        'price_monthly': 29.00,
        'price_quarterly': 69.00,    # 省20%
        'price_yearly': 199.00,      # 省43%
        'price_monthly_offer': 9.90, # 新客首月特惠
        'desc': '解锁500次深度分析 + 详细报告 + 优先响应',
        'icon': '⭐',
    },
    'unlimited': {
        'name': '无限版',
        'price_monthly': 99.00,
        'price_yearly': 499.00,      # 省58%
        'price_monthly_offer': 39.00, # 新客首月特惠
        'desc': '无限次数 + 所有高级功能 + 专属客服',
        'icon': '👑',
    }
}

# ========== 用户生命周期阶段 ==========
LIFECYCLE_STAGES = ['cold', 'new', 'active', 'engaged', 'loyal', 'churn_risk', 'churned']

def classify_lifecycle(profile):
    """
    判断用户生命周期阶段
    参照 SaaS 用户生命周期框架（Totango/Amplitude 标准）

    返回: 'cold'|'new'|'active'|'engaged'|'loyal'|'churn_risk'|'churned'
    """
    member = profile.get('member', {})
    now = datetime.now()

    total_days = member.get('total_days', 0)
    streak_days = member.get('streak_days', 0)
    last_active_str = member.get('last_active', '')

    # 计算最后活跃距今天数
    delta = 999
    if last_active_str:
        try:
            last = datetime.strptime(last_active_str.split(' ')[0], '%Y-%m-%d')
            delta = (now - last).days
        except:
            pass

    # 已流失（7天未活跃）
    if delta >= 7:
        return 'churned'
    # 流失预警（5天未活跃）
    if delta >= 5:
        return 'churn_risk'
    # 忠实用户（连续7天以上）
    if streak_days >= 7 and total_days >= 20:
        return 'loyal'
    # 互动中（连续3天以上）
    if streak_days >= 3 and total_days >= 7:
        return 'engaged'
    # 活跃（总天数>=3）
    if total_days >= 3:
        return 'active'
    # 新用户（总天数1-2）
    if total_days >= 1:
        return 'new'
    # 冷启动
    return 'cold'


def compute_rfm(profile):
    """
    RFM评分: Recency → Frequency → Monetary(睡眠评分替代)
    返回: {recency_score, frequency_score, score_value, rfm_total}
    每个维度 1-5 分，总分 3-15
    """
    member = profile.get('member', {})
    behavior = profile.get('behavior_stats', {})
    meta = profile.get('meta_params', {})

    now = datetime.now()

    # Recency（最后活跃距今）
    last_active_str = member.get('last_active', '')
    delta = 0
    if last_active_str:
        try:
            last = datetime.strptime(last_active_str.split(' ')[0], '%Y-%m-%d')
            delta = (now - last).days
        except:
            pass
    if delta <= 0:
        recency_score = 5   # 今天活跃
    elif delta == 1:
        recency_score = 4
    elif delta <= 3:
        recency_score = 3
    elif delta <= 5:
        recency_score = 2
    else:
        recency_score = 1

    # Frequency（总活跃天数 + 减压次数）
    total_days = member.get('total_days', 0)
    total_sessions = behavior.get('total_relax_sessions', 0)
    total_analyses = meta.get('total_interactions', 0)
    total_use = total_sessions + total_analyses + total_days

    if total_use >= 50:
        frequency_score = 5
    elif total_use >= 30:
        frequency_score = 4
    elif total_use >= 15:
        frequency_score = 3
    elif total_use >= 5:
        frequency_score = 2
    else:
        frequency_score = 1

    # Monetary（睡眠评分值代替消费金额）
    scores = member.get('daily_scores', [])
    recent_scores = [s.get('score', 0) for s in scores[-7:] if s.get('score')]
    avg_score = sum(recent_scores) / len(recent_scores) if recent_scores else 0

    # 低评分=高价值（睡眠差的人更需要付费方案）
    score_value = 0
    if avg_score >= 85:
        score_value = 1   # 睡得好，不太需要付费
    elif avg_score >= 70:
        score_value = 2
    elif avg_score >= 55:
        score_value = 3
    elif avg_score >= 40:
        score_value = 4
    elif avg_score > 0:
        score_value = 5   # 睡得极差，最需要付费方案
    else:
        score_value = 3   # 无数据，中间值

    return {
        'recency_score': recency_score,
        'frequency_score': frequency_score,
        'score_value': score_value,
        'rfm_total': recency_score + frequency_score + score_value,
        'avg_recent_score': avg_score,
    }


def infer_purchase_intent(rfm, profile, lifecycle):
    """
    推断付费意愿（0.0 - 1.0）
    多因子加权:
    - RFM总分（权重0.4）
    - 生命周期阶段（权重0.3）
    - 历史订单记录（权重0.2）
    - 减压完成率（权重0.1）
    """
    rfm_total = rfm['rfm_total']

    # 1. RFM因子
    # RFM 3-15分段映射到 0-1
    rfm_factor = (rfm_total - 3) / 12.0

    # 2. 生命周期因子
    stage_factor_map = {
        'cold': 0.05,
        'new': 0.20,
        'active': 0.40,
        'engaged': 0.60,
        'loyal': 0.75,
        'churn_risk': 0.35,
        'churned': 0.10,
    }
    stage_factor = stage_factor_map.get(lifecycle, 0.2)

    # 3. 历史订单因子（以前付过费更愿意再付）
    order_history = profile.get('order_history', [])
    order_factor = min(0.20, len(order_history) * 0.10)
    # 有未过期会员也不推
    current_level = profile.get('member', {}).get('level', 'free')
    if current_level == 'unlimited':
        return 0.0  # 已经是最高等级

    # 4. 完成率因子
    behavior = profile.get('behavior_stats', {})
    total_sessions = behavior.get('total_relax_sessions', 0)
    completed = behavior.get('total_completed_sessions', 0)
    completion_rate = (completed / total_sessions) if total_sessions > 0 else 0.5
    completion_factor = min(completion_rate * 0.10, 0.10)

    intent = rfm_factor * 0.40 + stage_factor * 0.30 + order_factor * 0.20 + completion_factor * 0.10
    return round(min(intent, 1.0), 3)


def compute_discount_tier(intent, lifecycle, current_level):
    """
    动态定价: 根据付费意愿和生命周期决定折扣策略
    返回: (base_tier, discounted_price, discount_label)
    """
    if current_level == 'unlimited':
        return None, None, None

    target_tier = 'unlimited' if current_level == 'pro' else 'pro'

    # 冷启动/新用户 → 首月特惠
    if lifecycle in ('cold', 'new'):
        if target_tier == 'pro' and PRICING['pro'].get('price_monthly_offer'):
            return target_tier, PRICING['pro']['price_monthly_offer'], '新客首月'
        elif target_tier == 'unlimited' and PRICING['unlimited'].get('price_monthly_offer'):
            return target_tier, PRICING['unlimited']['price_monthly_offer'], '新客首月'

    # 低付费意愿 → 首月折扣
    if intent < 0.4:
        if target_tier == 'pro':
            return target_tier, round(PRICING['pro']['price_monthly'] * 0.6, 1), '限时6折'
        else:
            return target_tier, round(PRICING['unlimited']['price_monthly'] * 0.7, 1), '限时7折'

    # 中等付费意愿 → 标准价
    if intent < 0.7:
        return target_tier, PRICING[target_tier]['price_monthly'], None

    # 高付费意愿 → 引导年卡
    if lifecycle == 'loyal':
        return target_tier, PRICING[target_tier]['price_yearly'], '年付特惠'

    return target_tier, PRICING[target_tier]['price_monthly'], None


# ========== 推荐语模板系统（A/B测试友好） ==========
AB_TEST_VARIANTS = {
    'heavy_free': {
        'A': '您已累计分析{total_usage}次，专业版每月可解锁500次深度分析+详细报告，让您的睡眠管理更精准。',
        'B': '用了{total_usage}次还免费？专业版仅¥{price}/月，下次分析就能看到完整报告。',
    },
    'scorer_low': {
        'A': '您的睡眠评分偏低，专业版提供完整诊断报告和个性化改善方案，助您突破瓶颈。',
        'B': '评分连续{streak_days}天低于60？专业版帮你找到症结。首月仅¥{price}。',
    },
    'loyal': {
        'A': '连续使用{streak_days}天，您已经是睡眠管理达人了！升级专业版获得更精准的分析。',
        'B': '{streak_days}天打卡不断🔥 年付仅¥{price_yearly}，每天不到{price_per_day}元。',
    },
    'dedicated': {
        'A': '您是高频用户！无限版为您解锁全部潜力，让AI成为您24小时的睡眠管家。',
        'B': '用了{total_usage}次还是不够？无限版不限次数，¥{price_yearly}/年随便用。',
    },
    'churn_risk': {
        'A': '最近几天没见您了😊 有一份专属福利等您领取——升级专业版享首月特惠。',
        'B': '您的睡眠数据还在等您回来分析。回归即享{price_offer}首月体验价。',
    },
    'engaged': {
        'A': '连用{streak_days}天效果显著！专业版让每一次分析都更深入。',
        'B': '检测到您已养成习惯🎯 专业版报告能帮您发现更深层的睡眠规律。',
    },
    'default': {
        'A': '升级专业版 ¥{price_monthly}/月，解锁500次深度分析+完整报告。',
        'B': '想看得更透？专业版首月¥{price_offer}，体验深度睡眠分析。',
    }
}


def pick_message_variant(profile, scenario, tier, price, discount_label):
    """
    选择A/B变体（基于用户openid哈希决定，保证同一用户看到相同变体）
    返回: 渲染后的推荐语
    """
    openid = profile.get('openid', profile.get('user_info', {}).get('wx_openid', ''))
    # 用openid哈希决定A/B
    use_variant = 'B' if (hash(openid) % 2 == 1) else 'A'

    templates = AB_TEST_VARIANTS.get(scenario, AB_TEST_VARIANTS['default'])
    template = templates.get(use_variant, templates.get('A', ''))

    # 数据填充
    member = profile.get('member', {})
    behavior = profile.get('behavior_stats', {})
    meta = profile.get('meta_params', {})
    scores = member.get('daily_scores', [])
    recent_scores = [s.get('score', 0) for s in scores[-7:] if s.get('score')]

    total_usage = behavior.get('total_relax_sessions', 0) + meta.get('total_interactions', 0)
    streak_days = member.get('streak_days', 0)
    avg_score = round(sum(recent_scores) / len(recent_scores)) if recent_scores else 0

    # 年付折算每日价格
    price_yearly = PRICING.get(tier, {}).get('price_yearly', price * 12)
    price_per_day = round(price_yearly / 365, 1)
    price_offer = round(PRICING.get(tier, {}).get('price_monthly_offer', price), 1)

    message = template.format(
        total_usage=total_usage,
        price=price,
        price_yearly=price_yearly,
        price_per_day=price_per_day,
        price_offer=price_offer,
        price_monthly=PRICING.get(tier, {}).get('price_monthly', price),
        streak_days=streak_days,
        avg_score=avg_score,
    )

    return message, use_variant


# ========== 冷却机制 ==========
def check_cooldown(profile):
    """
    检查推荐冷却
    - 每天最多看到1次推荐
    - 上次推荐被关闭后12小时不重复推
    - 已付费用户7天内不重复推
    """
    member = profile.get('member', {})
    now = datetime.now()

    # 已付费用户的冷却
    current_level = member.get('level', 'free')
    if current_level != 'free' and current_level != 'pro':
        return False, '已是最高等级'

    # 上次推荐时间
    last_rec = member.get('_last_recommendation_time', '')
    if last_rec:
        try:
            last_time = datetime.strptime(last_rec, '%Y-%m-%d %H:%M')
            hours_since = (now - last_time).total_seconds() / 3600
            if hours_since < 12:
                return False, f'冷却中（{12 - int(hours_since)}小时后可再推荐）'
        except:
            pass

    # 今天是否已推过
    today_str = now.strftime('%Y-%m-%d')
    rec_history = profile.get('recommendation_history', [])
    today_recs = [r for r in rec_history if r.get('date', '').startswith(today_str)]
    if len(today_recs) >= 1:
        return False, '今日已推荐'

    return True, None


def record_recommendation(profile, scenario, tier, variant, price, message):
    """记录推荐事件，用于A/B测试分析和冷却"""
    history = profile.setdefault('recommendation_history', [])
    history.append({
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'scenario': scenario,
        'tier': tier,
        'variant': variant,
        'price': price,
        'message': message,
        'clicked': False,
        'converted': False,
    })
    member = profile.setdefault('member', {})
    member['_last_recommendation_time'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    return history


def record_recommendation_click(profile, scenario, variant):
    """记录用户点击了推荐"""
    history = profile.get('recommendation_history', [])
    for r in reversed(history):
        if r.get('scenario') == scenario and r.get('variant') == variant:
            r['clicked'] = True
            r['clicked_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            break


def record_conversion(profile, tier, order_no):
    """记录用户付费转化"""
    history = profile.get('recommendation_history', [])
    for r in reversed(history):
        if not r.get('converted'):
            r['converted'] = True
            r['converted_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            r['converted_tier'] = tier
            r['order_no'] = order_no
            break


# ========== 主推荐接口 ==========
def get_smart_recommendation(openid):
    """
    专业版推荐引擎主入口

    流程:
    1. 加载用户画像
    2. 生命周期分群
    3. RFM评分
    4. 付费意愿推断
    5. 冷却检查
    6. 动态定价
    7. 场景匹配 → 推荐语生成（A/B变体）
    8. 记录推荐事件

    返回: 推荐结果字典
    """
    from deepseek_proxy import _load_user_profile  # 延迟导入避免循环

    profile = _load_user_profile(openid)
    if not profile:
        return {'should_recommend': False, 'reason': '用户不存在'}

    # 确保 openid 在 profile 中
    profile['openid'] = openid

    member = profile.get('member', {})
    current_level = member.get('level', 'free')

    # 已是最高等级不推
    if current_level == 'unlimited':
        return {'should_recommend': False, 'reason': '已是最高等级'}

    # 生命周期
    lifecycle = classify_lifecycle(profile)

    # RFM评分
    rfm = compute_rfm(profile)

    # 付费意愿
    intent = infer_purchase_intent(rfm, profile, lifecycle)

    # 冷却检查
    cooldown_ok, cooldown_reason = check_cooldown(profile)
    if not cooldown_ok:
        return {'should_recommend': False, 'reason': cooldown_reason}

    # 动态定价
    tier, price, discount_label = compute_discount_tier(intent, lifecycle, current_level)
    if not tier:
        return {'should_recommend': False, 'reason': '无合适套餐'}

    # 场景匹配
    behavior = profile.get('behavior_stats', {})
    meta = profile.get('meta_params', {})
    total_usage = behavior.get('total_relax_sessions', 0) + meta.get('total_interactions', 0)
    streak_days = member.get('streak_days', 0)
    scores = member.get('daily_scores', [])
    recent_scores = [s.get('score', 0) for s in scores[-7:] if s.get('score')]
    avg_score = round(sum(recent_scores) / len(recent_scores)) if recent_scores else 0

    # 场景优先级: 免费→低分→忠实→高频→流失->默认
    scenario = 'default'
    if current_level == 'free' and total_usage >= 15 and avg_score < 70 and streak_days >= 3:
        scenario = 'heavy_free'
    elif current_level == 'free' and avg_score < 60 and streak_days >= 2:
        scenario = 'scorer_low'
    elif current_level == 'free' and streak_days >= 7:
        scenario = 'loyal'
    elif current_level == 'pro' and total_usage >= 25:
        scenario = 'dedicated'
    elif lifecycle == 'churn_risk':
        scenario = 'churn_risk'
    elif lifecycle in ('active', 'engaged'):
        scenario = 'engaged'

    # 生成推荐语（A/B变体）
    message, variant = pick_message_variant(profile, scenario, tier, price, discount_label)

    # 附加折扣标签
    display_price = price
    if discount_label:
        display_price = price  # 实际价格
        original_price = PRICING.get(tier, {}).get('price_monthly', price)
    else:
        original_price = price

    # 构建结果
    result = {
        'should_recommend': True,
        'scenario': scenario,
        'tier': tier,
        'message': message,
        'price': price,
        'original_price': PRICING.get(tier, {}).get('price_monthly', price),
        'discount_label': discount_label,
        'icon': PRICING.get(tier, {}).get('icon', ''),
        'lifecycle': lifecycle,
        'rfm_score': rfm['rfm_total'],
        'intent_score': intent,
        'variant': variant,
        # 付费意愿驱动年卡推荐
        'recommend_yearly': lifecycle == 'loyal' and intent >= 0.6,
    }

    # 记录推荐事件
    profile['openid'] = openid
    record_recommendation(profile, scenario, tier, variant, price, message)
    from deepseek_proxy import _save_user_profile
    _save_user_profile(profile, openid)

    return result


def get_pricing_info():
    """获取定价全信息"""
    return {
        'pricing': PRICING,
        'lifecycle_stages': LIFECYCLE_STAGES,
        'ab_variants': {
            k: list(v.keys()) for k, v in AB_TEST_VARIANTS.items()
        }
    }
