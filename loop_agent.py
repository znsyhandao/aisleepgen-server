# -*- coding: utf-8 -*-
"""
闭环智能体 — 专气至柔，能如婴儿乎？
──────────────────────────────────────
婴儿式闭环：
  • 不主动扫描 — 只在事件驱动时才介入
  • 感知但不唠叨 — 检测到信号不一定行动，先判断用户是否在可打扰窗口
  • 需要才发声 — 连续差睡眠不是马上干预，等用户下次打开小程序时自然融入
  • 沉默是金 — 用户状态良好时，"不干预"就是最好的干预
  
适合异步启动，随服务器运行但不主动刷屏。
"""

import os, sys, json, time, datetime, threading, traceback
sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, 'data')
STATE_FILE = os.path.join(DATA_DIR, 'loop_agent_state.json')

# ============================================================
# 用户画像加载
# ============================================================
def _load_profile(openid):
    """加载用户画像"""
    path = os.path.join(DATA_DIR, 'user_profile.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            profiles = json.load(f)
        return profiles.get(openid, {})
    except:
        return {}

def _save_profile(openid, data):
    """保存用户画像片段"""
    path = os.path.join(DATA_DIR, 'user_profile.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            profiles = json.load(f)
    except:
        profiles = {}
    profiles[openid] = data
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)

# ============================================================
# Stage 1: 面部预测
# ============================================================
def predict_from_face(openid):
    """用面部照片预测睡眠质量"""
    try:
        from face_analyzer import analyze as _face_analyze
    except ImportError:
        return None
    
    # 获取最近的用户照片
    profile = _load_profile(openid)
    photos = profile.get('photos', [])
    if not photos:
        return None
    
    # 取最近的照片
    latest = photos[-1]
    img_path = latest.get('path', '')
    if not img_path or not os.path.exists(img_path):
        return None
    
    try:
        result = _face_analyze(img_path)
        return {
            'predicted_score': result.get('sleep_score'),
            'confidence': result.get('confidence', 0.5),
            'features': {
                'eye_bags': result.get('eye_bags', 0),
                'skin_tone': result.get('skin_tone_uniformity', 0),
                'dark_circles': result.get('dark_circles', 0),
            },
            'photo_time': latest.get('timestamp', ''),
        }
    except:
        return None

# ============================================================
# Stage 2: 趋势检测 → 发现"信号"
# ============================================================
def detect_signals(openid):
    """检测用户趋势信号，触发干预"""
    profile = _load_profile(openid)
    scores = profile.get('sleep_history', [])
    interventions = profile.get('interventions', [])
    
    signals = []
    
    # 信号1: 连续差睡眠
    recent = [s for s in (scores[-7:] if len(scores) > 7 else scores) if s.get('score', 5) < 4]
    if len(recent) >= 2:
        signals.append({
            'type': 'deterioration',
            'level': 'high',
            'message': f'连续{len(recent)}晚睡眠评分低于4分',
            'action': 'auto_soothe',
        })
    
    # 信号2: 单晚断崖下降
    if len(scores) >= 2:
        drop = scores[-2].get('score', 5) - scores[-1].get('score', 5)
        if drop >= 3:
            signals.append({
                'type': 'cliff_drop',
                'level': 'high',
                'message': f'睡眠评分断崖下降{drop}分',
                'action': 'compassionate_checkin',
            })
    
    # 信号3: 昨晚没用干预
    recent_interventions = [i for i in interventions if i.get('date', '') >= (datetime.date.today() - datetime.timedelta(days=1)).strftime('%Y%m%d')]
    if not recent_interventions:
        signals.append({
            'type': 'no_intervention',
            'level': 'medium',
            'message': '昨晚未使用任何放松练习',
            'action': 'suggest_intervention',
        })
    
    # 信号4: 连续好睡眠 → 降低干预
    good_days = len([s for s in (scores[-5:] if len(scores) > 5 else scores) if s.get('score', 5) >= 7])
    if good_days >= 3:
        signals.append({
            'type': 'improving',
            'level': 'low',
            'message': f'连续{good_days}晚好睡眠，建议降低干预强度',
            'action': 'reduce_intervention',
        })
    
    return signals

# ============================================================
# Stage 3: 决策 — RL或规则选择干预策略
# ============================================================
def decide_intervention(openid, signals, face_pred=None):
    """基于信号 + 面部预测选择干预策略"""
    if not signals:
        return None
    
    # 优先级排序
    high = [s for s in signals if s['level'] == 'high']
    med = [s for s in signals if s['level'] == 'medium']
    
    if high:
        # 高优先级：选择最适合当前状况的干预
        signal = high[0]
        action = signal['action']
    elif med:
        signal = med[0]
        action = signal['action']
    else:
        return None
    
    # 映射到具体干预协议
    protocol_map = {
        'auto_soothe': {
            'type': 'meditation',
            'protocol': 'body_scan',
            'duration_min': 15,
            'message': '最近睡眠似乎不太好，今晚和我一起做个身体扫描放松吧？',
            'priority': 'high',
        },
        'compassionate_checkin': {
            'type': 'narrative',
            'protocol': 'compassion_story',
            'duration_min': 10,
            'message': '今晚评分有些波动，别担心。让我讲个关于好眠的小故事。',
            'priority': 'high',
        },
        'suggest_intervention': {
            'type': 'meditation',
            'protocol': 'breathing_478',
            'duration_min': 5,
            'message': '今晚试试4-7-8呼吸法吧，只需5分钟就能帮你放松下来。',
            'priority': 'medium',
        },
        'reduce_intervention': {
            'type': 'none',
            'protocol': 'silent',
            'duration_min': 0,
            'message': '你最近睡得很棒！今晚就不打扰你了，默默守护。',
            'priority': 'low',
        },
    }
    
    return protocol_map.get(action)

# ============================================================
# Stage 4: 执行干预
# ============================================================
def execute_intervention(openid, decision):
    """执行干预并记录"""
    if not decision:
        return False
    
    profile = _load_profile(openid)
    if 'interventions' not in profile:
        profile['interventions'] = []
    
    today = datetime.date.today().strftime('%Y%m%d')
    
    # 记录干预
    profile['interventions'].append({
        'date': today,
        'time': datetime.datetime.now().strftime('%H:%M'),
        'type': decision['type'],
        'protocol': decision['protocol'],
        'duration_min': decision['duration_min'],
        'message': decision['message'],
        'completed': False,
    })
    
    # 限制历史记录
    if len(profile['interventions']) > 100:
        profile['interventions'] = profile['interventions'][-100:]
    
    _save_profile(openid, profile)
    return True

# ============================================================
# Stage 5: 学习 — 更新模型
# ============================================================
def learn_from_feedback(openid):
    """从用户反馈学习，更新校准参数"""
    profile = _load_profile(openid)
    interventions = profile.get('interventions', [])
    scores = profile.get('sleep_history', [])
    
    if len(interventions) < 3 or len(scores) < 3:
        return None
    
    # 分析哪种干预效果最好
    protocol_effectiveness = {}
    for inv in interventions:
        if not inv.get('completed'):
            continue
        protocol = inv['protocol']
        date = inv['date']
        # 找干预后次日的睡眠评分
        next_day_scores = [s for s in scores if s.get('date', '') > date]
        if next_day_scores:
            effect = next_day_scores[0].get('score', 5)
            if protocol not in protocol_effectiveness:
                protocol_effectiveness[protocol] = []
            protocol_effectiveness[protocol].append(effect)
    
    if not protocol_effectiveness:
        return None
    
    # 更新偏好
    prefs = profile.get('protocol_preferences', {})
    for protocol, effects in protocol_effectiveness.items():
        avg = sum(effects) / len(effects)
        prefs[protocol] = {'avg_score_after': round(avg, 1), 'count': len(effects)}
    
    profile['protocol_preferences'] = prefs
    profile['last_learned'] = datetime.date.today().strftime('%Y%m%d')
    _save_profile(openid, profile)
    
    return prefs

# ============================================================
# 主循环 — 对一个用户执行完整闭环
# ============================================================
def run_one_cycle(openid):
    """对一个用户执行一次完整闭环"""
    today = datetime.date.today().strftime('%Y%m%d')
    print(f'[LOOP] {openid} 闭环开始')
    
    # S1: 面部预测
    face_pred = predict_from_face(openid)
    if face_pred:
        print(f'[LOOP] {openid} 面部预测: {face_pred.get("predicted_score")}')
    
    # S2: 信号检测
    signals = detect_signals(openid)
    if not signals:
        print(f'[LOOP] {openid} 无异常信号')
        return {'status': 'idle', 'reason': 'no_signals'}
    
    print(f'[LOOP] {openid} 检测到 {len(signals)} 个信号')
    for s in signals:
        print(f'  -> [{s["level"]}] {s["message"]}')
    
    # S3: 决策
    decision = decide_intervention(openid, signals, face_pred)
    if not decision:
        return {'status': 'no_decision'}
    
    print(f'[LOOP] {openid} 决策: {decision["protocol"]}')
    
    # S4: 执行
    executed = execute_intervention(openid, decision)
    if executed:
        print(f'[LOOP] {openid} 干预已记录: {decision["message"]}')
    
    # S5: 学习（每小时检查一次）
    learn_from_feedback(openid)
    
    return {
        'status': 'intervened',
        'openid': openid,
        'date': today,
        'signals': len(signals),
        'decision': decision['protocol'],
        'message': decision['message'],
    }

# ============================================================
# 后台调度器
# ============================================================
class LoopAgent:
    """闭环智能体调度器 — 后台线程运行"""
    
    def __init__(self, interval_minutes=30):
        self.interval = interval_minutes
        self._running = False
        self._thread = None
    
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f'[LOOP] 闭环智能体已启动 (每{self.interval}分钟)')
    
    def stop(self):
        self._running = False
        print('[LOOP] 闭环智能体已停止')
    
    def _get_users(self):
        """获取活跃用户列表"""
        try:
            path = os.path.join(DATA_DIR, 'user_profile.json')
            with open(path, 'r', encoding='utf-8') as f:
                profiles = json.load(f)
            return [(oid, p) for oid, p in profiles.items() if p.get('settings', {}).get('proactive', True)]
        except:
            return []
    
    def _run(self):
        while self._running:
            try:
                users = self._get_users()
                for openid, _ in users:
                    if not self._running:
                        break
                    try:
                        run_one_cycle(openid)
                    except Exception as e:
                        print(f'[LOOP] {openid} 错误: {e}')
                    time.sleep(2)  # 用户间隔
            except Exception as e:
                print(f'[LOOP] 循环错误: {e}')
            
            # 等待下一轮
            for _ in range(self.interval * 60):
                if not self._running:
                    break
                time.sleep(1)

# ============================================================
# 快速测试
# ============================================================
if __name__ == '__main__':
    print('=' * 50)
    print('闭环智能体 自检')
    print('=' * 50)
    
    # 检测各阶段是否可用
    checks = [
        ('face_analyzer', lambda: __import__('face_analyzer', fromlist=['analyze'])),
        ('profile_storage', lambda: __import__('profile_storage')),
    ]
    
    for name, fn in checks:
        try:
            fn()
            print(f'  ✅ {name}')
        except Exception as e:
            print(f'  ⚠️  {name}: {e}')
    
    print()
    print('启动: loop_agent.start()')
    print('停止: loop_agent.stop()')
    print()
    
    # 测试信号检测（用测试用户）
    print('> 信号检测测试 (default):')
    sigs = detect_signals('default')
    if sigs:
        for s in sigs:
            print(f'  [{s["level"]}] {s["message"]} -> {s["action"]}')
    else:
        print('  无信号')
