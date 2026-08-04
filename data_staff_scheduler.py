# -*- coding: utf-8 -*-
"""
data_staff_scheduler.py — 虚拟数据员工调度官 v3
每天自动执行12步完整管线，最后一步：员工学习进化系统评估所有员工表现。
"""
import os, sys, subprocess, json, time, traceback
from datetime import datetime

BASE = 'D:\\AISleepGen_Optimized'
LOG_DIR = os.path.join(BASE, 'logs', 'staff')
os.makedirs(LOG_DIR, exist_ok=True)

STAFF = [
    {
        'name': '📊 数据科学专家 (align_data_sources)',
        'script': os.path.join(BASE, 'scripts', 'align_data_sources.py'),
        'cwd': BASE,
        'essential': True,
        'timeout': 60,
    },
    {
        'name': '🏋️ 模型训练专家 (migrate_to_lgb)',
        'script': os.path.join(BASE, 'migrate_to_lgb.py'),
        'cwd': BASE,
        'essential': True,
        'timeout': 180,
    },
    {
        'name': '🌓 Shadow Bridge 健康检查 (shadow_model_bridge)',
        'script': os.path.join(BASE, 'shadow_model_bridge.py'),
        'cwd': BASE,
        'essential': False,  # shadow不影响主流程
        'timeout': 30,
    },
    {
        'name': '🏛️ Ridge 旧管线 (retrain_model)',
        'script': os.path.join(BASE, 'retrain_model.py'),
        'cwd': BASE,
        'essential': False,
        'timeout': 30,
    },
    {
        'name': '🛡️ 安全防御专家 (ai_defender)',
        'script': os.path.join(BASE, 'ai_defender.py'),
        'cwd': BASE,
        'essential': True,
        'timeout': 10,
    },
    {
        'name': '🛡️ 安全回归测试 (security_regression)',
        'script': os.path.join(BASE, 'security_regression_test.py'),
        'cwd': BASE,
        'essential': True,
        'timeout': 30,
    },
    {
        'name': '📊 数据分析师 (mood_from_sleep)',
        'script': os.path.join(BASE, 'mood_from_sleep.py'),
        'cwd': BASE,
        'essential': False,
        'timeout': 30,
    },
    {
        'name': '📋 用工报告 (staff_org_chart)',
        'script': os.path.join(BASE, 'staff_org_chart.py'),
        'cwd': BASE,
        'essential': False,
        'timeout': 10,
    },
    {
        'name': '🖥️ SRE运维专家 (sre_watchdog)',
        'script': os.path.join(BASE, 'sre_watchdog.py'),
        'cwd': BASE,
        'essential': True,
        'timeout': 15,
    },
    {
        'name': '🏷️ 标注团队 (label_team)',
        'script': os.path.join(BASE, 'label_team.py'),
        'cwd': BASE,
        'essential': False,
        'timeout': 30,
    },
    {
        'name': '📋 产品经理 (product_manager)',
        'script': os.path.join(BASE, 'product_manager.py'),
        'cwd': BASE,
        'essential': False,
        'timeout': 10,
    },
    {
        'name': '🧑‍⚖️ 医疗合规官 (compliance_officer)',
        'script': os.path.join(BASE, 'compliance_officer.py'),
        'cwd': BASE,
        'essential': False,
        'timeout': 15,
    },
    {
        'name': '🔐 数据隐私官 (privacy_officer)',
        'script': os.path.join(BASE, 'privacy_officer.py'),
        'cwd': BASE,
        'essential': False,
        'timeout': 15,
    },
    {
        'name': '🔬 A/B测试工程师 (ab_test_engineer)',
        'script': os.path.join(BASE, 'ab_test_engineer.py'),
        'cwd': BASE,
        'essential': False,
        'timeout': 10,
    },
    {
        'name': '🔑 数据加密脱敏 (data_encryptor)',
        'script': os.path.join(BASE, 'data_encryptor.py'),
        'cwd': BASE,
        'essential': False,
        'timeout': 15,
    },
    {
        'name': '🎯 提示词工程师 (prompt_engineer)',
        'script': os.path.join(BASE, 'prompt_engineer.py'),
        'cwd': BASE,
        'essential': False,
        'timeout': 10,
    },
]

