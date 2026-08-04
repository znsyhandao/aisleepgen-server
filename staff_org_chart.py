# -*- coding: utf-8 -*-
"""
虚拟员工分层用工制度 v1
核心团队(essential) + 外包员工(contractor) + 外援联盟(partner)
"""
import os, json, subprocess, sys, time
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SCHEDULER_LOG = os.path.join(BASE, 'sleep-skin features', 'staff_schedule_log.json')

# ============================================================
# 核心团队 — essential, 每日打卡, 安全稳定
# ============================================================
CORE_TEAM = [
    {
        'name': '📊 数据科学专家 (align_data_sources)',
        'script': os.path.join(BASE, 'scripts', 'align_data_sources.py'),
        'pay': '月薪(股份)',
        'hours': '每日08:00',
        'timeout': 60,
    },
    {
        'name': '🏋️ 模型训练专家 (migrate_to_lgb)',
        'script': os.path.join(BASE, 'migrate_to_lgb.py'),
        'pay': '月薪(股份)',
        'hours': '每日08:00',
        'timeout': 180,
    },
    {
        'name': '🏷️ 标注团队 (label_team)',
        'script': os.path.join(BASE, 'label_team.py'),
        'pay': '月薪(股份)',
        'hours': '每日08:00（数据更新后）',
        'timeout': 30,
    },
    {
        'name': '🖥️ SRE运维专家 (sre_watchdog)',
        'script': os.path.join(BASE, 'sre_watchdog.py'),
        'pay': '月薪(股份)',
        'hours': '每日08:00 + 持续后台',
        'timeout': 15,
    },
    {
        'name': '🛡️ 安全防御专家 (ai_defender)',
        'script': os.path.join(BASE, 'ai_defender.py'),
        'pay': '月薪(股份)',
        'hours': '每日08:00',
        'timeout': 10,
    },
    {
        'name': '🧑‍⚖️ 医疗合规官 (compliance_officer)',
        'script': os.path.join(BASE, 'compliance_officer.py'),
        'pay': '月薪(股份)',
        'hours': '每日08:00',
        'timeout': 15,
    },
    {
        'name': '🔐 数据隐私官 (privacy_officer)',
        'script': os.path.join(BASE, 'privacy_officer.py'),
        'pay': '月薪(股份)',
        'hours': '每日08:00',
        'timeout': 15,
    },
    {
        'name': '🔬 A/B测试工程师 (ab_test_engineer)',
        'script': os.path.join(BASE, 'ab_test_engineer.py'),
        'pay': '月薪(股份)',
        'hours': '模型更新后',
        'timeout': 10,
    },
    {
        'name': '🔑 数据加密脱敏 (data_encryptor)',
        'script': os.path.join(BASE, 'data_encryptor.py'),
        'pay': '月薪(股份)',
        'hours': '每日08:00',
        'timeout': 15,
    },
    {
        'name': '🎯 提示词工程师 (prompt_engineer)',
        'script': os.path.join(BASE, 'prompt_engineer.py'),
        'pay': '月薪(股份)',
        'hours': '每日08:00',
        'timeout': 10,
    },
    {
        'name': '🛡️ 安全回归测试 (security_regression_test)',
        'script': os.path.join(BASE, 'security_regression_test.py'),
        'pay': '月薪(股份)',
        'hours': '每日08:00',
        'timeout': 30,
    },
    {
        'name': '📋 调度官 (data_staff_scheduler)',
        'script': os.path.join(BASE, 'data_staff_scheduler.py'),
        'pay': '月薪(股份)',
        'hours': '每日08:00',
        'timeout': 300,
    },
]

# ============================================================
# 外包员工 — contract, 按件计费, 有产出才跑
# ============================================================
CONTRACTOR_TEAM = [
    {
        'name': '📈 数据分析师 (mood_from_sleep)',
        'script': os.path.join(BASE, 'mood_from_sleep.py'),
        'pay': '按日计费',
        'trigger': '每天早上的数据分析',
        'timeout': 30,
    },
    {
        'name': '🌓 Shadow Bridge (shadow_model_bridge)',
        'script': os.path.join(BASE, 'shadow_model_bridge.py'),
        'pay': '按日计费',
        'trigger': '面部分析完成后',
        'timeout': 15,
    },
    {
        'name': '🏛️ Ridge旧管线 (retrain_model)',
        'script': os.path.join(BASE, 'retrain_model.py'),
        'pay': '按次计费',
        'trigger': '数据更新后',
        'timeout': 30,
    },
]

