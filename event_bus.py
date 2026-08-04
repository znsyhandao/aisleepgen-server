# -*- coding: utf-8 -*-
"""
事件总线 v1 — 让员工能"说话"的调度中枢

取代"每天08:00全部跑一次"的粗放调度。
改为：事件触发 → 精准唤醒相关员工。

突变动力学安全：
  1. 不修改任何员工脚本
  2. 只在事件总线上注册"监听器"
  3. 员工正常跑，事件总线在旁边记录
"""

import os, json, time, threading
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
EVENT_LOG = os.path.join(BASE, 'sleep-skin features', 'event_bus_log.json')
EVOLUTION_DIR = os.path.join(BASE, 'staff_evolution')

# ============================================================
# 事件类型定义
# ============================================================

class Event:
    DATA_UPDATED = 'data.updated'           # 数据更新了
    MODEL_TRAINED = 'model.trained'         # 模型训练完
    USER_FEEDBACK = 'user.feedback'         # 用户给了反馈
    SECURITY_ALERT = 'security.alert'       # 安全告警
    HEALTH_CHECK = 'health.check'           # 健康检查
    STAFF_CLOCKED = 'staff.clocked'         # 员工打卡完成
    ANOMALY_DETECTED = 'anomaly.detected'   # 异常数据
    AB_RESULT = 'ab.result'                # A/B测试出结果
    EVOLUTION = 'staff.evolution'           # 员工进化

# ============================================================
# 员工监听注册表
# ============================================================

# 每个员工监听什么事件，事件来了做什么
LISTENERS = {
    'data_pipeline': {
        'listens': [Event.DATA_UPDATED],
        'action': '数据对齐管线启动',
        'script': 'scripts/align_data_sources.py',
    },
    'model_trainer': {
        'listens': [Event.DATA_UPDATED],
        'action': 'LightGBM重训练',
        'script': 'migrate_to_lgb.py',
    },
    'label_team': {
        'listens': [Event.DATA_UPDATED],
        'action': '自动标注',
        'script': 'label_team.py',
    },
    'shadow_bridge': {
        'listens': [Event.MODEL_TRAINED],
        'action': 'Shadow模型对比',
        'script': 'shadow_model_bridge.py',
    },
    'ab_engineer': {
        'listens': [Event.MODEL_TRAINED],
        'action': 'A/B对比实验',
        'script': 'ab_test_engineer.py',
    },
    'product_manager': {
        'listens': [Event.STAFF_CLOCKED, Event.MODEL_TRAINED],
        'action': '更新策略报告',
        'script': 'product_manager.py',
    },
    'ai_defender': {
        'listens': [Event.SECURITY_ALERT],
        'action': '升级防御规则',
        'script': 'ai_defender.py',
    },
    'compliance_officer': {
        'listens': [Event.SECURITY_ALERT],
        'action': '合规评估',
        'script': 'compliance_officer.py',
    },
    'sre_watchdog': {
        'listens': [Event.HEALTH_CHECK],
        'action': '服务巡检',
        'script': 'sre_watchdog.py',
    },
    'mood_analyst': {
        'listens': [Event.DATA_UPDATED],
        'action': '情绪推断',
        'script': 'mood_from_sleep.py',
    },
    'evolution_system': {
        'listens': [Event.STAFF_CLOCKED],
        'action': '学习进化评估',
        'script': 'staff_evolution.py',
    },
}


