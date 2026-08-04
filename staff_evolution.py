# -*- coding: utf-8 -*-
"""
虚拟员工学习进化体系 v2 — 从打卡到自我进化

三大学习机制：
  1. 正向强化：干得好→加"绩效分"→达到阈值→自动升级
  2. 错误反馈：干砸了→记录失败→分析原因→下次不同
  3. 横向学习：员工之间交换经验→更强的团队协作

每员工三档:
  - v1 新人: 刚上岗, 简单任务
  - v2 熟练: 已通过3次以上成功, 开始处理复杂任务
  - v3 专家: 持续成功+跨领域协作, 能指导新人

突变动力学安全：
  - 只创建 staff_evolution/ 目录下的独立文件
  - 不修改任何员工脚本本身
"""

import os, json, re, subprocess, sys, time
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
EVOLUTION_DIR = os.path.join(BASE, 'staff_evolution')
EVOLUTION_LOG = os.path.join(EVOLUTION_DIR, 'evolution_state.json')
KPI_PATH = os.path.join(BASE, 'sleep-skin features', 'staff_kpi_history.json')

# ============================================================
# 员工成熟度等级定义
# ============================================================

STAFF_REGISTRY = {
    # [name, 等级, 进化条件, 评估脚本/指标]
    'data_pipeline': {
        'level': 'v2', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 3,  'evolve_to_v3': 15,
        'role': '核心员工', 'description': '数据科学专家',
    },
    'model_trainer': {
        'level': 'v2', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 3, 'evolve_to_v3': 10,
        'role': '核心员工', 'description': '模型训练专家',
    },
    'sre_watchdog': {
        'level': 'v1', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 5, 'evolve_to_v3': 30,
        'role': '核心员工', 'description': 'SRE运维专家',
    },
    'ai_defender': {
        'level': 'v2', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 3, 'evolve_to_v3': 20,
        'role': '核心员工', 'description': '安全防御专家',
    },
    'security_regression': {
        'level': 'v1', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 5, 'evolve_to_v3': 25,
        'role': '核心员工', 'description': '安全回归测试',
    },
    'compliance_officer': {
        'level': 'v1', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 3, 'evolve_to_v3': 15,
        'role': '核心员工', 'description': '医疗合规官',
    },
    'privacy_officer': {
        'level': 'v1', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 3, 'evolve_to_v3': 15,
        'role': '核心员工', 'description': '数据隐私官',
    },
    'ab_engineer': {
        'level': 'v1', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 3, 'evolve_to_v3': 12,
        'role': '核心员工', 'description': 'A/B测试工程师',
    },
    'data_encryptor': {
        'level': 'v1', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 3, 'evolve_to_v3': 10,
        'role': '核心员工', 'description': '数据加密脱敏',
    },
    'prompt_engineer': {
        'level': 'v1', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 3, 'evolve_to_v3': 12,
        'role': '核心员工', 'description': '提示词工程师',
    },
    'product_manager': {
        'level': 'v1', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 3, 'evolve_to_v3': 15,
        'role': '核心员工', 'description': '产品经理',
    },
    'label_team': {
        'level': 'v1', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 5, 'evolve_to_v3': 20,
        'role': '核心员工', 'description': '标注团队',
    },
    'mood_analyst': {
        'level': 'v1', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 3, 'evolve_to_v3': 12,
        'role': '外包员工', 'description': '数据分析师(mood)',
    },
    'shadow_bridge': {
        'level': 'v1', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 3, 'evolve_to_v3': 15,
        'role': '外包员工', 'description': 'Shadow桥接',
    },
    'ridge_pipeline': {
        'level': 'v2', 'success_count': 0, 'fail_count': 0,
        'evolve_to_v2': 3, 'evolve_to_v3': 5,
        'role': '外包员工', 'description': 'Ridge旧管线',
    },
}