# ============================================================
# 外援联盟 — partner, 按需调用, 通过LLM/API
# ============================================================
PARTNER_TEAM = [
    {
        'name': '🔮 前沿速递联盟 (daily_frontier + ai_reader)',
        'location': 'D:/super_frontier_radar',
        'pay': '数据共享协议',
        'trigger': '每日06:00 cron',
        'service': '论文抓取与AI解读',
    },
    {
        'name': '🧠 DeepSeek 推理引擎 (外部LLM)',
        'location': 'deepseek_proxy.py (接口)',
        'pay': 'API调用费',
        'trigger': '用户聊天/分析请求',
        'service': '对话生成、数据分析、推理',
    },
    {
        'name': '🦅 WeChat 生态 (微信小程序)',
        'location': '微信开发者工具',
        'pay': '微信审核服务',
        'trigger': '用户打开小程序',
        'service': '用户界面、推送、静默登录',
    },
    {
        'name': '🩺 expert_board 休眠专家 (13人委员会)',
        'location': 'expert_board.json',
        'pay': '待定（阻塞等待）',
        'trigger': '条件触发',
        'service': '战略规划、质量保证、市场分析',
    },
    {
        'name': '🎧 客服外援 (customer_service)',
        'location': 'expert_board.json',
        'pay': '按反馈量计费',
        'trigger': '用户反馈>10条',
        'service': '自动回复、投诉分类',
    },
]

# 储备役（已实现但暂时无用）
RESERVE_POOL = [
    {
        'name': '🔬 ClawHub社区 (clawhub_toolkit)',
        'location': 'D:/OpenClaw_Unified_Tools/ClawHub_Compliance',
        'pay': '开源社区贡献',
        'trigger': '发布ClawHub插件时启用',
        'service': '技能发布合规审核',
    },
]


def run_contractor(worker):
    """按件计费地跑一个外包员工"""
    name = worker['name']
    script = worker.get('script', '')
    if not script or not os.path.exists(script):
        return {'name': name, 'status': 'skipped', 'reason': '脚本不存在'}
    
    try:
        t0 = time.time()
        r = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=worker['timeout'],
            cwd=BASE, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        )
        elapsed = time.time() - t0
        ok = r.returncode == 0
        return {
            'name': name,
            'status': 'ok' if ok else 'fail',
            'returncode': r.returncode,
            'elapsed': f'{elapsed:.1f}s',
            'stdout': r.stdout[-300:] if r.stdout else '',
            'stderr': r.stderr[-200:] if r.stderr else '',
        }
    except subprocess.TimeoutExpired:
        return {'name': name, 'status': 'timeout', 'reason': f'超过{worker["timeout"]}s'}
    except Exception as e:
        return {'name': name, 'status': 'error', 'reason': str(e)[:100]}


def hire_partner(partner_name):
    """按需调用外援，返回可用状态"""
    for p in PARTNER_TEAM:
        if p['name'] == partner_name:
            location = p['location']
            exists = os.path.exists(location) if not location.startswith('deepseek') and not location.startswith('微信') else True
            return {
                'name': p['name'],
                'status': 'available' if exists else 'unavailable',
                'service': p['service'],
                'trigger': p['trigger'],
                'pay': p['pay'],
            }
    return {'name': partner_name, 'status': 'unknown'}


def report():
    """生成用工报告"""
    now = datetime.now().isoformat()
    
    # 核心团队报告
    core_report = [{'name': w['name'], 'role': '核心', 'pay': w['pay'], 'shift': w['hours']} for w in CORE_TEAM]
    
    # 外包团队报告
    contractor_report = [{'name': w['name'], 'role': '外包', 'pay': w['pay'], 'trigger': w['trigger']} for w in CONTRACTOR_TEAM]
    
    # 外援报告
    partner_report = [hire_partner(p['name']) for p in PARTNER_TEAM]
    
    total = len(core_report) + len(contractor_report) + len(partner_report)
    
    return {
        'ts': now,
        'total_staff': total,
        'core_team': {'count': len(core_report), 'members': core_report},
        'contractors': {'count': len(contractor_report), 'members': contractor_report},
        'partners': {'count': len(partner_report), 'members': partner_report},
        'cost_model': {
            'core': '股份(固定月薪)',
            'contractor': '按件计费',
            'partner': 'API调用/数据共享/开源贡献',
        },
    }


if __name__ == '__main__':
    print('=' * 60)
    print(f'  虚拟员工用工制度报告  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('=' * 60)
    
    r = report()
    print(f'\n  全体员工: {r["total_staff"]} 名')
    print(f'  {"─" * 40}')
    
    print(f'\n  【核心团队】{r["core_team"]["count"]}名 — 月薪股份，每日打卡')
    for m in r['core_team']['members']:
        print(f'    {m["name"]}')
    
    print(f'\n  【外包员工】{r["contractors"]["count"]}名 — 按件计费')
    for m in r['contractors']['members']:
        print(f'    {m["name"]}  ({m["trigger"]})')
    
    print(f'\n  【外援联盟】{r["partners"]["count"]}名 — 按需调用')
    for m in r['partners']['members']:
        status = '✅' if m['status'] == 'available' else '⚠️'
        print(f'    {status} {m["name"]:30s} {m["service"]}')
    
    print(f'\n  【储备役】{len(RESERVE_POOL)}名 — 代码就绪，触发时激活')
    for m in RESERVE_POOL:
        print(f'    {m["name"]:30s} 触发: {m["trigger"]}')
    
    print()
    print(f'  💰 用工成本模型:')
    print(f'    - 核心团队: {"股份(固定月薪)"}')
    print(f'    - 外包员工: {"按件计费"}')
    print(f'    - 外援联盟: {"API调用/数据共享/开源贡献"}')
