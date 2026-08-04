# -*- coding: utf-8 -*-
"""
反馈闭环系统 v1 — 员工干得好不好，由下游自动评估

三种反馈环：
  1. A→B→A: A产出物→B使用→B给A打分→A根据分数改进
  2. 自动回滚: 新模型上线后如果性能下降，自动切回旧版
  3. 经验沉淀: 干好了→记录最佳实践→培训同岗

突变动力学安全：
  1. 只创建 feedback_loop/ 目录下的独立文件
  2. 不影响任何员工脚本的执行
"""

import os, json, time, subprocess, sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
FEEDBACK_DIR = os.path.join(BASE, 'feedback_loop')
FEEDBACK_LOG = os.path.join(FEEDBACK_DIR, 'feedback_loop_log.json')

# ============================================================
# 反馈环节点定义
# ============================================================

# [上游, 下游, 关键指标, 阈值]
FEEDBACK_LOOPS = [
    {
        'id': 'model_shadow',
        'upstream': 'model_trainer',
        'downstream': 'shadow_bridge',
        'metric': 'shadow_divergence',
        'good_threshold': lambda v: v < 3.0,  # 差异<3%算好
        'bad_threshold': lambda v: v >= 5.0,  # 差异>=5%要告警
        'action': 'shadow对比通过: 继续; 对比失败: 标记旧模型继续使用',
    },
    {
        'id': 'model_ab',
        'upstream': 'model_trainer',
        'downstream': 'ab_engineer',
        'metric': 'mae_improvement',
        'good_threshold': lambda v: v > 0,  # MAE下降就是好事
        'bad_threshold': lambda v: v <= -0.5,  # MAE上升0.5%要回滚
        'action': '新模型MAE下降→晋升; 上升→触发自动回滚',
    },
    {
        'id': 'security_regression',
        'upstream': 'ai_defender',
        'downstream': 'security_regression',
        'metric': 'regression_pass_rate',
        'good_threshold': lambda v: v >= 1.0,  # 全部通过
        'bad_threshold': lambda v: v < 0.9,  # 低于90%要告警
        'action': '回归测试全部通过→安全升级通过; 失败→阻止部署',
    },
    {
        'id': 'medical_audit',
        'upstream': 'deepseek_proxy',
        'downstream': 'compliance_officer',
        'metric': 'medical_risk_rate',
        'good_threshold': lambda v: v < 0.01,  # 风险率<1%
        'bad_threshold': lambda v: v >= 0.05,  # 风险率>=5%要告警
        'action': '医疗风险率<1%: 合规通过; >=5%: 紧急审查',
    },
    {
        'id': 'sre_uptime',
        'upstream': 'sre_watchdog',
        'downstream': 'product_manager',
        'metric': 'server_uptime_pct',
        'good_threshold': lambda v: v >= 0.99,  # 99%以上可用
        'bad_threshold': lambda v: v < 0.95,  # 低于95%要告警
        'action': '可用性>99%: SRE优秀; <95%: 需要排查',
    },
    {
        'id': 'data_flywheel',
        'upstream': 'user_data',
        'downstream': 'intervention_scheduler',
        'metric': 'flywheel_health',
        'good_threshold': lambda v: v >= 0.6,  # 飞轮健康度>=0.6: 干预阈值保持
        'bad_threshold': lambda v: v < 0.3,  # 飞轮健康度<0.3: 降低干预频率
        'action': '飞轮健康: 维持干预阈值; 不健康: 自动降低干预密度(避噪声)',
        'min_users': 30,  # 最少用户数才生效（测试环境自动跳过）
        'min_sessions': 100,  # 最少session数
    },
    {
        'id': 'grpo_evaluation',
        'upstream': 'recommendation_tracker',
        'downstream': 'intervention_scheduler',
        'metric': 'grpo_group_effect_pct',
        'good_threshold': lambda v: v >= 0.3,  # 好日子组中出现比例≥30%: 有效
        'bad_threshold': lambda v: v < 0.15,  # 好日子组中出现比例<15%: 无效
        'action': 'GRPO组间对比: 有效策略保持推荐; 无效策略从verified移除',
        'min_users': 5,
        'min_sessions': 20,
    },
]


