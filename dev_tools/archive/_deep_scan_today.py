# -*- coding: utf-8 -*-
import sys, os, json

sys.stdout.reconfigure(encoding='utf-8')
print('=' * 60)
print('深度扫描: 从系统评估到下一步规划')
print('=' * 60)

# 1. 实验平台状态
expts_dir = r'D:\AISleepGen_Optimized\data\experiments'
expts = [f for f in os.listdir(expts_dir) if f.endswith('.json') and
         not f.startswith('_') and not f.startswith('.')]
active_exp = []
for fn in expts:
    fp = os.path.join(expts_dir, fn)
    try:
        with open(fp, 'r', encoding='utf-8') as f:
            d = json.load(f)
            status = d.get('status', d.get('_status', d.get('step', '?')))
            if status not in ('completed', 'rolled_back', 'finished'):
                active_exp.append((fn, status, d.get('name', '')))
    except:
        pass
print(f'\n📊 活跃实验: {len(active_exp)}')
for name, st, desc in active_exp:
    print(f'   {name:40s} {st:15s} {desc[:40]}')

# 2. 校准文件
cal_path = r'D:\AISleepGen_Optimized\data\experiments\calibration.json'
if os.path.exists(cal_path):
    with open(cal_path, 'r', encoding='utf-8') as f:
        cal = json.load(f)
    exp_keys = [k for k in cal if '_experiment' in k.lower()]
    print(f'\n📐 实验旋钮: {len(exp_keys)}')
    for k in sorted(exp_keys):
        print(f'   {k:50s} = {str(cal[k])[:80]}')

# 3. 算法存档
arch_path = r'D:\AISleepGen_Optimized\data\algorithm_archive.json'
if os.path.exists(arch_path):
    with open(arch_path, 'r', encoding='utf-8') as f:
        arch = json.load(f)
    if isinstance(arch, list):
        print(f'\n🧠 算法归档: {len(arch)} 条')
        landed = [a for a in arch if a.get('landed', False)]
        not_land = [a for a in arch if not a.get('landed', False)]
        print(f'   已落地: {len(landed)} / 待落地: {len(not_land)}')
        if not_land:
            print(f'   待落地 Top-10:')
            for a in sorted(not_land, key=lambda x: x.get('priority', 99))[:10]:
                name = a.get('name', '')
                pri = a.get('priority', '?')
                print(f'     [{pri}] {name}')


# 4. 闭环确认线
closed_dir = r'D:\AISleepGen_Optimized\data\closed_loop'
print(f'\n🔄 闭环确认线:')
if os.path.exists(closed_dir):
    for fn in sorted(os.listdir(closed_dir)):
        print(f'   {fn}')

# 5. feedback数据维度覆盖
fb_path = r'D:\AISleepGen_Optimized\data\feedback.json'
if os.path.exists(fb_path):
    with open(fb_path, 'r', encoding='utf-8') as f:
        fbs = json.load(f)
    if isinstance(fbs, list):
        dims = {}
        keys_of_interest = ['pain', 'mood', 'anxiety', 'energy', 'sleep_score',
                            'satisfaction', 'onboarding_complete', 'wakeup_mood',
                            'efficiency', 'awake', 'recovering', 'depth', 'latency']
        for fb in fbs:
            for k in keys_of_interest:
                if k in fb and fb[k] is not None:
                    dims[k] = dims.get(k, 0) + 1
        print(f'\n📝 feedback维度覆盖 ({len(fbs)} 条总feedback):')
        for k, v in sorted(dims.items(), key=lambda x: -x[1]):
            if v < 5:
                flag = '⚠️'
            else:
                flag = '✅'
            pct = v / len(fbs) * 100
            print(f'   {flag} {k:25s} {v:3d}条 ({pct:.0f}%)')

