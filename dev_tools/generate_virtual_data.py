# -*- coding: utf-8 -*-
"""为AISleepGen生成真实分布的测试数据"""

import json, os, time, random, math, sys
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\AISleepGen_Optimized'
FB_PATH = os.path.join(BASE, 'data', 'feedback.json')
PROFILE_PATH = os.path.join(BASE, 'data', 'user_profile.json')
EXPT_DIR = os.path.join(BASE, 'data', 'experiments')

# 真实睡眠APP的反馈分布（来自公开研究数据）
# 偏态分布：3-4分占60%，2分和5分各15%，1分10%
RATING_DIST = [1]*10 + [2]*15 + [3]*30 + [4]*30 + [5]*15  # 共100个样本点

# 疼痛分布：轻度为主
PAIN_DIST = [1]*25 + [2]*30 + [3]*25 + [4]*15 + [5]*5

# 情绪分布：中等偏上
MOOD_DIST = [1]*5 + [2]*15 + [3]*35 + [4]*30 + [5]*15

# 焦虑分布：中等偏下
ANXIETY_DIST = [1]*20 + [2]*35 + [3]*25 + [4]*15 + [5]*5

# 能量分布
ENERGY_DIST = [1]*10 + [2]*20 + [3]*35 + [4]*25 + [5]*10

# 虚拟用户池（2个低频用户+2个高频用户）
VIRTUAL_USERS = [
    {'openid': 'virt_alice', 'frequency': 10, 'sleep_time': '23:00', 'wake_time': '07:00'},
    {'openid': 'virt_bob', 'frequency': 5, 'sleep_time': '00:30', 'wake_time': '08:30'},
    {'openid': 'virt_carol', 'frequency': 15, 'sleep_time': '22:30', 'wake_time': '06:30'},
    {'openid': 'virt_dave', 'frequency': 3, 'sleep_time': '01:00', 'wake_time': '09:00'},
]

# 每个虚拟用户的评分偏置（有些人天生乐观/悲观）
USER_BIAS = {
    'virt_alice': {'rating': 0.3, 'pain': -0.5, 'mood': 0.4},
    'virt_bob': {'rating': -0.2, 'pain': 0.3, 'mood': -0.3},
    'virt_carol': {'rating': 0.5, 'pain': -0.3, 'mood': 0.6},
    'virt_dave': {'rating': -0.4, 'pain': 0.6, 'mood': -0.5},
}


def _load_existing():
    """加载已有feedback，保留真实用户数据"""
    if os.path.exists(FB_PATH):
        with open(FB_PATH, 'r', encoding='utf-8') as f:
            fbs = json.load(f)
        # 保留真实用户数据
        real = [fb for fb in fbs if fb.get('openid', '') not in ('reg_test', 'test')
                and not str(fb.get('openid', '')).startswith('virt_')]
        print(f'保留真实数据: {len(real)}条')
        return real
    return []


def _sample_from(dist):
    """从分布中采样"""
    return random.choice(dist)


def _clamp(val, lo=1, hi=5):
    return max(lo, min(hi, val))


def _bias_shift(base_val, bias):
    """应用用户偏置"""
    if bias > 0:
        return _clamp(base_val + random.uniform(0, bias))
    else:
        return _clamp(base_val + random.uniform(bias, 0))


