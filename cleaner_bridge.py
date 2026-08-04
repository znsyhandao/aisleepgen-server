"""
cleaner_bridge.py — 清道夫系统 ↔ 清醒的质量 数据桥接

【突变动力学声明】
- 本文件为纯新增，不修改任何现有文件
- 依赖：仅通过 user_profile.json 与现有系统共享数据
- 回滚：直接删除即可，无副作用

清道夫系统（独立项目）负责追踪用户的精神消耗（社交、信息过载、任务切换等），
给出每日"精神负担系数"。本模块负责读取这些数据并转换为AISleepGen世界模型
可用的入参格式。
"""

import json, os, datetime
from typing import Optional

# 清道夫数据目录（可环境变量覆盖）
CLEANER_DATA_DIR = os.environ.get(
    'CLEANER_DATA_DIR',
    os.path.join(os.path.dirname(__file__), 'data', 'cleaner')
)

# AISleepGen用户画像目录
USER_PROFILE_DIR = os.path.dirname(
    os.environ.get('USER_PROFILE_PATH', 
                   os.path.join(os.path.dirname(__file__), 'user_profile.json'))
)


# ── 公开接口 ──

def query_cleaner_status(openid: str) -> dict:
    """
    查询用户在清道夫系统中的当日状态
    
    返回：
        baseline: 用户精神消耗基线（1.0 = 正常）
        today: 当日精神消耗系数（>1 = 超负荷，<1 = 轻松）
        ratio: today/baseline 比值
        sources: 主要消耗源列表
        has_data: 是否有清道夫数据
    """
    path = os.path.join(CLEANER_DATA_DIR, f'cleaner_{openid}.json')
    if not os.path.exists(path):
        return {
            'baseline': 1.0,
            'today': 1.0,
            'ratio': 1.0,
            'sources': [],
            'has_data': False,
        }
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        baseline = data.get('baseline_consumption', 1.0)
        today = data.get('daily_consumption', 1.0)
        
        return {
            'baseline': baseline,
            'today': today,
            'ratio': today / max(baseline, 0.1),
            'sources': data.get('consumption_sources', []),
            'has_data': True,
        }
    except (json.JSONDecodeError, FileNotFoundError):
        return {
            'baseline': 1.0,
            'today': 1.0,
            'ratio': 1.0,
            'sources': [],
            'has_data': False,
        }


def get_weekly_pattern(openid: str) -> list:
    """
    获取本周清道夫数据模式（用于压力源-睡眠关联分析）
    返回：按日期倒序的7天记录列表
    """
    records = []
    today = datetime.date.today()
    
    for i in range(7):
        date = (today - datetime.timedelta(days=i)).strftime('%Y-%m-%d')
        path = os.path.join(CLEANER_DATA_DIR, f'cleaner_{openid}_{date}.json')
        
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    records.append(json.load(f))
            except (json.JSONDecodeError, FileNotFoundError):
                continue
    
    return records


def get_decision_quality_input(openid: str) -> dict:
    """
    生成决策力分析所需的输入数据
    这是清道夫系统 → 世界模型的标准数据格式
    
    返回：
        mental_load: 精神负担评分（0-100）
        top_pressure: 最大压力源类型
        pressure_detail: 压力源详情
        trend: 与昨日对比趋势（up/down/stable）
        recommendation: 简要建议
    """
    status = query_cleaner_status(openid)
    
    if not status['has_data']:
        return {
            'has_data': False,
            'mental_load': 50,
            'top_pressure': 'unknown',
            'pressure_detail': '暂无清道夫数据',
            'trend': 'stable',
            'recommendation': '建议连接清道夫系统以获取更精准的分析',
        }
    
    ratio = status['ratio']
    sources = status['sources']
    
    # 计算精神负担评分
    if ratio > 1.5:
        mental_load = min(100, int((ratio - 1.0) * 60 + 40))
        trend = 'up'
    elif ratio < 0.7:
        mental_load = max(0, int(ratio * 30))
        trend = 'down'
    else:
        mental_load = int(ratio * 50)
        trend = 'stable'
    
    # 找最大压力源
    top_source = max(sources, key=lambda s: s.get('impact', 0)) if sources else {}
    
    return {
        'has_data': True,
        'mental_load': mental_load,
        'top_pressure': top_source.get('type', 'unknown') if sources else 'none',
        'pressure_detail': sources[:3] if sources else [],
        'trend': trend,
        'recommendation': _generate_recommendation(ratio, sources),
    }


# ── 内部辅助 ──

def _generate_recommendation(ratio: float, sources: list) -> str:
    """根据清道夫数据生成简要建议"""
    if ratio > 1.5:
        if any(s.get('type') == 'social' for s in sources):
            return '今日社交消耗较高，建议减少非必要社交互动'
        if any(s.get('type') == 'information_overload' for s in sources):
            return '信息过载较严重，建议今日执行信息斋戒'
        return '精神负担偏重，建议降低今日决策密度，聚焦核心事项'
    elif ratio < 0.7:
        return '今日状态轻松，适合处理高难度决策'
    else:
        return '状态正常，维持当前节奏'


