# -*- coding: utf-8 -*-
"""P1实验收敛: 清理0706僵尸挂起实验"""
import sys, os, json, time

sys.stdout.reconfigure(encoding='utf-8')
expts_dir = r'D:\AISleepGen_Optimized\data\experiments'
backup_file = os.path.join(expts_dir, f'_pre_cleanup_{time.strftime("%Y%m%d_%H%M%S")}.json')

# 备份当前状态
all_exps = {}
for fn in os.listdir(expts_dir):
    if not fn.endswith('.json') or fn.startswith('_'):
        continue
    fp = os.path.join(expts_dir, fn)
    try:
        with open(fp, 'r', encoding='utf-8') as f:
            all_exps[fn] = json.load(f)
    except:
        pass

with open(backup_file, 'w', encoding='utf-8') as f:
    json.dump(all_exps, f, ensure_ascii=False, indent=2)
print(f'✅ 状态备份: {backup_file}')

# 清理规则: 0706挂起实验(无数据) + jepa_fuse
to_clean = [
    # 0706 挂起实验 - 全部僵尸
    '28c139e59d29', '2b24ebf2da38', '34a80a331dec', '3956b8a96d16',
    '594ff3e2546e', '5b731cac7a41', '5c1db42025e8', '5c6eff96d2e7',
    '5e0c5f6e42bc', '697b78c054ac', '8cf5dae60303', 'ab834f4dad94',
    'acd8ce4bc3ab', 'bb4a2e81557d', 'cea35b287bd3', 'd8000110eb03',
    'e0e6f4db2894', 'f9398c1dee50', 'fea1a7c2dd51',
    # jepa_fuse 无数据
    'jepa_fuse_20260706',
]

cleaned = 0
for prefix in to_clean:
    fn = prefix + '.json'
    fp = os.path.join(expts_dir, fn)
    if not os.path.exists(fp):
        continue
    with open(fp, 'r', encoding='utf-8') as f:
        exp = json.load(f)
    old_status = exp.get('status', exp.get('_status', '?'))
    exp['status'] = 'rolled_back'
    exp['_status'] = 'rolled_back'
    exp['rolled_back_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    exp['rollback_reason'] = 'auto_cleanup: 僵尸实验, 0706挂起且无数据'
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(exp, f, ensure_ascii=False, indent=2)
    cleaned += 1
    print(f'  ✅ {fn:45s} ({old_status} → rolled_back)')

print(f'\n🎯 共清理 {cleaned} 个僵尸实验')
print(f'   剩余 running: 13 个 (0707实验)')