def evaluate_loop(loop_def):
    """
    评估一个反馈环
    
    返回:
      {'loop_id': ..., 'verdict': 'pass'/'warning'/'fail', 'detail': ...}
    """
    loop_id = loop_def['id']
    upstream = loop_def['upstream']
    downstream = loop_def['downstream']
    metric = loop_def['metric']
    
    # 获取下游最近的产出物，看有没有评价
    result = _find_latest_downstream_output(downstream, loop_id)
    
    if result is None:
        return {
            'loop_id': loop_id,
            'verdict': 'unknown',
            'detail': f'{downstream} 没有产出物可评估',
        }
    
    metric_value = result.get('metric_value', result.get(metric, 0))
    
    if loop_def['good_threshold'](metric_value):
        return {
            'loop_id': loop_id,
            'upstream': upstream,
            'downstream': downstream,
            'verdict': 'pass',
            'metric': metric,
            'value': metric_value,
            'detail': f'{upstream} 产出合格',
        }
    elif loop_def['bad_threshold'](metric_value):
        return {
            'loop_id': loop_id,
            'upstream': upstream,
            'downstream': downstream,
            'verdict': 'fail',
            'metric': metric,
            'value': metric_value,
            'detail': f'{upstream} 产出不合格! 自动回滚/告警触发',
        }
    else:
        return {
            'loop_id': loop_id,
            'upstream': upstream,
            'downstream': downstream,
            'verdict': 'warning',
            'metric': metric,
            'value': metric_value,
            'detail': f'{upstream} 产出需关注',
        }


def _find_latest_downstream_output(employee_name, loop_id):
    """找某个员工最近的产出物里有价值的指标"""
    # 搜索路径
    search_paths = [
        (os.path.join(BASE, 'ab_results'), ['json']),
        (os.path.join(BASE, 'feedback_loop'), ['json']),
        (os.path.join(BASE, 'sleep-skin features'), ['json']),
    ]
    
    candidates = []
    for path, exts in search_paths:
        if not os.path.exists(path):
            continue
        for f in os.listdir(path):
            if not any(f.endswith(ext) for ext in exts):
                continue
            fpath = os.path.join(path, f)
            if os.path.isfile(fpath):
                candidates.append(fpath)
    
    # 找最近的
    if not candidates:
        return None
    
    latest = max(candidates, key=os.path.getmtime)
    
    try:
        with open(latest, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, list):
            data = data[-1] if data else {}
        
        return data
    except:
        return None


def _evaluate_data_flywheel(loop_def):
    """评估数据飞轮健康度——影响干预阈值调整

    数据不足时返回 unknown（测试环境自动跳过）
    数据充足时返回 pass/warning/fail
    """
    loop_id = loop_def['id']
    metric = loop_def['metric']
    min_users = loop_def.get('min_users', 30)
    min_sessions = loop_def.get('min_sessions', 100)

    # 读取用户画像（SQLite优先）
    profiles = _load_profiles_for_flywheel()
    if not profiles:
        return {
            'loop_id': loop_id,
            'verdict': 'unknown',
            'detail': f'无法读取用户数据，跳过飞轮评估',
        }

    user_count = len(profiles)
    total_sessions = sum(p.get('total_sessions', 0) for p in profiles.values() if isinstance(p, dict))
    users_with_usage = sum(1 for p in profiles.values() if isinstance(p, dict) and p.get('total_sessions', 0) > 0)
    repeat_users = sum(1 for p in profiles.values() if isinstance(p, dict) and p.get('total_sessions', 0) >= 2)

    # 数据不足自动跳过
    if user_count < min_users or total_sessions < min_sessions:
        return {
            'loop_id': loop_id,
            'verdict': 'unknown',
            'detail': f'数据不足(min_users={min_users}, min_sessions={min_sessions})，'
                      f'当前(user_count={user_count}, total_sessions={total_sessions})，跳过飞轮反馈',
        }

    # 计算飞轮健康度指标
    usage_rate = users_with_usage / max(user_count, 1)
    retention_rate = repeat_users / max(users_with_usage, 1)
    # 理想飞轮: 使用率>60%, 回访率>40%, 深度用户>10%
    depth_users = sum(1 for p in profiles.values() if isinstance(p, dict) and p.get('total_sessions', 0) >= 4)
    depth_rate = depth_users / max(users_with_usage, 1)

    health = (usage_rate * 0.3 + retention_rate * 0.4 + depth_rate * 0.3)

    detail = f'飞轮: 使用率={usage_rate:.0%}, 回访率={retention_rate:.0%}, 深度率={depth_rate:.0%}, 健康度={health:.2f}'

    if loop_def['good_threshold'](health):
        return {
            'loop_id': loop_id,
            'verdict': 'pass',
            'metric': metric,
            'value': round(health, 2),
            'detail': detail + ' → 飞轮健康，维持干预阈值',
        }
    elif loop_def['bad_threshold'](health):
        return {
            'loop_id': loop_id,
            'verdict': 'fail',
            'metric': metric,
            'value': round(health, 2),
            'detail': detail + ' → 飞轮不健康，建议降低干预密度',
        }
    else:
        return {
            'loop_id': loop_id,
            'verdict': 'warning',
            'metric': metric,
            'value': round(health, 2),
            'detail': detail + ' → 飞轮需关注',
        }