def generate_day(user, day_offset):
    """为某个用户生成一天的feedback"""
    openid = user['openid']
    freq = user['frequency']
    bias = USER_BIAS.get(openid, {})
    
    # 基于频率决定今天是否有feedback
    if random.random() > freq / 20:  # 20为最大频率归一化
        return None
    
    date = (datetime.now() - timedelta(days=day_offset)).strftime('%Y-%m-%d')
    
    # 基础值
    base_rating = _sample_from(RATING_DIST)
    base_pain = _sample_from(PAIN_DIST)
    base_mood = _sample_from(MOOD_DIST)
    base_anxiety = _sample_from(ANXIETY_DIST)
    base_energy = _sample_from(ENERGY_DIST)
    
    # 应用用户偏置
    rating = _bias_shift(base_rating, bias.get('rating', 0))
    pain = _bias_shift(base_pain, bias.get('pain', 0))
    mood = _bias_shift(base_mood, bias.get('mood', 0))
    
    # 睡眠时间（基于用户习惯+随机波动）
    sleep_h, sleep_m = map(int, user['sleep_time'].split(':'))
    wake_h, wake_m = map(int, user['wake_time'].split(':'))
    
    sleep_h_actual = _clamp(sleep_h + random.randint(-1, 1), 20, 4) if sleep_h < 5 else _clamp(sleep_h + random.randint(-1, 1), 20, 28)
    # 简化：用固定时间
    sleep_latency = random.randint(15, 90)  # 入睡潜伏期 15-90分钟
    awake_times = random.randint(0, 4)      # 醒来次数
    total_duration = random.uniform(4.5, 9.0)  # 总睡眠时长
    
    # 评分合理性约束：如果睡眠时长<5h，评分不能>4
    if total_duration < 5 and rating > 4:
        rating = 4
    if total_duration > 8 and rating < 2:
        rating = 3
    
    # 至少有一条feedback在"最近"以便新鲜度检测
    time_str = f'{date}T{random.randint(6, 10):02d}:{random.randint(0, 59):02d}:00'
    
    feedback = {
        'openid': openid,
        'time': time_str,
        'rating': rating,
        'pain': pain,
        'mood': mood,
        'anxiety': _clamp(base_anxiety + random.uniform(-0.5, 0.5)),
        'energy': _clamp(base_energy + random.uniform(-0.5, 0.5)),
        'sleep_latency': sleep_latency,
        'awake_times': awake_times,
        'total_duration': round(total_duration, 1),
        'sleep_score': round(rating * 20 + random.uniform(-5, 5), 0),
        'satisfaction': rating if random.random() < 0.7 else _clamp(rating + random.choice([-1, 1])),
        'wakeup_mood': mood if random.random() < 0.6 else _clamp(mood + random.choice([-1, 1])),
        'efficiency': round(85 - awake_times * 3 + random.uniform(-5, 5), 0),
        'recovering': random.choice([True, False]),
        'depth': random.choice(['light', 'medium', 'deep']),
        'is_virtual': True,
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }
    
    return feedback


def generate(day_span=7):
    """生成过去N天的虚拟用户feedback"""
    existing = _load_existing()
    
    new_feedbacks = []
    for day_offset in range(day_span):
        for user in VIRTUAL_USERS:
            fb = generate_day(user, day_offset)
            if fb:
                new_feedbacks.append(fb)
    
    all_feedbacks = existing + new_feedbacks
    all_feedbacks.sort(key=lambda x: x.get('time', ''))
    
    print(f'生成 {len(new_feedbacks)} 条虚拟feedback (来自{len(VIRTUAL_USERS)}个用户, {day_span}天跨度)')
    print(f'总feedback: {len(all_feedbacks)} (含{len(existing)}条真实)')
    
    # 写入
    with open(FB_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_feedbacks, f, ensure_ascii=False, indent=2)
    
    # 统计
    from collections import Counter
    rating_dist = Counter(fb.get('rating') for fb in new_feedbacks)
    print(f'评分分布: {dict(sorted(rating_dist.items()))}')
    
    user_counts = Counter(fb.get('openid') for fb in new_feedbacks)
    print(f'用户分布: {dict(user_counts)}')
    
    # 验证新鲜度
    latest = max(fb.get('time', '') for fb in new_feedbacks)
    print(f'最新feedback: {latest}')
    
    return len(new_feedbacks)


def update_calibration_min_users():
    """降低所有实验的 min_users_per_group 以适配测试环境"""
    expts = [f for f in os.listdir(EXPT_DIR) if f.endswith('.json') and not f.startswith('_')]
    changed = 0
    for fn in expts:
        fp = os.path.join(EXPT_DIR, fn)
        with open(fp, 'r', encoding='utf-8') as f:
            d = json.load(f)
        if d.get('min_users_per_group', 999) > 2:
            d['min_users_per_group'] = 2
            d['min_days'] = 1  # 一天就能出结果
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            changed += 1
    print(f'更新 {changed} 个实验的 min_users_per_group=2, min_days=1')


if __name__ == '__main__':
    print('AISleepGen 虚拟测试数据生成器')
    print('=' * 40)
    
    n = generate(day_span=7)
    print()
    update_calibration_min_users()
    print()
    print(f'✅ 生成完成: {n} 条虚拟feedback')
    print(f'   4个虚拟用户: alice(高频,乐观), bob(低频,悲观), carol(高频,非常乐观), dave(低频,悲观)')
    print(f'   分布: rating=3-4偏态, pain=轻中度, mood=中上')
    print(f'   后端可以开始测试全部闭环组件')