def load_user_profile(openid: str) -> dict:
    """读取用户画像（复用现有系统数据）"""
    path = os.path.join(USER_PROFILE_DIR, 'user_profile.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


# ── [清醒的质量] 冷启动角色推导 ──

def detect_role_from_history(profile: dict) -> str:
    """
    从用户历史行为自动推导角色。
    不依赖前端选择，纯后端逻辑。
    
    规则：
    - 连续3天有数据 + 次数>=5 → professional
    - 有手机号或已付费 → premium
    - 其它 → explorer
    
    返回: 'explorer' | 'professional' | 'premium'
    """
    history = profile.get('history', [])
    total = profile.get('total_sessions', 0)
    user_info = profile.get('user_info', {})
    member = profile.get('member', {})
    
    # 检查已付费
    if member.get('tier') in ('pro', 'unlimited') or member.get('paid_days', 0) > 0:
        return 'premium'
    
    # 检查有手机号（实名用户倾向）
    if user_info.get('phone'):
        return 'premium'
    
    # 检查活跃度
    if len(history) >= 5 and total >= 10:
        return 'professional'
    
    # 连续活跃检测
    if len(history) >= 3:
        # 取最近3条
        recent = history[-3:]
        if all(h.get('score', 0) > 0 for h in recent):
            return 'professional'
    
    return 'explorer'


def save_role_to_profile(openid: str, role: str) -> bool:
    """写 role 到 user_profile.json"""
    import os, json, datetime
    
    profile_dir = os.path.dirname(
        os.environ.get('USER_PROFILE_PATH',
                       os.path.join(os.path.dirname(__file__), 'user_profile.json'))
    )
    path = os.path.join(profile_dir, 'user_profile.json')
    
    if not os.path.exists(path):
        return False
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if openid not in data:
            return False
        
        if not isinstance(data[openid], dict):
            return False
        
        old_role = data[openid].get('role', 'not set')
        if old_role == role:
            return True  # 无需更新
        
        data[openid]['role'] = role
        data[openid]['role_inferred_at'] = datetime.datetime.now().isoformat()
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception:
        return False


# ── 数据采集：用户每日消耗自报/API ──

def handle_cleaner_sync(openid, data):
    """接收前端/chat提取的消耗数据，写入 cleaner 数据文件"""
    mental_load = data.get('mental_load', 50)
    top_pressure = data.get('top_pressure', 'unknown')
    pressure_detail = data.get('pressure_detail', [])
    source = data.get('source', 'manual')

    record = {
        'baseline_consumption': 1.0,
        'daily_consumption': round(1.0 + (mental_load - 50) / 100.0, 2),
        'consumption_sources': pressure_detail or (
            [{'type': top_pressure, 'level': 'medium', 'description': '用户自报消耗'}]
            if top_pressure != 'unknown' else []
        ),
        'last_updated': datetime.datetime.now().isoformat(),
    }

    os.makedirs(CLEANER_DATA_DIR, exist_ok=True)
    with open(os.path.join(CLEANER_DATA_DIR, 'cleaner_' + openid + '.json'), 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return {'status': 'ok'}


_parse_keywords = {
    'social': ['社交', 'social', '会议', 'meeting', '团建', '人际', '应酬',
               '跟人', '聊天', '说话多', '沟通', '社交消耗'],
    'work': ['工作', 'work', '加班', '赶工', '项目', 'deadline', '任务',
             '开会', '汇报', '工作压力'],
    'info': ['信息', 'info', '阅读', 'reading', '刷信息', '资讯',
             '学习', '上课', '读书', '论文', '研究'],
    'emotion': ['焦虑', 'anxiety', '担心', 'worried', '烦躁', '情绪',
                '低气压', '心情差', '难过', '沮丧'],
}


def parse_cleaner_from_chat(openid, user_message, ai_reply=None):
    """从聊天对话中提取消耗数据（关键词匹配，轻量无模型）"""
    msg = user_message.lower()
    import re

    # 数字匹配：用户说"7分"或"7/10"
    score = 0
    source = None
    reasons = []
    score_match = re.findall(r'(\d+)\s*(分|级|/10)', msg)
    if score_match:
        raw = int(score_match[-1][0])
        score = min(100, max(0, raw * 10 if raw <= 10 else raw))

    if score == 0:
        for s_type, keywords in _parse_keywords.items():
            for kw in keywords:
                if kw in msg:
                    source = s_type
                    reasons.append(s_type)
                    break
        hit_count = len(reasons)
        if hit_count >= 3:
            score = 75
        elif hit_count == 2:
            score = 60
        elif hit_count == 1:
            score = 45
        else:
            general = ['累', 'tired', '疲惫', '疲劳', '乏', '没精神', '困', '消耗']
            if any(w in msg for w in general):
                score = 50
                source = source or 'general'

    if score > 0:
        sync_data = {
            'mental_load': score,
            'top_pressure': source or 'general',
            'pressure_detail': [{'type': s, 'level': 'medium', 'description': user_message[:60]}
                                for s in (reasons or [source or 'general'])],
            'source': 'chat_parse',
        }
        handle_cleaner_sync(openid, sync_data)
        return sync_data

    return {}