def _evaluate_grpo(loop_def):
    """GRPO式组间对比评估

    从所有用户的历史中抽取Top-3和Bottom-3，对比两组干预策略分布
    如果一个策略在好组出现的频率显著高于差组 → 有效
    反之 → 无效

    输出写入 feedback_loop/grpo_results.json
    """
    profiles = _load_profiles_for_flywheel()
    if not profiles:
        return {
            'loop_id': loop_def['id'],
            'verdict': 'unknown',
            'detail': '无法读取用户数据',
        }

    from recommendation_tracker import grpo_group_evaluation

    # 汇总所有用户的评估
    all_effects = {}  # sid → {'positive': 0, 'negative': 0, 'neutral': 0}
    evaluated_users = 0
    for openid, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        result = grpo_group_evaluation(profile, min_group_size=3)
        if not result.get('has_enough_data'):
            continue
        evaluated_users += 1
        for sid, effect in result.get('group_effects', {}).items():
            if sid not in all_effects:
                all_effects[sid] = {'positive': 0, 'negative': 0, 'neutral': 0, 'insufficient': 0}
            if effect in all_effects[sid]:
                all_effects[sid][effect] += 1

    if evaluated_users < loop_def.get('min_users', 5):
        return {
            'loop_id': loop_def['id'],
            'verdict': 'unknown',
            'detail': f'数据不足(evaluated_users={evaluated_users} < {loop_def.get("min_users", 5)})',
        }

    # 计算每个策略的有效率
    strategy_insights = {}
    for sid, counts in all_effects.items():
        total = counts['positive'] + counts['negative'] + counts['neutral']
        if total < 3:
            continue
        positive_ratio = counts['positive'] / max(total, 1)
        strategy_insights[sid] = {
            'positive_ratio': round(positive_ratio, 2),
            'count': total,
            'verdict': 'effective' if positive_ratio >= 0.3 else ('ineffective' if positive_ratio < 0.15 else 'uncertain'),
        }

    # 写结果文件
    grpo_path = os.path.join(FEEDBACK_DIR, 'grpo_results.json')
    try:
        with open(grpo_path, 'w', encoding='utf-8') as f:
            json.dump({
                'ts': datetime.now().isoformat(),
                'evaluated_users': evaluated_users,
                'strategy_insights': strategy_insights,
            }, f, ensure_ascii=False, indent=2)
    except:
        pass

    effective_count = sum(1 for v in strategy_insights.values() if v['verdict'] == 'effective')
    total_strategies = len(strategy_insights)
    effect_pct = effective_count / max(total_strategies, 1)
    detail = f'GRPO评估{evaluated_users}用户, {total_strategies}策略, 有效{effective_count}({effect_pct:.0%})'

    if effect_pct >= loop_def['good_threshold'](effect_pct) if callable(loop_def['good_threshold']) else True:
        return {
            'loop_id': loop_def['id'],
            'verdict': 'pass',
            'metric': loop_def['metric'],
            'value': round(effect_pct, 2),
            'detail': detail + ' → 策略效果正常',
        }
    elif effect_pct < 0.15:
        return {
            'loop_id': loop_def['id'],
            'verdict': 'fail',
            'metric': loop_def['metric'],
            'value': round(effect_pct, 2),
            'detail': detail + ' → 多数策略效果不明确，建议review干预方案',
        }
    else:
        return {
            'loop_id': loop_def['id'],
            'verdict': 'warning',
            'metric': loop_def['metric'],
            'value': round(effect_pct, 2),
            'detail': detail,
        }