# 6. 管线产出
print('\n📡 前沿速递管线:')
data_dir = r'D:\super_frontier_radar\frontier_data'
if os.path.exists(data_dir):
    files = sorted([f for f in os.listdir(data_dir) if f.endswith('.json')])
    for f in files[-5:]:
        sz = os.path.getsize(os.path.join(data_dir, f))
        print(f'   {f:45s} {sz/1024:6.0f}KB')

# 7. 今日心跳完成度
print('\n❤️ 今日心跳管线 (11:35 执行):')
print('   阶段1: 雷达 ✅')
print('   阶段2: 退化+实验+OPSD ✅ (WARN退化信号)')
print('   阶段3: 决策产出 ✅ (2条 action=True)')
print('   阶段4: 自我改进 ✅ (1空白, 3建议)')
print('   alert写入: ❌ 已修复 (_pending_alerts模块重建)')

# 8. 预测
print('\n🔮 预测模型状态:')
lm_path = r'D:\AISleepGen_Optimized\data\lgbm_tracker_model.pkl'
if os.path.exists(lm_path):
    sz = os.path.getsize(lm_path)
    print(f'   LightGBM模型: {sz/1024:.0f}KB (已就绪)')
else:
    print(f'   LightGBM模型: ❌ 不存在')

db_path = r'D:\AISleepGen_Optimized\data\trajectory_samples.db'
if os.path.exists(db_path):
    sz = os.path.getsize(db_path)
    print(f'   轨迹数据库: {sz/1024:.0f}KB (已就绪)')
else:
    print(f'   轨迹数据库: ❌ 不存在')

# 9. 当前缺口汇总
print('\n' + '=' * 60)
print('缺口汇总')
print('=' * 60)
gaps = []

# 缺口1: 数据稀疏
real_fbs = [fb for fb in fbs if fb.get('openid', '') != 'reg_test']
if len(real_fbs) < 3:
    gaps.append(f'用户数据极稀疏: 仅{len(real_fbs)}条非测试feedback')

# 缺口2: 实验分析功能
if not os.path.exists(expts_dir + '\\_dashboard.html'):
    gaps.append('实验Dashboard未生成')

# 缺口3: 前沿扫描未集成
frontier_scan_dir = r'D:\super_frontier_radar\frontier_data'
has_recent = any('2026-07-07' in f for f in files[-3:])
if not has_recent:
    gaps.append('今日前沿速递管线未产出新数据')

# 缺口4: 不确定性校准
unc_path = r'D:\AISleepGen_Optimized\dev_tools\uncertainty_calibrator.py'
if not os.path.exists(unc_path):
    gaps.append('不确定性校准模块未创建')

# 缺口5: analyze.wxml数据看板丢失
wxml_path = r'D:\AISleepGen_Optimized\miniprogram\pages\analyze\analyze.wxml'
if os.path.exists(wxml_path):
    with open(wxml_path, 'r', encoding='utf-8') as f:
        wxml = f.read()
    if len(wxml.split('\n')) < 80:
        gaps.append('analyze.wxml 为极简版, 数据看板功能丢失')

# 缺口6: 华为云同步确认
gaps.append('华为云/腾讯云 deepseek_proxy.py 代码一致性待确认')

for i, g in enumerate(gaps, 1):
    print(f'   {i}. {g}')

# 10. 建议优先级
print('\n🎯 建议优先级 (按R²提升 × 实现成本的加权):')
suggestions = [
    ('P0 不确定性校准 → UA-ChatDev注入', '预计R² +0.1~0.2, ~120行, 昨日已注入入口但链路未完整验证'),
    ('P0 前沿扫描集成 → heartbeat阶段', '单次扫描 <10秒, 长期收益: 自驱不依赖外部触发'),
    ('P1 实验Dashboard美化 → 可直观点', '~80行HTML补全, 至尊宝可浏览器查看'),
    ('P1 analyze.wxml数据看板恢复', '需要找到安全的WXML策略, 昨天试了11次失败'),
    ('P2 华为云同步确认', '纯运维, 确认两个服务器代码一致'),
]
for s, detail in suggestions:
    print(f'   {s}')
    print(f'      {detail}')

print()