def run_staff(member):
    """运行一名员工，返回 (ok, output)"""
    name = member['name']
    script = member['script']
    timeout = member.get('timeout', 120)
    
    if not os.path.exists(script):
        return False, f"脚本不存在: {script}"
    
    print(f"  ▶ {name} ...", end=' ', flush=True)
    t0 = time.time()
    
    try:
        r = subprocess.run(
            [sys.executable, script],
            cwd=member.get('cwd', BASE),
            capture_output=True, text=True, timeout=timeout
        )
        elapsed = time.time() - t0
        
        if r.returncode == 0:
            print(f"✅ {elapsed:.0f}s")
            return True, r.stdout[-500:] if r.stdout else ""
        else:
            print(f"❌ rc={r.returncode} ({elapsed:.0f}s)")
            return False, (r.stderr or r.stdout)[-500:]
    except subprocess.TimeoutExpired:
        print(f"⏰ 超时>{timeout}s")
        return False, f"超时 {timeout}s"
    except Exception as e:
        print(f"💥 {str(e)[:50]}")
        return False, str(e)

def main():
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  虚拟数据员工调度官 v1  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(sep)
    
    report = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'results': [],
        'summary': {'ok': 0, 'fail': 0, 'skip': 0},
    }
    
    for member in STAFF:
        print()
        ok, output = run_staff(member)
        
        status = 'ok' if ok else 'fail'
        report['results'].append({
            'name': member['name'],
            'status': status,
            'output_preview': output[:200],
        })
        report['summary'][status] = report['summary'].get(status, 0) + 1
    
    # 汇总报告
    print(f"\n{sep}")
    print("  虚拟员工考勤日报")
    print(sep)
    s = report['summary']
    print(f"  在岗: {s.get('ok', 0)} | 摸鱼: {s.get('fail', 0)} | 跳过: {s.get('skip', 0)}")
    for r in report['results']:
        icon = '✅' if r['status'] == 'ok' else '❌'
        print(f"  {icon} {r['name']}")
    print(sep)
    
    # 保存报告
    log_path = os.path.join(LOG_DIR, f"staff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  日志: {log_path}")
    
    # ===== 员工学习进化评估 =====
    print(f"\n{sep}")
    print("  [STAFF] 员工学习进化系统 — 每日评估")
    print(sep)
    try:
        import staff_evolution
        
        key_map = {
            '数据科学': 'data_pipeline',
            '模型训练': 'model_trainer',
            'SRE运维': 'sre_watchdog',
            '安全防御': 'ai_defender',
            '安全回归': 'security_regression',
            '医疗合规': 'compliance_officer',
            '数据隐私': 'privacy_officer',
            'A/B测试': 'ab_engineer',
            '数据加密': 'data_encryptor',
            '提示词': 'prompt_engineer',
            '产品经理': 'product_manager',
            '标注团队': 'label_team',
            '数据分析师': 'mood_analyst',
            'Shadow': 'shadow_bridge',
            'Ridge': 'ridge_pipeline',
        }
        
        for r in report['results']:
            for kw, key in key_map.items():
                if kw in r['name']:
                    ok = r['status'] == 'ok'
                    staff_evolution.record_outcome(key, ok, f'调度官: {r["status"]}')
                    break
        
        learn = staff_evolution.batch_learn()
        print(f"  学习结果: {learn['summary']}")
        for ev in learn.get('evolution_events', []):
            emp = ev.get('employee', '')
            print(f"    [EVOLVE] {emp}: {ev.get('from','')} -> {ev.get('to','')}")
    except Exception as eve:
        print(f"  [ERROR] 学习系统异常: {eve}")
    
    # ===== 触发事件总线的打卡完成事件 =====
    try:
        from event_bus import fire
        fire('staff.clocked', {
            'ok': report['summary'].get('ok', 0),
            'fail': report['summary'].get('fail', 0),
            'total': len(report['results']),
        })
    except Exception as ebe:
        print(f"  [ERROR] 事件总线异常: {ebe}")
    
    # ===== 反馈闭环评估 =====
    print(f"\n{sep}")
    print("  [FEEDBACK] 反馈闭环系统 — 员工上下游评价")
    print(sep)
    try:
        import feedback_loop
        fb = feedback_loop.full_evaluation()
        print(f"  健康状态: {fb['health']} (Pass={fb['pass']} Warn={fb['warning']} Fail={fb['fail']})")
        for r in fb['results']:
            v = r['verdict']
            sym = {'pass': 'OK', 'fail': 'FAIL', 'warning': 'WARN'}.get(v, '?')
            print(f"    [{sym}] {r['loop_id']}: {r.get('upstream','')} -> {r.get('downstream','')} ({r.get('metric','')}={r.get('value','?')})")
    except Exception as fbe:
        print(f"  [ERROR] 反馈闭环异常: {fbe}")
    
    return report['summary'].get('fail', 0) == 0

if __name__ == '__main__':
    all_ok = main()
    sys.exit(0 if all_ok else 1)
