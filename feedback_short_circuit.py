import sys
if hasattr(sys, "stdout") and hasattr(sys.stdout, "reconfigure"):
    pass

def _safe_print(*args, sep=' ', **kwargs):
    """GBK安全打印"""
    import sys
    text = sep.join(str(a) for a in args)
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        print(text.encode('utf-8', errors='replace').decode('gbk', errors='replace'), **kwargs)



    sys.stdout.reconfigure(encoding="utf-8")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
feedback_short_circuit.py — 反馈短路器 v1

职责：不走慢路径（LightGBM/轨迹模型），快路径响应：
1. 评分 <= 2 连续出现 N 次 → 自动降级
2. 特定维度（如pain > 3）→ 自动切换策略
3. 收敛趋势检测 → 自动调优

架构: watchdog线程 + 事件通道
运行: 心跳管线自动调用
"""

import json, os, time, threading, traceback, sys
from collections import deque

BASE = r'D:\AISleepGen_Optimized'
FB_PATH = os.path.join(BASE, 'data', 'feedback.json')
CONFIG_PATH = os.path.join(BASE, 'data', 'short_circuit_config.json')
EFFECT_PATH = os.path.join(BASE, 'data', 'short_circuit_effects.json')
LOG_PATH = os.path.join(BASE, 'logs', 'short_circuit.log')

# ─── 默认配置 ───
DEFAULT_CONFIG = {
    # 当前阈值（数据驱动会自动调整）
    'rating_low_threshold': 2,      # rating <= 此值为"差"
    'rating_consecutive': 3,         # 连续N次差→触发降级
    'pain_high_threshold': 3,        # pain > 此值→切换策略
    'pain_consecutive': 2,           # 连续2次高pain→触发
    'mood_low_threshold': 2,         # mood <= 此值→触发情绪关注
    'mood_consecutive': 2,
    'anxiety_high_threshold': 3,
    
    # 响应动作
    'on_rating_drop_action': 'stress_breathing',
    'on_pain_high_action': 'sleep_gentle',
    'on_mood_low_action': 'warm_chat',
    
    # 自动调优参数
    'auto_tune_enabled': True,
    'tune_interval_minutes': 60,     # 每60分钟调整一次阈值
    'min_samples_before_tune': 5,    # 至少5个真实样本才调
}

# ─── Logger ───
def _log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    _safe_print(f'[{ts}] {msg}')
    line = f'[{ts}] {msg}'
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
    print(line)


class FeedbackShortCircuit:
    """
    反馈短路器核心
    
    使用方式:
        fsc = FeedbackShortCircuit()
        fsc.check()  # 在心跳中调用
        fsc.get_current_state()  # 查看当前状态
    """
    
    def __init__(self):
        self.config = self._load_config()
        
        # openid → deque of recent ratings
        self._rating_buffers = {}
        # openid → deque of recent pain values
        self._pain_buffers = {}
        # openid → deque of recent mood values
        self._mood_buffers = {}
        
        # 触发器历史
        self._triggers = deque(maxlen=100)
        
        # 当前状态
        self.state = {
            'active_actions': {},
            'last_check': 0,
            'total_triggers': 0,
        }
        
        # 加载效应数据
        self.effects = self._load_effects()
        
        self._load_past_feedback()
    
    def _load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    return {**DEFAULT_CONFIG, **cfg}
            except:
                pass
        return dict(DEFAULT_CONFIG)
    
    def _save_config(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    def _load_effects(self):
        if os.path.exists(EFFECT_PATH):
            try:
                with open(EFFECT_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {'actions_taken': [], 'tuning_history': []}
    
    def _save_effects(self):
        os.makedirs(os.path.dirname(EFFECT_PATH), exist_ok=True)
        with open(EFFECT_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.effects, f, ensure_ascii=False, indent=2)
    
    def _load_past_feedback(self):
        """加载历史feedback到缓冲区（启动时一次）"""
        if not os.path.exists(FB_PATH):
            return
        try:
            with open(FB_PATH, 'r', encoding='utf-8') as f:
                fbs = json.load(f)
            if not isinstance(fbs, list):
                return
            # 按openid+时间分组，每组保留最近5条
            by_user = {}
            for fb in fbs:
                oid = fb.get('openid', 'unknown')
                if oid in ('reg_test', 'test'):
                    continue
                if oid not in by_user:
                    by_user[oid] = []
                by_user[oid].append(fb)
            
            for oid, entries in by_user.items():
                entries.sort(key=lambda x: x.get('time', ''))
                recent = entries[-5:]
                buf_ratings = deque([e.get('rating') for e in recent if e.get('rating') is not None], maxlen=5)
                buf_pain = deque([e.get('pain') for e in recent if e.get('pain') is not None], maxlen=5)
                buf_mood = deque([e.get('mood') for e in recent if e.get('mood') is not None], maxlen=5)
                if buf_ratings:
                    self._rating_buffers[oid] = buf_ratings
                if buf_pain:
                    self._pain_buffers[oid] = buf_pain
                if buf_mood:
                    self._mood_buffers[oid] = buf_mood
        except Exception as e:
            _log(f'load_past_feedback error: {e}')
    
    def _get_recent_feedback(self, limit=10):
        """获取最新的真实feedback（非test/reg_test）"""
        if not os.path.exists(FB_PATH):
            return []
        try:
            with open(FB_PATH, 'r', encoding='utf-8') as f:
                fbs = json.load(f)
            if not isinstance(fbs, list):
                return []
            real = [fb for fb in fbs if fb.get('openid', '') not in ('reg_test', 'test')]
            real.sort(key=lambda x: x.get('time', ''), reverse=True)
            return real[:limit]
        except:
            return []
    
    def _detect_rating_drop(self, oid, recent_ratings):
        """检测评分下降趋势"""
        cfg = self.config
        if len(recent_ratings) < cfg['rating_consecutive']:
            return None
        last_n = list(recent_ratings)[-cfg['rating_consecutive']:]
        # 全部低于阈值才触发
        if all(r <= cfg['rating_low_threshold'] for r in last_n):
            return {
                'type': 'rating_drop',
                'severity': 'WARN',
                'action': cfg['on_rating_drop_action'],
                'details': f'连续{cfg["rating_consecutive"]}次rating≤{cfg["rating_low_threshold"]}: {last_n}',
            }
        return None
    
    def _detect_pain_high(self, oid, recent_pain):
        """检测疼痛高"""
        cfg = self.config
        if len(recent_pain) < cfg['pain_consecutive']:
            return None
        last_n = list(recent_pain)[-cfg['pain_consecutive']:]
        if all(p > cfg['pain_high_threshold'] for p in last_n):
            return {
                'type': 'pain_high',
                'severity': 'WARN',
                'action': cfg['on_pain_high_action'],
                'details': f'连续{cfg["pain_consecutive"]}次pain>{cfg["pain_high_threshold"]}: {last_n}',
            }
        return None
    
    def _detect_mood_low(self, oid, recent_mood):
        """检测情绪低"""
        cfg = self.config
        if len(recent_mood) < cfg['mood_consecutive']:
            return None
        last_n = list(recent_mood)[-cfg['mood_consecutive']:]
        if all(m <= cfg['mood_low_threshold'] for m in last_n):
            return {
                'type': 'mood_low',
                'severity': 'INFO',
                'action': cfg['on_mood_low_action'],
                'details': f'连续{cfg["mood_consecutive"]}次mood≤{cfg["mood_low_threshold"]}: {last_n}',
            }
        return None
    
    def _auto_tune(self):
        """基于效应数据自动调整阈值"""
        if not self.config.get('auto_tune_enabled'):
            return
        
        actions = self.effects.get('actions_taken', [])
        if len(actions) < self.config.get('min_samples_before_tune', 5):
            return  # 数据不够，不调
        
        # 分析：每个action触发后，后续3条feedback的平均变化
        for action_type in ['rating_drop', 'pain_high', 'mood_low']:
            related = [a for a in actions if a.get('type') == action_type]
            if len(related) < 3:
                continue
            
            # 未使用数据链路——暂不实施，保留框架
            # 以后效应数据多了，可以自动收紧/放松阈值
            pass
        
        tune_record = {
            'ts': time.time(),
            'total_actions': len(actions),
            'note': 'auto_tune placeholder',
        }
        self.effects.setdefault('tuning_history', []).append(tune_record)
    
    def check(self):
        """
        主检测入口：加载最新feedback → 检测所有用户 → 触发事件
        
        返回: 当前触发的动作列表
        """
        triggers = []
        recent = self._get_recent_feedback(limit=20)
        
        for fb in recent:
            oid = fb.get('openid', 'unknown')
            if oid in ('reg_test', 'test'):
                continue
            
            rating = fb.get('rating')
            pain = fb.get('pain')
            mood = fb.get('mood')
            
            # 更新缓冲区
            if rating is not None:
                if oid not in self._rating_buffers:
                    self._rating_buffers[oid] = deque(maxlen=5)
                self._rating_buffers[oid].append(rating)
            
            if pain is not None:
                if oid not in self._pain_buffers:
                    self._pain_buffers[oid] = deque(maxlen=5)
                self._pain_buffers[oid].append(pain)
            
            if mood is not None:
                if oid not in self._mood_buffers:
                    self._mood_buffers[oid] = deque(maxlen=5)
                self._mood_buffers[oid].append(mood)
            
            # 检测（分别看三个维度）
            tr = self._detect_rating_drop(oid, list(self._rating_buffers.get(oid, [])))
            if tr:
                tr['openid'] = oid
                triggers.append(tr)
            
            tp = self._detect_pain_high(oid, list(self._pain_buffers.get(oid, [])))
            if tp:
                tp['openid'] = oid
                triggers.append(tp)
            
            tm = self._detect_mood_low(oid, list(self._mood_buffers.get(oid, [])))
            if tm:
                tm['openid'] = oid
                triggers.append(tm)
        
        # 去重：同一openid+type只触发一次
        seen = set()
        unique_triggers = []
        for t in triggers:
            key = (t.get('openid', ''), t.get('type', ''))
            if key not in seen:
                seen.add(key)
                unique_triggers.append(t)
        
        # 记录触发
        for t in unique_triggers:
            self._triggers.append(t)
            self.state['total_triggers'] += 1
            self.effects.setdefault('actions_taken', []).append({
                'ts': time.time(),
                'type': t['type'],
                'action': t['action'],
                'openid': t.get('openid', 'unknown'),
                'details': t.get('details', ''),
            })
            
            action_name = t['action']
            self.state['active_actions'][action_name] = {
                'triggered_at': time.time(),
                'by_openids': t.get('openid', 'unknown'),
                'details': t.get('details', ''),
            }
            
            _log(f'触发: [{t["type"]}] {t["action"]} for {t.get("openid","?")} - {t.get("details","")}')
        
        # 自动调优（定期）
        now = time.time()
        if now - self.state['last_check'] > self.config['tune_interval_minutes'] * 60:
            self._auto_tune()
            self.state['last_check'] = now
        
        self._save_effects()
        return unique_triggers
    
    def get_current_state(self):
        return {
            'active_actions': self.state['active_actions'],
            'total_triggers': self.state['total_triggers'],
            'config': self.config,
            'buffer_sizes': {
                'ratings': {k: len(v) for k, v in self._rating_buffers.items()},
                'pain': {k: len(v) for k, v in self._pain_buffers.items()},
                'mood': {k: len(v) for k, v in self._mood_buffers.items()},
            },
        }


# ═══ 独立运行入口 ═══
def run_once():
    """心跳调用：一次检测"""
    fsc = FeedbackShortCircuit()
    triggers = fsc.check()
    state = fsc.get_current_state()
    _json = json.dumps(state, ensure_ascii=False)
    _log(f'检测完成: {len(triggers)}个触发, 状态={_json[:200]}')
    return triggers


def watch(daemon=True, interval=60):
    """后台线程模式"""
    def _loop():
        _log('反馈短路器 watch 模式启动')
        while True:
            try:
                run_once()
            except Exception as e:
                _log(f'watch错误: {e}')
                traceback.print_exc()
            time.sleep(interval)
    
    t = threading.Thread(target=_loop, daemon=daemon)
    t.start()
    return t


if __name__ == '__main__':
    print('反馈短路器 自测')
    triggers = run_once()
    print(f'  触发: {len(triggers)}')
    if not triggers:
        print('  (数据不足, 无触发 — 框架就绪)')
    else:
        for t in triggers:
            print(f'  → {t["type"]}: {t["action"]}')
