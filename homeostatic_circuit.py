#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
homeostatic_circuit.py — AISleepGen 稳态回路 v1.0

SCAN启示第1条的实现：将系统拆分为两个平等交织的回路。

稳态回路 (Homeostatic Circuit):
  始终运行的后台守护，负责：
  1. 持续监测身体上下文（情绪趋势/睡眠节律/生理信号）
  2. 信号积累而非即时决策（把"发现"写到信号板，不直接推）
  3. 背景调节（冷却计时、时段约束、用户偏好检查）
  4. 定时扫描到期延迟推送

干预回路 (Intervention Circuit):
  chat handler / companion / push — 读取信号板做决策。
  两个回路通过 SignalBoard 共享内存通信。

核心设计原则:
  - 稳态回路不做任何用户可见的操作（不发推送、不写prompt）
  - 干预回路只读取信号板，不覆盖稳态回路的数据
  - 信号板是纯内存结构，秒级更新，不落盘
"""

import json, os, time, threading, logging
from datetime import datetime, timedelta

_ho_log = logging.getLogger('aisleepgen.homeostatic')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ==================== SignalBoard — 回路间通信 ====================

class SignalBoard:
    """两个回路之间的共享内存信号板。

    稳态回路写入信号：
      signal_board.write(user_id, 'sleep_debt', 'severe')
      signal_board.write(user_id, 'mood_trend', 'declining')
      signal_board.write(user_id, 'circadian_risk', True)

    干预回路读取信号：
      board = signal_board.read(user_id)
      if board.get('circadian_risk'): ...

    信号板自动清理：超过 TTL 的信号被清除。
    """
    def __init__(self, signal_ttl=3600):
        self._board = {}       # {openid: {signal_name: {value, timestamp}}}
        self._lock = threading.RLock()
        self._signal_ttl = signal_ttl  # 信号默认存活1小时

    def write(self, openid, name, value, ttl=None):
        """写入一个信号

        Args:
            openid: 用户ID
            name: 信号名 (e.g. 'sleep_debt', 'mood_trend')
            value: 信号值 (任意JSON可序列化类型)
            ttl: 存活秒数 (None=使用默认)
        """
        with self._lock:
            user_signals = self._board.setdefault(openid, {})
            user_signals[name] = {
                'value': value,
                'timestamp': time.time(),
                'ttl': ttl or self._signal_ttl,
            }

    def read(self, openid):
        """读取用户的所有活跃信号

        Returns:
            dict: {signal_name: value} — 所有未过期的信号
        """
        now = time.time()
        with self._lock:
            user_signals = self._board.get(openid, {})
            result = {}
            expired = []
            for name, entry in user_signals.items():
                if now - entry['timestamp'] < entry['ttl']:
                    result[name] = entry['value']
                else:
                    expired.append(name)
            # 清理过期信号
            for name in expired:
                del user_signals[name]
            return result

    def read_all_users(self):
        """读取所有用户的活跃信号

        Returns:
            dict: {openid: {signal_name: value}}
        """
        now = time.time()
        with self._lock:
            result = {}
            expired = {}
            for openid, signals in self._board.items():
                user_result = {}
                user_expired = []
                for name, entry in signals.items():
                    if now - entry['timestamp'] < entry['ttl']:
                        user_result[name] = entry['value']
                    else:
                        user_expired.append(name)
                if user_result:
                    result[openid] = user_result
                if user_expired:
                    for name in user_expired:
                        del signals[name]
            return result

    def clear_user(self, openid):
        """清除用户的所有信号"""
        with self._lock:
            self._board.pop(openid, None)

    def get_signal(self, openid, name):
        """获取单个信号的值

        Returns:
            value or None (信号不存在或已过期)
        """
        board = self.read(openid)
        return board.get(name)


# 全局信号板实例
signal_board = SignalBoard()


# ==================== 稳态回路守护 ====================

_HOMEOSTATIC_RUNNING = False
_HOMEOSTATIC_THREAD = None

HO_SCAN_INTERVAL = 180  # 3分钟扫描一次（比scheduler更频繁）
HO_SIGNAL_TTL = 7200    # 信号存活2小时（跨扫描周期）

# 信号名称常量
SIG_SLEEP_DEBT = 'sleep_debt'
SIG_MOOD_TREND = 'mood_trend'
SIG_ANXIETY_RISK = 'anxiety_risk'
SIG_CIRCADIAN_RISK = 'circadian_risk'
SIG_EMOTIONAL_EXHAUSTION = 'emotional_exhaustion'
SIG_LONG_INACTIVE = 'long_inactive'
SIG_RECOVERY_STATUS = 'recovery_status'
SIG_SUGGESTED_MODE = 'suggested_mode'
SIG_PUSH_COOLDOWN_EXPIRED = 'push_cooldown_expired'
SIG_RECOVERY_SCORE = 'recovery_score'
SIG_CIRCADIAN_PHASE = 'circadian_phase'       # v3.0: 昼夜节律相位
SIG_CIRCADIAN_DRIFT = 'circadian_drift'        # v3.0: 节律漂移
SIG_DROWSINESS = 'drowsiness'                  # v3.0: 当前犯困程度
SIG_IN_BEDTIME_WINDOW = 'in_bedtime_window'    # v3.0: 是否在就寝窗口内



def _load_hc_cooldown(default=10, openid=None):
    """从元学习读冷却时间（支持用户级覆盖）"""
    import json, os
    try:
        base = os.path.dirname(__file__)
        if openid:
            safe = openid.replace('/', '_').replace('\\', '_')
            upath = os.path.join(base, 'data', 'params', safe + '.json')
            if os.path.exists(upath):
                with open(upath, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                if 'cooldown_minutes' in d:
                    return d['cooldown_minutes']
        p = os.path.join(base, 'data', 'params.json')
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                d = json.load(f)
            return d.get('cooldown_minutes', default)
    except Exception as _e:
        _log = logging.getLogger('homeostatic_circuit')
        _log.warning('get_cooldown failed: %s', _e)
    return default


def _load_profiles():
    """加载所有用户的profiles"""
    try:
        profile_path = os.path.join(PROJECT_ROOT, 'user_profile.json')
        if os.path.exists(profile_path):
            with open(profile_path, 'r', encoding='utf-8-sig') as f:
                return json.load(f)
    except Exception as e:
        _ho_log.warning('[Homeostatic] Profile load failed: %s', e)
    return {}


def _homeostatic_scan():
    """稳态回路的一次完整扫描——只积累信号，不做任何用户可见操作"""
    profiles = _load_profiles()
    if not profiles:
        _ho_log.debug('[Homeostatic] No profiles to scan')
        return

    scanned = 0
    # 全局约束：检查是否在免打扰时段
    current_hour = datetime.now().hour
    is_quiet_hours = 23 <= current_hour or current_hour < 7  # 晚11点~早7点免打扰

    for openid, profile in profiles.items():
        try:
            _scan_single_user(openid, profile)
            # 免打扰时段：清除所有推送相关信号（让干预回路安静）
            if is_quiet_hours:
                _suppress_push_signals(openid)
            scanned += 1
        except Exception as e:
            _ho_log.warning('[Homeostatic] Scan error for %s: %s', openid[:8], e)

    _ho_log.debug('[Homeostatic] Scanned %d users (quiet_hours=%s)', scanned, is_quiet_hours)


def _suppress_push_signals(openid):
    """免打扰时段：压制所有推送相关信号"""
    with signal_board._lock:
        signals = signal_board._board.get(openid, {})
        # 标记推送相关信号为"安静中"，不删除（保留给干预回路参考）
        signal_board.write(openid, '_quiet_hours', True, ttl=1800)  # 30分钟清除


def _scan_single_user(openid, profile):
    """扫描单个用户，写入信号到信号板"""
    from body_context import _analyze_sleep_rhythm, _analyze_emotion_baseline, _assess_recovery

    # 用 body_context 的分析函数提取状态
    rhythm = _analyze_sleep_rhythm(profile)
    emotion = _analyze_emotion_baseline(profile)
    recovery = _assess_recovery({'today_survey_submitted': False}, rhythm, emotion)

    # ===== v3.0: 昼夜节律相位分析 =====
    try:
        from circadian_phase_model import get_circadian_signal
        circ_signal = get_circadian_signal(openid)
        if circ_signal:
            if circ_signal.get('drowsiness'):
                signal_board.write(openid, SIG_DROWSINESS, circ_signal['drowsiness'], ttl=HO_SIGNAL_TTL)
            if circ_signal.get('circadian_drift'):
                signal_board.write(openid, SIG_CIRCADIAN_DRIFT, circ_signal['circadian_drift'], ttl=HO_SIGNAL_TTL)
            if circ_signal.get('in_bedtime_window') is not None:
                signal_board.write(openid, SIG_IN_BEDTIME_WINDOW, circ_signal['in_bedtime_window'], ttl=HO_SIGNAL_TTL)
            signal_board.write(openid, SIG_CIRCADIAN_PHASE, circ_signal.get('parameters', {}), ttl=HO_SIGNAL_TTL)
            _ho_log.debug('[Homeostatic] Circadian phase written for %s', openid[:8])
    except ImportError:
        pass  # 可选模块
    except Exception as e:
        _ho_log.warning('[Homeostatic] Circadian scan error: %s', e)

    # ===== 写入信号 =====
    if rhythm.get('has_data'):
        if rhythm.get('sleep_debt') in ('severe', 'moderate'):
            signal_board.write(openid, SIG_SLEEP_DEBT, rhythm['sleep_debt'], ttl=HO_SIGNAL_TTL)
        if rhythm.get('circadian_risk'):
            signal_board.write(openid, SIG_CIRCADIAN_RISK, True, ttl=HO_SIGNAL_TTL)

    if emotion.get('has_data'):
        if emotion.get('mood_trend') == 'declining':
            signal_board.write(openid, SIG_MOOD_TREND, 'declining', ttl=HO_SIGNAL_TTL)
        if emotion.get('anxiety_risk'):
            signal_board.write(openid, SIG_ANXIETY_RISK, True, ttl=HO_SIGNAL_TTL)
        if emotion.get('emotional_exhaustion'):
            signal_board.write(openid, SIG_EMOTIONAL_EXHAUSTION, True, ttl=HO_SIGNAL_TTL)

    if recovery.get('status') != 'unknown':
        signal_board.write(openid, SIG_RECOVERY_STATUS, recovery['status'], ttl=HO_SIGNAL_TTL)
        signal_board.write(openid, SIG_RECOVERY_SCORE, recovery['score_estimate'], ttl=HO_SIGNAL_TTL)
        if recovery.get('suggested_mode'):
            signal_board.write(openid, SIG_SUGGESTED_MODE, recovery['suggested_mode'], ttl=HO_SIGNAL_TTL)

    # 检查不活跃
    history = profile.get('history', [])
    if history:
        last = history[-1]
        if isinstance(last, dict):
            ts = last.get('timestamp', '')
            if ts:
                try:
                    last_time = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                    days_since = (datetime.now() - last_time).days
                    if days_since >= 2:
                        signal_board.write(openid, SIG_LONG_INACTIVE, days_since, ttl=HO_SIGNAL_TTL)
                    else:
                        # 用户最近活跃，清除不活跃信号
                        signal_board.write(openid, SIG_LONG_INACTIVE, 0, ttl=HO_SIGNAL_TTL)
                except Exception:
                    pass


def _get_inactive_users_for_cooldown_check():
    """获取所有用户中不活跃时间（用于冷却检查）"""
    profiles = _load_profiles()
    result = {}
    for openid, profile in profiles.items():
        history = profile.get('history', [])
        if not history:
            result[openid] = 999
            continue
        last = history[-1]
        if isinstance(last, dict):
            ts = last.get('timestamp', '')
            if ts:
                try:
                    last_time = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                    days = (datetime.now() - last_time).days
                    result[openid] = days
                    continue
                except Exception as _e:
                    _log.warning("[homeostatic_circuit] %s", _e)
        result[openid] = 999
    return result


def _check_push_cooldowns():
    """检查推送冷却是否已过期，写入信号"""
    from scheduler_daemon import _load_push_queue

    queue = _load_push_queue()
    now = time.time()

    # 按用户分组最近推送
    user_last_push = {}
    for entry in queue:
        oid = entry.get('openid', '')
        pushed_at = entry.get('pushed_at', 0)
        if oid and pushed_at > 0:
            if oid not in user_last_push or pushed_at > user_last_push[oid]:
                user_last_push[oid] = pushed_at

    for openid, last_push in user_last_push.items():
        hours_since = (now - last_push) / 3600
        if hours_since >= 20:  # 冷却已过期
            signal_board.write(openid, SIG_PUSH_COOLDOWN_EXPIRED, True, ttl=HO_SIGNAL_TTL)


def _homeostatic_loop():
    """稳态回路主循环"""
    _ho_log.info('[Homeostatic] Circuit started (interval=%ds)', HO_SCAN_INTERVAL)
    global _HOMEOSTATIC_RUNNING
    _HOMEOSTATIC_RUNNING = True

    while _HOMEOSTATIC_RUNNING:
        try:
            _homeostatic_scan()
            _check_push_cooldowns()
        except Exception as e:
            _ho_log.warning('[Homeostatic] Loop error: %s', e)
        time.sleep(HO_SCAN_INTERVAL)

    _ho_log.info('[Homeostatic] Circuit stopped')


def start_circuit():
    """启动稳态回路守护线程"""
    global _HOMEOSTATIC_THREAD
    if _HOMEOSTATIC_THREAD and _HOMEOSTATIC_THREAD.is_alive():
        _ho_log.warning('[Homeostatic] Already running')
        return _HOMEOSTATIC_THREAD

    _HOMEOSTATIC_THREAD = threading.Thread(
        target=_homeostatic_loop, daemon=True, name='homeostatic-circuit'
    )
    _HOMEOSTATIC_THREAD.start()
    _ho_log.info('[Homeostatic] Circuit thread started')
    return _HOMEOSTATIC_THREAD


def stop_circuit():
    """停止稳态回路"""
    global _HOMEOSTATIC_RUNNING
    _HOMEOSTATIC_RUNNING = False
    _ho_log.info('[Homeostatic] Circuit stopping')


# ==================== 干预回路适配器（代替旧的 push_decision 决策入口） ====================

def get_circuit_context(openid):
    """干预回路获取稳态回路的上下文

    替代旧的 push_decision.decide_interaction() 中的 profile 读取逻辑。
    返回的是稳态回路积累的信号，而不是实时读profile。

    Returns:
        dict: {
            'signals': {name: value},       # 信号板内容
            'recovery_status': str,          # 恢复状态
            'sleep_debt': str,               # 睡眠债务
            'mood_trend': str,               # 情绪趋势
            'circadian_risk': bool,          # 昼夜节律风险
            'anxiety_risk': bool,            # 焦虑风险
            'suggested_mode': str or None,   # 建议的行动模式
            'recovery_score': int,           # 恢复评分
            'inactive_days': int,            # 不活跃天数
            'push_cooldown_ok': bool,        # 推送冷却是否允许
            'quiet_hours': bool,             # 是否在免打扰时段
        }
    """
    signals = signal_board.read(openid)

    # 检查全局免打扰
    quiet = signals.get('_quiet_hours', False) or bool(
        23 <= datetime.now().hour or datetime.now().hour < 7
    )

    return {
        'signals': signals,
        'recovery_status': signals.get(SIG_RECOVERY_STATUS),
        'sleep_debt': signals.get(SIG_SLEEP_DEBT),
        'mood_trend': signals.get(SIG_MOOD_TREND),
        'anxiety_risk': signals.get(SIG_ANXIETY_RISK, False),
        'circadian_risk': signals.get(SIG_CIRCADIAN_RISK, False),
        'emotional_exhaustion': signals.get(SIG_EMOTIONAL_EXHAUSTION, False),
        'suggested_mode': signals.get(SIG_SUGGESTED_MODE),
        'recovery_score': signals.get(SIG_RECOVERY_SCORE, 50),
        'inactive_days': signals.get(SIG_LONG_INACTIVE, 0),
        'push_cooldown_ok': signals.get(SIG_PUSH_COOLDOWN_EXPIRED, True),
        'quiet_hours': quiet,
        # v3.0 circadian signals
        'circadian_drift': signals.get(SIG_CIRCADIAN_DRIFT),
        'drowsiness': signals.get(SIG_DROWSINESS),
        'in_bedtime_window': signals.get(SIG_IN_BEDTIME_WINDOW),
    }


# ==================== 自测 ====================
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    # 测试信号板
    signal_board.write('test_user', 'sleep_debt', 'severe')
    signal_board.write('test_user', 'mood_trend', 'declining')

    board = signal_board.read('test_user')
    print('[Test] Signal board:', board)
    assert board.get('sleep_debt') == 'severe'
    assert board.get('mood_trend') == 'declining'

    # 测试回路上下文
    ctx = get_circuit_context('test_user')
    print(f'[Test] Recovery status: {ctx["recovery_status"]}')
    print(f'[Test] Sleep debt: {ctx["sleep_debt"]}')
    print(f'[Test] Mood trend: {ctx["mood_trend"]}')

    # 清理信号
    signal_board.clear_user('test_user')
    board = signal_board.read('test_user')
    assert board == {}
    print('[Test] Cleanup OK')

    print('\nAll tests PASS!')