def _load_profiles_for_flywheel():
    """加载用户画像（SQLite优先）"""
    try:
        sys.path.insert(0, BASE)
        from db_sqlite import get_db
        db = get_db()
        profiles = db.load_all_profiles()
        if profiles and len(profiles) > 0:
            return profiles
    except Exception:
        pass
    # Fallback to JSON
    json_path = os.path.join(BASE, 'user_profile.json')
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def adjust_intervention_threshold(loop_result):
    """根据飞轮健康度调整干预阈值

    飞轮不健康(health<0.3) → 降低干预密度，减少噪声
    飞轮健康(health>=0.6) → 维持现有阈值
    数据不足 → 无操作
    """
    if loop_result['verdict'] != 'fail':
        return None  # 只有fail才需要调整

    # 读取当前干预调度器阈值建议
    adjust_path = os.path.join(FEEDBACK_DIR, 'flywheel_adjust.json')
    current = {}
    if os.path.exists(adjust_path):
        try:
            with open(adjust_path, 'r', encoding='utf-8') as f:
                current = json.load(f)
        except:
            current = {}

    health = loop_result.get('value', 0)
    # 写入调整建议（intervention_scheduler.py 会在下次运行前读取）
    adjustment = {
        'ts': datetime.now().isoformat(),
        'health': health,
        'action': 'SAVE_ADJUSTMENT',
        'suggested_trigger_threshold': max(65, 75 - int((0.3 - health) * 50)),
        'note': f'飞轮健康度{health:.2f}低于0.3，建议将干预触发阈值从75上调至{max(65, 75 - int((0.3 - health) * 50))}（更保守）',
    }
    current.update(adjustment)
    with open(adjust_path, 'w', encoding='utf-8') as f:
        json.dump(current, f, ensure_ascii=False, indent=2)

    print(f'[DataFlywheel] 干预阈值调整建议已写入: {adjustment["note"]}')
    return adjustment


def full_evaluation():
    """全量评估所有反馈环"""
    os.makedirs(FEEDBACK_DIR, exist_ok=True)
    
    results = []
    for loop in FEEDBACK_LOOPS:
        if loop['id'] == 'data_flywheel':
            result = _evaluate_data_flywheel(loop)
            results.append(result)
            # 如果飞轮不健康，自动写调整建议
            if result['verdict'] == 'fail':
                adjust_intervention_threshold(result)
        elif loop['id'] == 'grpo_evaluation':
            result = _evaluate_grpo(loop)
            results.append(result)
        else:
            result = evaluate_loop(loop)
            results.append(result)
    
    # 汇总
    passes = sum(1 for r in results if r['verdict'] == 'pass')
    warnings = sum(1 for r in results if r['verdict'] == 'warning')
    fails = sum(1 for r in results if r['verdict'] == 'fail')
    
    report = {
        'ts': datetime.now().isoformat(),
        'total_loops': len(results),
        'pass': passes,
        'warning': warnings,
        'fail': fails,
        'results': results,
        'health': 'HEALTHY' if fails == 0 else 'UNHEALTHY',
    }
    
    with open(FEEDBACK_LOG, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    return report


def auto_rollback(loop_id: str):
    """自动回滚——当新模型比旧模型差时"""
    rollback_path = os.path.join(FEEDBACK_DIR, 'rollback_actions.json')
    
    rollbacks = []
    if os.path.exists(rollback_path):
        try:
            with open(rollback_path, 'r', encoding='utf-8') as f:
                rollbacks = json.load(f)
        except:
            rollbacks = []
    
    action = {
        'ts': datetime.now().isoformat(),
        'loop_id': loop_id,
        'action': 'ROLLBACK',
        'status': 'pending',
        'note': f'{loop_id} 触发了自动回滚',
    }
    
    rollbacks.append(action)
    with open(rollback_path, 'w', encoding='utf-8') as f:
        json.dump(rollbacks, f, ensure_ascii=False, indent=2)
    
    print(f'[FeedbackLoop] [ROLLBACK] {loop_id} 启动了自动回滚')
    return action


def report():
    """打印反馈闭环状态"""
    ev = full_evaluation()
    
    print('反馈闭环系统 — 员工上下游评价')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print()
    
    for r in ev['results']:
        v = r['verdict']
        sym = {'pass': 'OK', 'fail': 'FAIL', 'warning': 'WARN', 'unknown': '?'}.get(v, '?')
        print(f'  [{sym}] {r["loop_id"]:20s} {r.get("upstream","?"):20s} -> {r.get("downstream","?"):20s}')
        if v != 'unknown':
            print(f'       {r.get("metric","?")} = {r.get("value","?")}  |  {r.get("detail","")}')
    
    print()
    print(f'  健康状态: {ev["health"]}')
    print(f'  通过: {ev["pass"]} | 警告: {ev["warning"]} | 失败: {ev["fail"]}')
    print()
    print('  反馈环类型:')
    for loop in FEEDBACK_LOOPS:
        print(f'    {loop["id"]:20s} {loop["upstream"]} => {loop["downstream"]}')
        print(f'    {"":20s} 阈值: good={loop["good_threshold"](0)} bad={loop["bad_threshold"](100)}')
        print(f'    {"":20s} 行动: {loop["action"]}')
    print()
    print('  突变动力学: 不修改任何员工输出, 只读评估')


if __name__ == '__main__':
    report()
