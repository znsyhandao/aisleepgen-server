# -*- coding: utf-8 -*-
"""
himiko_heart.py — AISleepGen 主动健康伙伴心脏

"一个你会一直带着的AI健康伙伴"

不是问答工具。是观察-思考-行动循环。

功能：
1. 后台事件驱动：用户feedback/健康数据变化主动触发思考
2. 主动对话：发现异常/变化/机会时，主动push对话建议
3. 健康数据自动获取：分析用户授权的手环/手表数据
4. 持续学习：每次对话后更新用户模型
5. 语音优先：语音输入为默认交互

集成方式：作为心跳管线的第一阶段，在现有_Before_ButlerScheduler_之前执行
"""

import os, json, time, sys, threading, random
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

BASE = r'D:\AISleepGen_Optimized'
DATA_DIR = os.path.join(BASE, 'data')
FB_PATH = os.path.join(DATA_DIR, 'feedback.json')
PROFILE_DIR = os.path.join(BASE, 'user_profiles')
LOG_PATH = os.path.join(BASE, 'logs', 'himiko.log')

# ─── 用户状态时间窗口（多久算"活跃"） ───
ACTIVE_WINDOW_HOURS = 72       # 72小时无数据视为不活跃
DEEP_WINDOW_HOURS = 24         # 24小时无数据触发主动问候
URGENT_WINDOW_HOURS = 6        # 6小时内连续异常→紧急推送


