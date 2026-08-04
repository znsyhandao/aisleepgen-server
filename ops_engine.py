"""
ops_engine.py — 内嵌运营引擎

专注三件事：
1. 用户激活：新用户第一次进来就能产生"wow"时刻
2. 次日留存：用户离开后为什么回来
3. 传播裂变：用户为什么想分享

不碰增长黑客/投放/商业化——那些需要真人决策。
"""

import json, os, time
from datetime import datetime, timedelta
from typing import Dict, Optional


# ===== 用户旅程里程碑 =====
# 定义用户从新用户到规律用户的"进化阶梯"
MILESTONES = {
    1: {
        'name': '首次对话',
        'trigger': '第一次发送消息',
        'action': 'return_wow',  # 让用户第一次就感受到"好专业"
        'reward': None,
    },
    2: {
        'name': '完成评分',
        'trigger': '第一次给反馈评星',
        'action': 'show_improvement',
        'reward': None,
    },
    3: {
        'name': '连续2晚记录',
        'trigger': '出现2天数据',
        'action': 'unlock_timeline',
        'reward': '时间线功能解锁',
    },
    4: {
        'name': '连续5晚记录',
        'trigger': '5天数据',
        'action': 'unlock_trend_report',
        'reward': '趋势报告解锁',
    },
    5: {
        'name': '连续7晚记录',
        'trigger': '7天数据',
        'action': 'deliver_weekly',
        'reward': '周报告可分享',
    },
}


def get_next_milestone(profile: Dict) -> Dict:
    """判断用户当前进度，返回下一个里程碑"""
    member = profile.get('member', {})
    daily = member.get('daily_scores', []) or []
    unique_days = len(set(d.get('date','') for d in daily if d.get('date')))
    total_sessions = profile.get('total_sessions', 0)
    
    milestones_passed = []
    
    if total_sessions >= 1:
        milestones_passed.append(1)
    # 检查是否有评分
    has_feedback = False
    try:
        fb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'feedback.json')
        if os.path.exists(fb_path):
            with open(fb_path, 'r', encoding='utf-8') as f:
                fbs = json.load(f)
            uid = profile.get('openid', '')
            has_feedback = any(fb.get('openid', '')[:16] == uid[:16] for fb in fbs)
    except Exception:
        pass
    if has_feedback:
        milestones_passed.append(2)
    if unique_days >= 2:
        milestones_passed.append(3)
    if unique_days >= 5:
        milestones_passed.append(4)
    if unique_days >= 7:
        milestones_passed.append(5)
    
    next_m = len(milestones_passed) + 1
    if next_m <= 5:
        return {
            'current': milestones_passed[-1] if milestones_passed else 0,
            'next': MILESTONES[next_m],
            'progress': f'{unique_days}/7天',
            'progress_pct': min(100, int(unique_days / 7 * 100)),
        }
    return {
        'current': 5,
        'next': None,
        'progress': '已完成',
        'progress_pct': 100,
    }


def craft_welcome_message(profile: Dict) -> str:
    """为新用户生成初次对话时的欢迎语"""
    total = profile.get('total_sessions', 0)
    if total > 0:
        return ''
    
    return (
        '我是你的睡眠管家，今天刚开始为你服务 😊\n'
        '你可以直接告诉我昨晚睡得怎么样，比如：\n'
        '"昨晚11点睡，7点醒，中间醒了一次"'
    )


def craft_retention_push(user_data: Dict) -> Optional[str]:
    """
    生成让用户回来的推送文案
    
    这东西会被微信小程序调用作为服务通知。
    但小程序没法主动给用户发消息（需要formId），
    所以这是给服务器用的——当用户主动触发butler_check时返回。
    """
    now = datetime.now()
    hour = now.hour
    
    # 晚间提醒（20:00-22:00）
    if 20 <= hour <= 22:
        return '🌙 今晚记得记录睡眠，连续记录能看到趋势变化'
    
    # 早晨问候（6:00-9:00）
    if 6 <= hour <= 9:
        return '☀️ 昨晚睡得怎么样？花30秒告诉我，获得专属分析'
    
    return None


def assess_retention_risk(profile: Dict) -> Optional[str]:
    """
    评估用户流失风险
    
    Returns: 风险等级或None
    """
    member = profile.get('member', {})
    last_active = member.get('last_active', '')
    total = profile.get('total_sessions', 0)
    
    if not last_active or total == 0:
        return None  # 新用户不判断
    
    try:
        last_dt = datetime.strptime(last_active, '%Y-%m-%d %H:%M')
        days_since = (datetime.now() - last_dt).days
    except:
        return None
    
    if days_since >= 7 and total <= 3:
        return 'high'
    if days_since >= 3 and total <= 5:
        return 'medium'
    return None


def get_user_insight_stats(profile: Dict) -> Dict:
    """
    生成用户洞察统计
    
    这些数据可以用来在微信小程序显示"你的睡眠报告比上周好XX"
    """
    member = profile.get('member', {})
    daily = member.get('daily_scores', []) or []
    
    if len(daily) < 2:
        return {'status': 'insufficient_data'}
    
    # 按日期排序
    sorted_daily = sorted(daily, key=lambda x: x.get('date', ''))
    
    # 前后半段对比
    mid = len(sorted_daily) // 2
    first = [d.get('score', 0) for d in sorted_daily[:mid] if d.get('score')]
    last = [d.get('score', 0) for d in sorted_daily[mid:] if d.get('score')]
    
    if first and last:
        avg_first = sum(first) / len(first)
        avg_last = sum(last) / len(last)
        change = round(avg_last - avg_first, 1)
        
        return {
            'status': 'ready',
            'days': len(sorted_daily),
            'trend': 'improving' if change > 5 else ('declining' if change < -5 else 'stable'),
            'change': change,
            'avg': round((avg_first + avg_last) / 2, 1),
        }
    
    return {'status': 'insufficient_data'}
