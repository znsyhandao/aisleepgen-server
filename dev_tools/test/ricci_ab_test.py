#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
瑞奇流 A/B 对比测试 v3 — 独立统计 + 使用 ab_framework 做分流
"""
import sys, os, json, math, random, time
from datetime import datetime

sys.path.insert(0, 'D:\\AISleepGen_Optimized')
os.chdir('D:\\AISleepGen_Optimized')
sys.path.insert(0, os.path.join(os.getcwd(), 'dev_tools', 'test'))

from ab_framework import (
    create_experiment, start_experiment, get_assignment,
    evaluate,
)

USER_POOL = [f"test_user_{i:03d}" for i in range(100)]

def generate_mock_input(seed: int) -> dict:
    rng = random.Random(seed)
    scenario_type = rng.choice(['mild','moderate','severe','controversial'])
    base = {
        'bedtime': f'{22+rng.randint(0,4):02d}:{rng.randint(0,59):02d}',
        'wake_time': f'{6+rng.randint(0,3):02d}:{rng.randint(0,59):02d}',
        'total_duration': f'{4+rng.randint(2,6)}h{rng.randint(0,59)}m',
        '_scenario': scenario_type,
    }
    if scenario_type == 'mild':
        base.update({'sleep_latency': int(15+rng.gauss(0,5)), 'awake_times': rng.choice([0,1,1,2]), 'stress_level': int(3+rng.gauss(0,1)), 'feeling': rng.choice(['ok','normal','sleepy','good'])})
    elif scenario_type == 'moderate':
        base.update({'sleep_latency': int(30+rng.gauss(0,10)), 'awake_times': rng.choice([1,2,2,3]), 'stress_level': int(5+rng.gauss(0,1.5)), 'feeling': rng.choice(['tired','sleepy','bad','ok'])})
    elif scenario_type == 'severe':
        base.update({'sleep_latency': int(60+rng.gauss(0,15)), 'awake_times': rng.choice([3,4,5,6]), 'stress_level': int(8+rng.gauss(0,1)), 'feeling': rng.choice(['very_tired','bad','very_bad','tired'])})
    elif scenario_type == 'controversial':
        base.update({'sleep_latency': int(10+rng.gauss(0,5)), 'awake_times': rng.choice([0,1,0,0]), 'stress_level': int(rng.choice([2,9,3,8])), 'feeling': 'refreshed' if rng.random()<0.5 else 'very_tired'})
    return base

def run_world_model(data: dict, ricci_enabled: bool) -> dict:
    rng = random.Random(hash(json.dumps(data, sort_keys=True)) & 0xFFFFFFFF)
    experts = ['ClinicalPsychologist','CBT','SleepPhysician','Chronobiologist','Physicist','DataScientist','LifeScientist','RiskManager']
    sleep_latency = int(data.get('sleep_latency',15))
    awake_times = int(data.get('awake_times',0))
    stress_level = int(data.get('stress_level',5))
    feeling = data.get('feeling','ok')
    scenario = data.get('_scenario','moderate')
    feeling_map = {'very_tired':0.25,'tired':0.35,'sleepy':0.45,'ok':0.55,'normal':0.50,'good':0.70,'refreshed':0.80,'bad':0.30,'very_bad':0.15}
    base_severity = (sleep_latency/120)*0.3 + (awake_times/6)*0.3 + (stress_level/10)*0.2 + (1-feeling_map.get(feeling,0.5))*0.2
    base_severity = max(0.1, min(0.9, base_severity))
    biases = {'ClinicalPsychologist':-0.12,'CBT':-0.06,'SleepPhysician':0.0,'Chronobiologist':0.05,'Physicist':0.02,'DataScientist':0.0,'LifeScientist':0.03,'RiskManager':-0.18}
    round2 = {}
    for expert in experts:
        bias = biases.get(expert,0.0)
        if scenario == 'severe': divergence = rng.gauss(0,0.03)
        elif scenario == 'controversial': divergence = rng.gauss(0,0.12)
        else: divergence = rng.gauss(0,0.06)
        score = max(0.1, min(0.95, 0.5 - base_severity*0.4 + bias + divergence))
        confidence = rng.uniform(0.6,0.85)
        if expert == 'RiskManager': confidence = min(0.9, confidence+0.05)
        templates = {'ClinicalPsychologist':['情绪状态{}','压力水平{}','睡眠认知{}'],'CBT':['睡眠效率{}','卧床时间{}','入睡行为{}'],'SleepPhysician':['OSA风险{}','睡眠时长{}','医学指征{}'],'Chronobiologist':['昼夜节律{}','就寝偏差{}','褪黑素窗口{}'],'Physicist':['睡眠振荡{}','非线性动态{}','稳定性{}'],'DataScientist':['统计数据{}','风险叠加{}','趋势分析{}'],'LifeScientist':['生理恢复{}','糖蛋白清除{}','生长激素{}'],'RiskManager':['心血管风险{}','OSA预警{}','综合风险{}']}
        if scenario == 'severe':
            texts = ['睡眠质量差','需要干预','建议评估','风险偏高'] if rng.random()<0.6 else [t.format('偏高') for t in templates.get(expert,['{}'])]
        elif scenario == 'controversial':
            if expert in ['ClinicalPsychologist','CBT']: texts = ['用户主观感受与客观数据矛盾','可能存在认知偏差']
            elif expert in ['SleepPhysician','RiskManager']: texts = ['客观风险指标需关注','数据驱动决策优先']
            else: texts = ['建议结合主观体验综合评估','需要更多数据交叉验证']
        else:
            texts = [t.format('中等') if rng.random()<0.5 else t.format('需关注') for t in templates.get(expert,['{}'])]
        round2[expert] = {'score':round(score,3),'confidence':round(confidence,3),'findings':texts,'risk_flags':[f'{expert}风险检测'] if score<0.3 else []}
    if ricci_enabled:
        try:
            from ricci_flow import RicciFlowCurvature
            ricci = RicciFlowCurvature()
            round2, curv_map = ricci.adjust(round2)
        except: pass
    tw = sum(r.get('confidence',0.5) for r in round2.values())
    ws = sum(r.get('score',0.5)*r.get('confidence',0.5) for r in round2.values())/max(tw,0.01) if tw>0 else 0.5
    ac = sum(r.get('confidence',0) for r in round2.values())/len(experts)
    sl = [r.get('score',0.5) for r in round2.values()]
    ss = (sum((s-sum(sl)/len(sl))**2 for s in sl)/len(sl))**0.5 if sl else 0

    # 曲率数据（如果瑞奇流开启）
    curvatures = {}
    if ricci_enabled:
        for ex in round2:
            if '_ricci_curvature' in round2[ex]:
                curvatures[ex] = round2[ex]['_ricci_curvature']

    return {'weighted_score':round(ws,4),'avg_confidence':round(ac,4),'score_std':round(ss,4),'scenario':scenario,'curvatures':curvatures,'n_high_curvature':sum(1 for v in curvatures.values() if v>=0.20) if curvatures else 0,'n_low_curvature':sum(1 for v in curvatures.values() if v<=0.05) if curvatures else 0}

def t_test(a, b):
    n1,n2=len(a),len(b)
    m1,m2=sum(a)/n1,sum(b)/n2
    v1=sum((x-m1)**2 for x in a)/(n1-1) if n1>1 else 0
    v2=sum((x-m2)**2 for x in b)/(n2-1) if n2>1 else 0
    se=math.sqrt(v1/n1+v2/n2)
    if se<1e-10: return 0,1.0,False
    t=(m1-m2)/se
    p=2*(1-0.5*(1+math.erf(abs(t)/math.sqrt(2))))
    return t,p,p<0.05

def agg(arm_data):
    if not arm_data: return {'n':0,'mean_score':0,'mean_conf':0,'mean_std':0,'mean_high':0,'mean_low':0}
    scores=[r['weighted_score'] for r in arm_data]
    confs=[r['avg_confidence'] for r in arm_data]
    stds=[r['score_std'] for r in arm_data]
    highs=[r.get('n_high_curvature',0) for r in arm_data]
    lows=[r.get('n_low_curvature',0) for r in arm_data]
    return {'n':len(scores),'mean_score':round(sum(scores)/len(scores),4),'mean_conf':round(sum(confs)/len(confs),4),'mean_std':round(sum(stds)/len(stds),4),'mean_high':round(sum(highs)/len(highs),2),'mean_low':round(sum(lows)/len(lows),2),'scores':scores,'stds':stds}

def main(n_users=100, n_repeats=3):
    exp_id = create_experiment(name='ricci_flow_test', config_a={'ricci_enabled':False}, config_b={'ricci_enabled':True}, split_ratio=0.5)
    start_experiment(exp_id)

    all_r = {'A':[],'B':[]}
    sc_r = {s:{'A':[],'B':[]} for s in ['mild','moderate','severe','controversial']}

    for repeat in range(n_repeats):
        for user in USER_POOL[:n_users]:
            seed = hash(f"{user}_{repeat}_{time.time()}") & 0xFFFFFFFF
            data = generate_mock_input(seed)
            arm = get_assignment(user, exp_id)
            ricci_enabled = (arm=='B')
            res = run_world_model(data, ricci_enabled)
            all_r[arm].append(res)
            sc_r[res['scenario']][arm].append(res)

    a_s, b_s = agg(all_r['A']), agg(all_r['B'])
    t1,p1,s1 = t_test(a_s['scores'], b_s['scores'])
    t2,p2,s2 = t_test(a_s['stds'], b_s['stds'])

    # 计算关键指标
    std_imp = ((b_s['mean_std']-a_s['mean_std'])/max(a_s['mean_std'],0.001))*100 if a_s['mean_std']>0 else 0
    conf_diff = b_s['mean_conf']-a_s['mean_conf']
    high_diff = b_s['mean_high']-a_s['mean_high']
    low_diff = b_s['mean_low']-a_s['mean_low']

    report = []
    report.append('='*70)
    report.append('Riccic Flow A/B 对比测试报告')
    report.append(f'执行时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    report.append(f'模拟用户: {n_users} x {n_repeats} 轮 = {n_users*n_repeats} 次推理')
    report.append(f'实验ID: {exp_id}')
    report.append(f'对照组 (A): 无瑞奇流 (原始 world_model)')
    report.append(f'实验组 (B): 启用瑞奇流曲率感知调整')
    report.append('')

    report.append(f'{'指标':<22} {'对照组(A)':<16} {'瑞奇流(B)':<16} {'差异':<12}')
    report.append(f'{'-'*22} {'-'*16} {'-'*16} {'-'*12}')
    report.append(f'{'样本数':<22} {a_s['n']:<16} {b_s['n']:<16}')
    report.append(f'{'综合评分均值':<22} {a_s['mean_score']:<16} {b_s['mean_score']:<16} {'+{:.4f}'.format(b_s['mean_score']-a_s['mean_score']):<12}')
    report.append(f'{'平均置信度':<22} {a_s['mean_conf']:<16} {b_s['mean_conf']:<16} {'+{:.4f}'.format(conf_diff):<12}')
    report.append(f'{'专家分歧度(σ)':<22} {a_s['mean_std']:<16} {b_s['mean_std']:<16} {'+{:.4f}'.format(b_s['mean_std']-a_s['mean_std']):<12}')
    report.append(f'{'高曲率专家数':<22} {a_s['mean_high']:<16} {b_s['mean_high']:<16} {'+{:.1f}'.format(high_diff):<12}')
    report.append(f'{'低曲率专家数':<22} {a_s['mean_low']:<16} {b_s['mean_low']:<16} {'{:+}'.format(int(high_diff-low_diff)):<12}')
    report.append('')

    report.append('【统计显著性】')
    report.append(f'  综合评分差异: t={t1:.4f}, p={p1:.6f}, {'显著性!' if s1 else '不显著（无异常偏移）'}')
    report.append(f'  分歧度差异:   t={t2:.4f}, p={p2:.6f}, {'显著性!' if s2 else '不显著'}')
    report.append('')

    report.append(f'{"场景":<14} {"分组":<8} {"N":<6} {"平均分":<10} {"分歧度":<10} {"变化%":<10}')
    report.append(f'{"-"*14} {"-"*8} {"-"*6} {"-"*10} {"-"*10} {"-"*10}')
    for sc in ['mild','moderate','severe','controversial']:
        c = agg(sc_r[sc].get('A',[]))
        b = agg(sc_r[sc].get('B',[]))
        if c['n']>0:
            imp = ((b['mean_std']-c['mean_std'])/max(c['mean_std'],0.001))*100 if c['mean_std']>0 else 0
            report.append(f'{sc:<14} {"A(对照)":<8} {c["n"]:<6} {c["mean_score"]:<10} {c["mean_std"]:<10} {"-":<10}')
            report.append(f'{"":<14} {"B(瑞奇)":<8} {b["n"]:<6} {b["mean_score"]:<10} {b["mean_std"]:<10} {"{:.1f}%".format(imp):<10}')
        report.append('')

    report.append('【核心结论】')
    if std_imp > 8:
        report.append(f'  1. 专家分歧度提升 {std_imp:.1f}% -> 瑞奇流有效保留了专家多样性')
    elif std_imp > 3:
        report.append(f'  1. 专家分歧度小幅提升 {std_imp:.1f}% -> 方向正确，幅度有限')
    elif std_imp > -3:
        report.append(f'  1. 分歧度变化不明显 ({std_imp:.1f}%) -> 正常分歧场景影响有限')
    else:
        report.append(f'  1. 分歧度下降 {abs(std_imp):.1f}% -> 参数需调整')

    # 场景深层分析
    sc_analysis = []
    for sc in ['severe','controversial']:
        c = agg(sc_r[sc].get('A',[]))
        b = agg(sc_r[sc].get('B',[]))
        if c['n']>0 and b['n']>0:
            imp = ((b['mean_std']-c['mean_std'])/max(c['mean_std'],0.001))*100
            sc_analysis.append((sc, imp, c['mean_std'], b['mean_std']))

    for sc_name, imp, c_std, b_std in sc_analysis:
        label = '争议' if sc_name=='controversial' else '严重趋同'
        if imp > 3:
            report.append(f'  2. [{label}] 趋同场景分歧度 +{imp:.1f}% -> 有效防止克隆化')
        elif imp < -3:
            report.append(f'  2. [{label}] 趋同场景分歧度 {imp:.1f}% -> 需注意')
        else:
            report.append(f'  2. [{label}] 趋同场景影响不大 ({imp:+.1f}%)')

    if abs(conf_diff) < 0.02:
        report.append(f'  3. 置信度几乎无偏移 ({conf_diff:+.4f}) -> 曲率调整未造成系统性偏差')
    else:
        report.append(f'  3. 置信度偏移 ({conf_diff:+.4f}) -> 需关注')

    # 曲率分布
    ricci_data = all_r['B']
    if ricci_data:
        all_curvs = []
        for r in ricci_data:
            if r.get('curvatures'):
                all_curvs.extend(r['curvatures'].values())
        if all_curvs:
            mean_curv = round(sum(all_curvs)/len(all_curvs),4)
            high_count = sum(1 for c in all_curvs if c>=0.20)
            low_count = sum(1 for c in all_curvs if c<=0.05)
            report.append(f'  4. 曲率分布: 均值={mean_curv}, 高曲率({">=0.20"})={high_count}, 低曲率({"<=0.05"})={low_count}')

    report.append('')
    report.append('【建议】')
    if std_imp > 5:
        report.append('  1. 瑞奇流参数可用，建议 canary 测试（5%流量）上线验证真实用户')
        report.append('  2. 持续观察 CurvatureLogger 长期趋势')
    elif std_imp > 0:
        report.append('  1. 方向正确，建议调低 low_curvature_threshold(0.05->0.03)')
        report.append('  2. 或增大 curvature_penalty_factor(0.10->0.15)')
    else:
        report.append('  1. 需调整参数：增大 boost_factor 或降低 high_curvature_threshold')
        report.append('  2. 考虑 embedding 替代 Jaccard')
    report.append('='*70)

    print('\n'.join(report))

if __name__ == '__main__':
    main(100, 3)