class HimikoHeart:
    """
    姬心脏：持续健康观察引擎
    
    每轮运行：
    1. 扫描所有用户的feedback → 检测状态变化
    2. 检测是否该主动对话
    3. 检测健康数据是否需自动获取
    4. 生成主动对话建议（暂不推送，等用户下次交互）
    """

    def __init__(self):
        self.now = datetime.now()
        self.today = self.now.strftime('%Y-%m-%d')
        self.logs = []

    def log(self, msg):
        """安全日志"""
        safe = ''.join(c if ord(c) < 128 else '?' for c in msg)
        self.logs.append(safe)
        print(f'  [\u65e5\u5411] {safe}')

    def run(self):
        """运行一轮主动观察"""
        self.log('姬心脏启动...')

        feedbacks = self._load_feedbacks()
        if not feedbacks:
            self.log('无feedback数据')
            return self._result()

        real_fbs = [f for f in feedbacks if not str(f.get('openid','')).startswith('virt_') and f.get('openid','') not in ('reg_test','test')]
        virt_fbs = [f for f in feedbacks if str(f.get('openid','')).startswith('virt_')]

        self.log(f'feedback: {len(real_fbs)}条真实 + {len(virt_fbs)}条虚拟')

        # 1. 按用户分组
        users_feedback = {}
        for fb in feedbacks:
            uid = fb.get('openid', '')
            if uid not in users_feedback:
                users_feedback[uid] = []
            users_feedback[uid].append(fb)

        self.log(f'活跃用户数: {len(users_feedback)}')

        # 2. 每个用户分析状态变化
        self.log(f'扫描 {len(users_feedback)} 个用户的状态...')
        event_count = 0
        for uid, fbs in users_feedback.items():
            events = self._analyze_user(uid, fbs)
            event_count += len(events)

        # 3. 检查系统是否需要主动对话（全局事件）
        sys_events = self._check_system_events()
        self.log(f'用户事件: {event_count}, 系统事件: {len(sys_events)}')

        # 4. 保存分析结果
        result = self._result({
            'user_analyzed': len(users_feedback),
            'user_events': event_count,
            'system_events': len(sys_events),
            'total_events': event_count + len(sys_events),
        })

        self.log(f'姬心脏完成: {event_count + len(sys_events)}个事件')
        return result

    def _load_feedbacks(self):
        try:
            with open(FB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []

    def _analyze_user(self, uid, fbs):
        """分析单用户状态，返回事件列表"""
        events = []
        if not fbs:
            return events

        # 排序按时序
        sorted_fbs = sorted(fbs, key=lambda x: x.get('time', ''))
        latest = sorted_fbs[-1]
        latest_time = latest.get('time', self.now.isoformat())

        # 检测最新feedback时间
        try:
            dt = datetime.fromisoformat(latest_time) if 'T' in latest_time else datetime.strptime(latest_time[:10], '%Y-%m-%d')
        except:
            dt = self.now

        hours_since = (self.now - dt).total_seconds() / 3600

        # 事件1: 用户24小时没来一次
        if hours_since > DEEP_WINDOW_HOURS:
            events.append({
                'type': 'inactive',
                'user': uid,
                'hours': hours_since,
                'suggested_action': 'greeting',
                'priority': 'low' if hours_since > ACTIVE_WINDOW_HOURS else 'medium',
            })

        # 事件2: 评分持续下降
        if len(sorted_fbs) >= 3:
            recent = [f.get('rating', 3) for f in sorted_fbs[-3:]]
            if all(r is not None for r in recent):
                if recent[2] < recent[0] - 0.5:
                    events.append({
                        'type': 'trend_down',
                        'user': uid,
                        'delta': recent[0] - recent[2],
                        'suggested_action': 'concern_check',
                        'priority': 'high',
                    })

        # 事件3: 疼痛指数飙升
        if len(sorted_fbs) >= 2:
            p1 = sorted_fbs[-2].get('pain', 3) or 3
            p2 = sorted_fbs[-1].get('pain', 3) or 3
            if p2 > p1 + 1.0:
                events.append({
                    'type': 'pain_spike',
                    'user': uid,
                    'old_pain': p1,
                    'new_pain': p2,
                    'suggested_action': 'pain_check',
                    'priority': 'high',
                })

        return events

    def _check_system_events(self):
        """检测系统级别的事件（跨用户）"""
        events = []

        # 检查是否有新跑完的实验结果
        expt_dir = os.path.join(DATA_DIR, 'experiments')
        if os.path.exists(expt_dir):
            for fn in os.listdir(expt_dir):
                if not fn.endswith('.json') or fn.startswith('_'):
                    continue
                fp = os.path.join(expt_dir, fn)
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        d = json.load(f)
                    if d.get('status') in ('completed', 'finished', 'finished_conclusive') and d.get('brain') == 'left':
                        events.append({
                            'type': 'experiment_result',
                            'user': '_system',
                            'detail': f'{d.get("knob_key","?")}: {d.get("direction","?")} (左脑获胜)',
                            'suggested_action': 'inform_user',
                            'priority': 'low',
                        })
                except:
                    pass

        return events

    def _result(self, extra=None):
        base = {
            'timestamp': self.now.isoformat(),
            'message': 'himiko_heart run complete',
        }
        if extra:
            base.update(extra)
        return base


def generate_active_conversation(uid, events, profile=None):
    """
    根据事件生成主动对话内容（用于用户下次交互时的开场白）
    
    返回: {greeting_type, message, context}
    """
    if not events:
        return None

    # 取最高优先级事件
    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    sorted_events = sorted(events, key=lambda e: priority_order.get(e.get('priority', 'low'), 2))
    top = sorted_events[0]

    templates = {
        'greeting': [
            f'昨天你睡得怎么样？我看到你好久没来了，有点担心你。',
            f'最近过的怎么样？好久不见你了，有什么新鲜事吗？',
        ],
        'concern_check': [
            f'看你最近的评分有点下降，是不是遇到什么烦心事了？',
            f'你的睡眠评分最近有点波动，要不要聊聊？',
        ],
        'pain_check': [
            f'看到你的疼痛指数涨了，是不是身体不舒服？',
            f'昨晚是不是身体不太舒服？数据上看到了一些变化。',
        ],
        'inform_user': [
            f'系统发现一个新发现，想跟你聊聊——关于你的睡眠模式。',
        ],
    }

    action = top.get('suggested_action', 'greeting')
    replies = templates.get(action, templates['greeting'])

    return {
        'type': action,
        'priority': top.get('priority', 'low'),
        'message': random.choice(replies),
        'events': events,
        'context': {
            'time': datetime.now().isoformat(),
            'user_inactive_hours': top.get('hours', 0),
        }
    }


if __name__ == '__main__':
    print('姬心脏测试')
    print('=' * 40)
    heart = HimikoHeart()
    result = heart.run()
    print(f'\n结果: {json.dumps(result, ensure_ascii=False, indent=2)}')
    
    # 测试主动对话生成
    print('\n--- 模拟主动对话 ---')
    test_events = [
        {'type': 'trend_down', 'user': 'test', 'delta': 1.2, 'suggested_action': 'concern_check', 'priority': 'high'}
    ]
    conv = generate_active_conversation('test', test_events)
    if conv:
        print(f'[优先级:{conv["priority"]}] {conv["message"]}')