def fire(event_type: str, payload: dict = None):
    """
    触发事件，唤醒所有监听这个事件的员工
    
    用法:
      fire('data.updated', {'new_records': 5, 'source': 'audio'})
    """
    if payload is None:
        payload = {}
    
    ts = datetime.now().isoformat()
    print(f'[EventBus] {event_type} triggered')
    
    # 记录事件
    log_entry = {
        'ts': ts,
        'event': event_type,
        'payload': {k: str(v)[:50] for k, v in payload.items()},
        'triggered_employees': [],
    }
    
    # 找出监听了这个事件的员工
    triggered = []
    for name, cfg in LISTENERS.items():
        if event_type in cfg.get('listens', []):
            triggered.append(name)
            log_entry['triggered_employees'].append(name)
    
    if not triggered:
        print(f'[EventBus] 无员工监听事件 {event_type}')
        _persist_log(log_entry)
        return {'event': event_type, 'triggered': 0, 'employees': []}
    
    print(f'[EventBus] 唤醒 {len(triggered)} 名员工: {", ".join(triggered)}')
    
    # 记录每个员工的触发
    staff_dir = os.path.join(EVOLUTION_DIR, 'trigger_log')
    os.makedirs(staff_dir, exist_ok=True)
    
    for name in triggered:
        record = {
            'ts': ts,
            'employee': name,
            'event': event_type,
            'payload_summary': str(payload)[:100],
        }
        log_path = os.path.join(staff_dir, f'{name}_triggers.jsonl')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    _persist_log(log_entry)
    
    return {
        'event': event_type,
        'triggered': len(triggered),
        'employees': triggered,
    }


def get_pending_tasks(employee_name: str, max_age_hours: int = 24) -> list:
    """
    查询某个员工的待办任务（基于事件触发记录）
    取代"每天跑一次"——只跑有任务的时候
    """
    staff_dir = os.path.join(EVOLUTION_DIR, 'trigger_log')
    log_path = os.path.join(staff_dir, f'{employee_name}_triggers.jsonl')
    
    if not os.path.exists(log_path):
        return []
    
    now = time.time()
    deadline = now - max_age_hours * 3600
    
    tasks = []
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                ts = record.get('ts', '')
                try:
                    record_time = datetime.fromisoformat(ts).timestamp()
                except:
                    continue
                if record_time > deadline:
                    tasks.append(record)
            except:
                continue
    
    return tasks


def status():
    """所有员工的待办状态"""
    results = []
    for name, cfg in LISTENERS.items():
        pending = get_pending_tasks(name)
        script = cfg.get('script', '')
        script_path = os.path.join(BASE, script) if script else ''
        exists = os.path.exists(script_path)
        
        results.append({
            'name': name,
            'listens': cfg.get('listens', []),
            'pending_tasks': len(pending),
            'script_exists': exists,
            'last_event': pending[-1].get('ts', 'N/A') if pending else 'N/A',
        })
    
    return results


def report():
    """打印事件总线状态"""
    results = status()
    
    print('事件总线 — 员工待办状态')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print()
    print('  员工名             | 监听事件              | 待办 | 状态')
    print('  ' + '-' * 65)
    
    for r in results:
        events = ', '.join(r['listens'])[:25]
        pending = r['pending_tasks']
        status_icon = 'OK' if r['script_exists'] else 'MISSING'
        print(f'  {r["name"]:20s} | {events:25s} | {pending:4d} | {status_icon}')
    
    print()
    print('  事件总线改变了什么:')
    print('    之前: 每天08:00全部跑一遍（不管有没有事做）')
    print('    现在: 事件触发 → 只唤醒相关的员工')
    print('    员工没活干时: 安静等待，不浪费CPU')
    print()
    print('  监听事件表:')
    print('    data.updated    → 数据科学+模型训练+标注+Shadow')
    print('    model.trained   → Shadow对比+A/B测试+产品经理')
    print('    security.alert  → 安全防御+合规官')
    print('    health.check    → SRE运维')
    print('    staff.clocked   → 产品经理+进化系统')
    print()
    print('  突变动力学: 不修改任何员工脚本，事件总线是独立的' )


def _persist_log(entry):
    """持久化事件日志"""
    log = []
    if os.path.exists(EVENT_LOG):
        try:
            with open(EVENT_LOG, 'r', encoding='utf-8') as f:
                log = json.load(f)
        except:
            log = []
    log.append(entry)
    if len(log) > 200:
        log = log[-200:]
    with open(EVENT_LOG, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    print('事件总线 — 员工触发式调度测试')
    print()
    
    # 模拟各种事件
    fire('data.updated', {'new_records': 5, 'source': 'audio'})
    print()
    fire('model.trained', {'new_mae': 2.5, 'version': 'v2'})
    print()
    fire('security.alert', {'type': 'scan_attempt', 'count': 3})
    print()
    fire('staff.clocked', {'staff': 'sre_watchdog', 'status': 'ok'})
    print()
    
    report()