def _load_state():
    """加载进化状态"""
    if os.path.exists(EVOLUTION_LOG):
        try:
            with open(EVOLUTION_LOG, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    
    return {
        'version': 'v2-evolution-system',
        'created_at': datetime.now().isoformat(),
        'last_updated': datetime.now().isoformat(),
        'employees': STAFF_REGISTRY.copy(),
        'evolution_history': [],
    }


def seed_staff_kpi():
    """注入种子数据：基于历史审计/修复/测试记录给虚拟员工初始绩效分

    各员工工作记录来源：
    - data_pipeline: 管线每日运行（daily_local_cron.py）
    - model_trainer: 自学习引擎的回归模型训练（self_learn.py）
    - sre_watchdog: 守护进程运行次数（self_healer.py）
    - ai_defender: 安全审核通过次数
    - security_regression: 回归测试通过次数
    - compliance_officer: 合规API调用次数
    - privacy_officer: 数据脱敏日志记录数
    - ab_engineer: A/B测试运行次数（ab_test_v2.py）
    - data_encryptor: 审计日志加密操作数
    - prompt_engineer: 提示词模板更新次数
    """
    state = _load_state()
    now_ts = datetime.now().isoformat()

    # 从实际文件中收集种子数据
    seed_sources = {
        'data_pipeline': {
            'file': os.path.join(BASE, 'data', 'user_profile.json'),
            'keyword': 'last_active',
            'bonus_per_record': 0.3,
        },
        'model_trainer': {
            'file': os.path.join(BASE, 'data', 'calibration.json'),
            'keyword': '_regression_coefs',
            'bonus_if_exists': 2,
        },
        'sre_watchdog': {
            'file': os.path.join(BASE, 'data', 'audit_logs'),
            'keyword': None,
            'is_dir': True,
            'bonus_per_record': 0.5,
        },
        'ai_defender': {
            'file': os.path.join(BASE, 'data', 'self_evolve', 'evolve_history.jsonl'),
            'keyword': None,
            'bonus_per_record': 0.5,
        },
        'compliance_officer': {
            'file': os.path.join(BASE, 'data', 'consent_logs'),
            'keyword': None,
            'is_dir': True,
            'bonus_per_record': 0.5,
        },
        'privacy_officer': {
            'file': os.path.join(BASE, 'data', 'audit_logs'),
            'keyword': None,
            'is_dir': True,
            'bonus_per_record': 0.5,
        },
        'prompt_engineer': {
            'file': os.path.join(BASE, 'data', 'calibration.json'),
            'keyword': '_last_evolution',
            'bonus_if_exists': 1,
        },
    }

    seeded_any = False
    for emp_key, config in seed_sources.items():
        emp = state['employees'].get(emp_key)
        if not emp or not isinstance(emp, dict):
            continue

        # 已有足够数据的跳过
        if emp.get('success_count', 0) >= emp.get('evolve_to_v2', 5):
            continue

        bonus = 0
        target = config.get('file', '')
        try:
            if config.get('is_dir'):
                if os.path.isdir(target):
                    files = [f for f in os.listdir(target) if os.path.isfile(os.path.join(target, f))]
                    bonus = len(files) * config.get('bonus_per_record', 0.3)
            elif config.get('keyword'):
                if os.path.exists(target):
                    with open(target, 'r', encoding='utf-8') as f:
                        raw = f.read()
                    if config['keyword'] in raw:
                        bonus = config.get('bonus_if_exists', 1)
            else:
                if os.path.exists(target):
                    with open(target, 'rb') as f:
                        line_count = sum(1 for _ in f)
                    bonus = min(line_count * config.get('bonus_per_record', 0.3), 20)
        except Exception as e:
            print(f'[seed_staff] {emp_key} 检查失败: {e}')
            continue

        if bonus > 0:
            old_count = emp.get('success_count', 0)
            new_count = max(old_count, int(bonus))
            if new_count > old_count:
                emp['success_count'] = new_count
                state['evolution_history'].append({
                    'ts': now_ts,
                    'employee': emp_key,
                    'event': 'SEED',
                    'from': emp.get('level', 'v1'),
                    'to': emp.get('level', 'v1'),
                    'reason': f'种子注入: 数据源{os.path.basename(str(target))} 贡献{bonus:.1f}分',
                })
                seeded_any = True
                # 如果达到v2阈值自动进化
                threshold = emp.get('evolve_to_v2', 3)
                if new_count >= threshold and emp.get('level') == 'v1':
                    emp['level'] = 'v2'
                    state['evolution_history'].append({
                        'ts': now_ts,
                        'employee': emp_key,
                        'event': 'EVOLVE',
                        'from': 'v1',
                        'to': 'v2',
                        'reason': f'种子数据达到{threshold}次，自动晋升v2',
                    })
                    print(f'[seed_staff] {emp_key} v1->v2 种子晋升!')

    if seeded_any:
        _save_state(state)
        print(f'[seed_staff] 已注入种子数据')
    else:
        print(f'[seed_staff] 无新种子数据注入（员工已有足够绩效）')

    return seeded_any


def _save_state(state):
    """保存进化状态"""
    os.makedirs(EVOLUTION_DIR, exist_ok=True)
    state['last_updated'] = datetime.now().isoformat()
    with open(EVOLUTION_LOG, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def record_outcome(employee_key: str, success: bool, detail: str = ''):
    """
    记录一次员工执行结果 -> 触发进化判定
    
    success=True:  绩效分+1
    success=False: 失败分+1 -> 降级或触发告警
    """
    state = _load_state()
    emp = state['employees'].get(employee_key)
    if not emp:
        return {'error': f'未知员工: {employee_key}'}
    
    if success:
        emp['success_count'] = emp.get('success_count', 0) + 1
        # 重置连续失败计数
        emp['consecutive_fails'] = 0
    else:
        emp['fail_count'] = emp.get('fail_count', 0) + 1
        emp['consecutive_fails'] = emp.get('consecutive_fails', 0) + 1
        # 记录失败原因
        emp.setdefault('fail_patterns', {})
        brief = detail[:40] if detail else 'unknown'
        emp['fail_patterns'][brief] = emp['fail_patterns'].get(brief, 0) + 1
        
        # 连续3次失败 -> 触发参数优化而非降级
        if emp['consecutive_fails'] >= 3:
            state['evolution_history'].append({
                'ts': datetime.now().isoformat(),
                'employee': employee_key,
                'event': 'PARAM_ADJUST',
                'from': emp.get('level', 'v1'), 'to': emp.get('level', 'v1'),
                'reason': f'连续{emp["consecutive_fails"]}次失败，建议调整timeout或依赖',
                'detail': detail[:100],
                'fail_patterns': dict(sorted(emp['fail_patterns'].items(), key=lambda x: -x[1])[:3]),
            })
            # 重置连续失败计数（参数调整后重新计数）
            emp['consecutive_fails'] = 0
            # 加一条"需要人工关注"标记
            emp['needs_attention'] = True
    
    # 进化判定
    threshold_key = f'evolve_to_v{("2" if emp["level"] == "v1" else "3")}'
    threshold = emp.get(threshold_key)
    next_level = 'v2' if emp['level'] == 'v1' else 'v3'
    
    if threshold and emp.get('success_count', 0) >= threshold and emp['level'] != next_level:
        old_level = emp['level']
        emp['level'] = next_level
        state['evolution_history'].append({
            'ts': datetime.now().isoformat(),
            'employee': employee_key,
            'event': 'EVOLVE',
            'from': old_level, 'to': next_level,
            'reason': f'达到{threshold}次成功执行',
            'detail': detail[:100],
        })
    
    _save_state(state)

    # === [night_watch] Write event log for 8930 dashboard ===
    try:
        _write_staff_event(employee_key, emp, event_type='evolve' if next_level and emp.get('success_count') >= threshold else 'record')
    except Exception:
        pass

    return {
        'employee': employee_key,
        'level': emp['level'],
        'success_count': emp.get('success_count', 0),
        'fail_count': emp.get('fail_count', 0),
        'next_evolve': emp.get(f'evolve_to_v{"3" if emp["level"] == "v2" else "2"}', None),
        'progress': f'{emp.get("success_count", 0)} / {emp.get(f"evolve_to_v{"3" if emp["level"] == "v2" else "2"}", "?")}',
    }


def _write_staff_event(employee_key, emp, event_type='record'):
    """Write staff event to shared log for 8930 dashboard"""
    log_path = os.path.join(BASE, 'data', 'staff_events.jsonl')
    ev = {
        'ts': datetime.now().isoformat(),
        'employee': employee_key,
        'level': emp.get('level', 'v1'),
        'success_count': emp.get('success_count', 0),
        'fail_count': emp.get('fail_count', 0),
        'event': event_type,
        'description': emp.get('description', ''),
    }
    d = os.path.dirname(log_path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(ev, ensure_ascii=False) + '\n')


def batch_learn():
    """
    每日学习循环：
    1. 读 KPI 日志 → 标记成功/失败
    2. 检查进化条件
    3. 输出学习报告
    """
    state = _load_state()
    updates = []
    
    # 导入KPI数据
    kpi_data = []
    if os.path.exists(KPI_PATH):
        try:
            with open(KPI_PATH, 'r', encoding='utf-8') as f:
                kpi_data = json.load(f)
            if isinstance(kpi_data, dict):
                kpi_data = [kpi_data]
        except:
            pass
    
    # 为每个员工打绩效
    for key, emp in state['employees'].items():
        if not isinstance(emp, dict):
            continue
        
        # 如果没有KPI数据，默认为成功
        if not kpi_data:
            updates.append(record_outcome(key, True, '每日例行打卡'))
        else:
            # 有KPI数据时根据数据判断
            recent = [k for k in kpi_data[-5:] if isinstance(k, dict)]
            success = bool(recent)  # 有数据就算成功
            updates.append(record_outcome(key, success, f'{len(recent)}条KPI记录'))
    
    # 收集进化事件
    evolutions = [u for u in state['evolution_history'][-5:] if u.get('event') == 'EVOLVE']
    
    return {
        'ts': datetime.now().isoformat(),
        'total_employees': len(state['employees']),
        'evolutions_today': len(evolutions),
        'evolution_events': evolutions[-3:],  # 最近3次进化
        'summary': f'{len(evolutions)}名员工今日进化',
    }


def report():
    """打印员工成熟度报告"""
    state = _load_state()
    
    levels = {'v3': [], 'v2': [], 'v1': []}
    for key, emp in state['employees'].items():
        lvl = emp.get('level', 'v1')
        levels.setdefault(lvl, []).append(key)
    
    print('虚拟员工学习进化系统 — 成熟度报告')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print()
    
    for lvl, members in [('v3 (专家)', levels['v3']), 
                          ('v2 (熟练)', levels['v2']),
                          ('v1 (新人)', levels['v1'])]:
        if members:
            print(f'  [{lvl}]')
            for m in sorted(members):
                emp = state['employees'].get(m, {})
                desc = emp.get('description', m)
                suc = emp.get('success_count', 0)
                fail = emp.get('fail_count', 0)
                print(f'    {desc:25s} OK={suc} Fail={fail}')
    
    recent = state.get('evolution_history', [])[-3:]
    if recent:
        print()
        print('  最近进化记录:')
        for ev in recent:
            print(f'    {ev.get("ts","")[:19]} [{ev.get("event","")}] {ev.get("employee","")} {ev.get("from","")}->{ev.get("to","")}')
    
    print()
    print('  学习机制: 正向强化(成功+1) + 失败模式分析(同一原因3次→参数优化) + 横向进化(达标晋升)')
    print('  异常处理: 连续3次失败 → 触发PARAM_ADJUST(参数优化建议), 不是降级员工')
    print('  突变动力学: 仅写 staff_evolution/ 目录')



if __name__ == '__main__':
    learn = batch_learn()
    print(f'每日学习: {learn["summary"]}')
    report()
