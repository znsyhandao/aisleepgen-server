#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
companion_mode.py — AISleepGen 睡眠AI陪伴模式

从"问诊AI"到"床伴AI"的核心跃迁。

职责:
  1. 用户说"睡不着"时，启动陪伴模式状态机
  2. 根据用户状态（呼吸/体动/时间）自动切换策略
  3. 输出可执行的引导步骤序列
  4. 可被 chat handler 或 独立API 调用

状态机:
  IDLE → ACTIVE (用户发起陪伴)
    ├─ CALMING: 呼吸引导 (4-7-8)
    ├─ GUIDING: 身体扫描 / 正念 (渐进)
    ├─ MONITORING: 安静跟踪 (如果安静保持→渐弱)
    ├─ RELAPSE: 用户又动→切回GUIDING
    └─ EXIT: 检测到入睡 / 用户取消

协议安全：所有引导文本都是预定义模板，不做自由生成。
"""

import json
import time
import math
import logging
from datetime import datetime, timedelta

# 具身上下文集成
try:
    from body_context import report_body_event as _report_body_ev
    _HAS_BODY_CTX = True
except ImportError:
    _HAS_BODY_CTX = False

_log = logging.getLogger('aisleepgen.companion')

# ===== 陪伴模式状态 =====
STATES = {
    'INIT': 'initializing',
    'CALMING': 'breath_guide',       # 呼吸引导
    'GUIDING': 'body_scan',          # 身体扫描/正念
    'MONITORING': 'quiet_monitor',   # 安静监测
    'RELEASE': 'fading_out',        # 渐弱退出
    'RELAPSE': 'return_to_guide',   # 用户又动→重返引导
    'EXIT': 'completed',            # 退出
}

# ===== 预设引导协议（安全，不自由生成） =====
PROTOCOLS = {
    '4-7-8': {
        'name': '4-7-8 呼吸法',
        'label': '呼吸引导',
        'intro_text': '跟着我的节奏，慢慢呼吸。准备好了吗？我们开始。',
        'steps': [
            {'phase': 'inhale', 'text': '用鼻子吸气', 'duration_s': 4, 'hint': '慢慢吸...'},
            {'phase': 'hold', 'text': '屏住呼吸', 'duration_s': 7, 'hint': '轻轻屏住...'},
            {'phase': 'exhale', 'text': '用嘴巴慢慢呼气', 'duration_s': 8, 'hint': '慢慢呼出...'},
        ],
        'repeat_times': 5,
    },
    'body_scan': {
        'name': '渐进身体扫描',
        'label': '身体扫描',
        'intro_text': '把你的注意力带到身体上，从头到脚慢慢放松。',
        'areas': [
            ('头顶和额头', '感受头顶的重量，让额头放松'),
            ('眼睛和脸颊', '让眼周的肌肉松弛下来'),
            ('下巴和脖子', '松开牙关，放松颈部'),
            ('肩膀', '让肩膀下沉，卸下今天的重量'),
            ('手臂和双手', '感受手臂自然垂放的感觉'),
            ('胸腔', '注意呼吸时胸腔的起伏'),
            ('腹部', '让腹部柔软，跟随呼吸'),
            ('背部', '感受床垫支撑着背部'),
            ('大腿和膝盖', '让双腿完全放松'),
            ('小腿和双脚', '感受脚底的温度'),
        ],
        'duration_per_area_s': 15,
    },
    'breathing_light': {
        'name': '轻柔呼吸',
        'label': '轻柔呼吸',
        'intro_text': '让我们做几个轻柔的呼吸。',
        'steps': [
            {'phase': 'inhale', 'text': '轻轻吸气', 'duration_s': 4, 'hint': '慢慢来...'},
            {'phase': 'exhale', 'text': '缓缓呼气', 'duration_s': 6, 'hint': '放松呼出...'},
        ],
        'repeat_times': 8,
    },
}

# ===== 陪伴模式会话 =====
class CompanionSession:
    """一次陪伴模式会话

    用法:
        session = CompanionSession('4-7-8')
        steps = session.get_initial_steps()  # 返回前几步引导指令
        while session.is_active():
            feedback = {'movement_detected': True, 'time_elapsed': 45}
            action = session.update(feedback)
            # action 包含下一步执行的指令
    """

    def __init__(self, protocol='4-7-8', user_msg=''):
        self.protocol_name = protocol if protocol in PROTOCOLS else '4-7-8'
        self.protocol = PROTOCOLS[self.protocol_name]

        self.state = 'INIT'
        self.started_at = time.time()
        self.last_activity_at = self.started_at
        self.reset_count = 0  # 监测到体动后重置次数
        self.current_step = 0
        self.current_cycle = 0
        self.total_cycles = self.protocol.get('repeat_times', 5) if 'repeat_times' in self.protocol else 1
        self.area_index = 0
        self.total_areas = len(self.protocol.get('areas', [])) if 'areas' in self.protocol else 0

        # 安静计时器（用户连续不动X秒→开始渐弱）
        self.quiet_seconds = 0
        self.quiet_threshold = 30  # 连续30秒不动→开始渐弱
        self.relapse_quiet_threshold = 20  # relapse后只要20秒不动

        self.max_duration = 900  # 最长15分钟

        # 时长跟踪
        self.phase_start = self.started_at
        self.total_duration_s = 0

        _log.info('[Companion] Session created: protocol=%s', self.protocol_name)

    def is_active(self):
        """会话是否仍在进行"""
        elapsed = time.time() - self.started_at
        if elapsed > self.max_duration:
            return False
        if self.state == 'EXIT':
            return False
        return True

    def get_elapsed(self):
        """获取已工作秒数"""
        return time.time() - self.started_at

    def get_initial_steps(self):
        """获取前几步引导指令（前端首次加载时使用）

        Returns:
            dict: {
                'protocol': str,
                'state': str,
                'intro': str,
                'steps': [{ 'phase': str, 'text': str, 'duration_s': int, 'hint': str }],
                'total_cycles': int,
            }
        """
        steps = self.protocol.get('steps', [])
        areatype = 'areas' in self.protocol
        areas = self.protocol.get('areas', [])

        result = {
            'protocol': self.protocol_name,
            'protocol_name': self.protocol['name'],
            'label': self.protocol['label'],
            'state': 'CALMING',
            'intro': self.protocol['intro_text'],
            'steps': steps,
            'total_cycles': self.total_cycles,
            'total_areas': self.total_areas,
            'is_scan': areatype,
            'areas': [{'name': a[0], 'instruction': a[1]} for a in areas] if areatype else [],
        }
        self.state = 'CALMING'
        return result

    def update(self, feedback):
        """根据用户状态反馈更新状态机

        Args:
            feedback: dict
                - 'movement_detected': bool  # 检测到体动
                - 'time_elapsed': float       # 当前阶段已过秒数
                - 'user_cancel': bool         # 用户主动取消

        Returns:
            dict: {
                'action': str,        # continue | next_step | switch_protocol | fade_out | exit
                'state': str,         # 当前状态
                'next_text': str,     # 下一步的引导文本
                'phase': str,         # 当前阶段名
                'duration_s': int,    # 这一步持续时间
                'hint': str,          # 提示语
                'progress': float,    # 0~1
            }
        """
        if self.state == 'EXIT':
            return self._make_action('exit', '已退出', 'completed', 0, '')

        if feedback.get('user_cancel'):
            self.state = 'EXIT'
            return self._make_action('exit', '好，晚安', 'completed', 0, '')

        movement = feedback.get('movement_detected', False)
        now = time.time()
        elapsed = now - self.phase_start

        # ===== 状态转换逻辑 =====

        if self.state in ('INIT', 'CALMING'):
            if movement:
                self.last_activity_at = now
                self.quiet_seconds = 0

            # 检查是否完成当前协议循环
            steps = self.protocol.get('steps', [])
            if steps:
                step_duration = sum(s['duration_s'] for s in steps)
                cycle_duration = step_duration * self.total_cycles

                # 检查是否已完成所有循环
                total_elapsed = now - self.started_at
                if total_elapsed >= cycle_duration:
                    # 身体扫描阶段
                    if 'areas' in self.protocol:
                        self.state = 'GUIDING'
                        self.area_index = 0
                        self.phase_start = now
                        area = self.protocol['areas'][self.area_index]
                        return self._make_action('next_step', area[1], 'GUIDING',
                                                  self.protocol['duration_per_area_s'], '放松...', progress=0.5)

                    # 呼吸完成→进入安静监测
                    self.state = 'MONITORING'
                    self.phase_start = now
                    return self._make_action('switch_protocol', '现在静静地躺着，感受呼吸的自然节奏',
                                            'MONITORING', 10, '放松...', progress=0.6)

                # 计算当前步骤
                cycle_total = 0
                for cycle in range(self.total_cycles):
                    for si, s in enumerate(steps):
                        step_start = cycle_total
                        step_end = cycle_total + s['duration_s']
                        if step_start <= total_elapsed < step_end:
                            return self._make_action('continue', s['text'], 'CALMING',
                                                      max(1, int(step_end - total_elapsed)), s['hint'],
                                                      progress=total_elapsed / max(cycle_duration, 1))
                        cycle_total += s['duration_s']

        elif self.state == 'GUIDING':
            if movement:
                self.last_activity_at = now
                self.quiet_seconds = 0

            areas = self.protocol.get('areas', [])
            if not areas:
                self.state = 'MONITORING'
                self.phase_start = now
                return self._make_action('switch_protocol', '感受全身的放松', 'MONITORING', 10, '', progress=0.7)

            area_duration = self.protocol.get('duration_per_area_s', 15)
            area_idx = int((now - self.started_at) / area_duration) % self.total_areas

            if area_idx != self.area_index:
                self.area_index = area_idx
                if area_idx >= self.total_areas:
                    # 扫描完成→进入安静监测
                    self.state = 'MONITORING'
                    self.phase_start = now
                    return self._make_action('switch_protocol', '全身扫描完成，感受此刻的放松',
                                            'MONITORING', 10, '', progress=0.85)

                name, instruction = areas[area_idx]
                return self._make_action('next_step', instruction, 'GUIDING',
                                        area_duration, name, progress=0.5 + 0.3 * (area_idx / self.total_areas))

            return self._make_action('continue', areas[area_idx][1], 'GUIDING',
                                    max(1, area_duration - int(elapsed)), '')

        elif self.state == 'MONITORING':
            if movement:
                self.reset_count += 1
                self.quiet_seconds = 0
                self.last_activity_at = now

                if self.reset_count <= 2:
                    self.state = 'RELAPSE'
                    return self._make_action('return_to_guide', '没关系，我们再来一次呼吸',
                                            'RELAPSE', 4, '回到呼吸', progress=0.6)
                elif self.reset_count <= 5:
                    # 重返轻柔呼吸
                    self.state = 'CALMING'
                    self.phase_start = now
                    return self._make_action('switch_protocol', '让我们再试一次深呼吸',
                                            'CALMING', 4, '吸...', progress=0.5)
                else:
                    # 多次反复→退出（系统判断用户不适合继续）
                    self.state = 'EXIT'
                    return self._make_action('exit', '没关系，睡不着也别有压力，闭目养神也是休息。',
                                            'EXIT', 0, '', progress=1.0)

            # 安静计时
            self.quiet_seconds += feedback.get('time_elapsed', 2)
            if self.quiet_seconds >= self.quiet_threshold:
                self.state = 'RELEASE'
                return self._make_action('fade_out', '你看起来放松了，我慢慢安静下来...',
                                        'RELEASE', 15, '晚安', progress=0.95)

            return self._make_action('continue', '保持放松，什么都不要想',
                                    'MONITORING', 5, '安静...', progress=0.7 + 0.2 * min(1, self.quiet_seconds / self.quiet_threshold))

        elif self.state == 'RELAPSE':
            if not movement:
                self.quiet_seconds += feedback.get('time_elapsed', 2)
                if self.quiet_seconds >= self.relapse_quiet_threshold:
                    # 重新安静→回到监测
                    self.state = 'MONITORING'
                    self.phase_start = now
                    return self._make_action('switch_protocol', '很好，继续放松',
                                            'MONITORING', 10, '', progress=0.7)

            # 做一轮轻柔呼吸
            steps = PROTOCOLS['breathing_light']['steps']
            elapsed_r = now - self.phase_start
            step_dur = steps[0]['duration_s']
            step_idx = 0 if int(elapsed_r / step_dur) % 2 == 0 else 1
            return self._make_action('continue', steps[step_idx]['text'], 'RELAPSE',
                                    max(1, step_dur - int(elapsed_r % step_dur)), steps[step_idx]['hint'],
                                    progress=0.5)

        elif self.state == 'RELEASE':
            # 渐弱→3秒后退出
            elapsed_r = now - self.phase_start
            if elapsed_r >= 15:
                self.state = 'EXIT'
                return self._make_action('exit', '晚安。', 'EXIT', 0, '', progress=1.0)
            return self._make_action('fade_out', '...', 'RELEASE',
                                    max(1, 15 - int(elapsed_r)), '渐渐安静', progress=0.95 + 0.05 * (elapsed_r / 15))

        # 默认→退出
        self.state = 'EXIT'
        return self._make_action('exit', '', 'EXIT', 0, '', progress=1.0)

    def _make_action(self, action, text, state, duration, hint, progress=0):
        return {
            'action': action,
            'text': text,
            'state': state,
            'duration_s': duration,
            'hint': hint,
            'progress': round(progress, 3),
        }


# ===== 工厂函数（供 API 调用） =====
_active_sessions = {}  # {openid: CompanionSession}


def _report_companion_exit(openid):
    """统一上报陪伴模式结束"""
    if _HAS_BODY_CTX:
        try:
            _report_body_ev(openid, 'companion_exit')
        except Exception:
            pass


def start_companion(openid, protocol='4-7-8', message=''):
    """启动陪伴模式

    Args:
        openid: 用户ID
        protocol: 引导协议名
        message: 用户原始消息

    Returns:
        dict: 初始状态 + 引导步骤
    """
    session = CompanionSession(protocol, message)
    _active_sessions[openid] = session
    initial = session.get_initial_steps()
    initial['session_active'] = True
    _log.info('[Companion] Started for %s: %s', openid[:8], protocol)

    # 通知具身上下文
    if _HAS_BODY_CTX:
        try:
            _report_body_ev(openid, 'companion_start', {'state': 'CALMING', 'protocol': protocol})
        except Exception:
            pass

    return initial


def update_companion(openid, feedback):
    """更新陪伴模式状态

    Args:
        openid: 用户ID
        feedback: dict { movement_detected, time_elapsed, user_cancel }

    Returns:
        dict: 下一步指令
    """
    session = _active_sessions.get(openid)
    if not session:
        return {'action': 'exit', 'error': 'no_active_session', 'text': ''}

    if not session.is_active():
        del _active_sessions[openid]
        _report_companion_exit(openid)
        return {'action': 'exit', 'text': '会话已结束', 'state': 'EXIT', 'progress': 1.0}

    result = session.update(feedback)

    # 如果已退出，清理session
    if result.get('state') == 'EXIT' or result.get('action') == 'exit':
        if openid in _active_sessions:
            del _active_sessions[openid]
            _report_companion_exit(openid)
        _log.info('[Companion] Ended for %s (dur=%.0fs)', openid[:8], session.get_elapsed())

    return result


def get_companion_status(openid):
    """获取陪伴模式当前状态"""
    session = _active_sessions.get(openid)
    if not session:
        return {'active': False}
    return {
        'active': session.is_active(),
        'state': session.state,
        'elapsed_s': session.get_elapsed(),
        'protocol': session.protocol_name,
        'reset_count': session.reset_count,
    }


def stop_companion(openid):
    """主动停止陪伴"""
    if openid in _active_sessions:
        del _active_sessions[openid]
        _report_companion_exit(openid)
        _log.info('[Companion] Stopped for %s', openid[:8])
        return True
    return False


# ===== 自测 =====
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    session = CompanionSession('4-7-8')
    initial = session.get_initial_steps()
    print('Initial state:', initial.get('state'), '|', initial.get('protocol_name'))
    print('Steps:', len(initial.get('steps', [])), 'x', initial.get('total_cycles'))

    # 模拟正常流程：无体动，完成呼吸
    print('\n=== Simulating normal flow ===')
    tick = 0
    while session.is_active():
        # 每2秒发一次反馈
        fb = {'movement_detected': False, 'time_elapsed': 2, 'user_cancel': False}
        action = session.update(fb)
        tick += 1
        if tick % 5 == 0 and action['action'] != 'continue':
            print(f'  t={tick*2}s | {action["action"]:20s} | state={action["state"]:12s} | {action["text"][:40]}')
        if action['action'] == 'exit':
            print(f'  EXIT at t={tick*2}s')
            break
        if tick > 200:
            print('  WARN: timeout')
            break

    print()
    print('OK')
