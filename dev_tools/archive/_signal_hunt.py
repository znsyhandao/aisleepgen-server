# -*- coding: utf-8 -*-
import sys, json, os
sys.stdout.reconfigure(encoding='utf-8')

db = json.load(open(r'D:\super_frontier_radar\frontier_data\scanned_papers_db.json', 'r'))
papers = db.get('scanned_papers', [])
print('=== arXiv 新论文 ===')
for p in papers:
    title = p.get('title', '?')[:100]
    summary = p.get('summary', '')[:120]
    print(f'  {title}')
    print(f'    {summary}')
    print()

# 2. 看今天战略内参
si_path = r'D:\super_frontier_radar\frontier_data\_strategic_insight_2026-07-07.json'
if os.path.exists(si_path):
    si = json.load(open(si_path, 'r', encoding='utf-8'))
    print('=== 战略内参 ===')
    for key in si:
        val = si[key]
        if isinstance(val, str):
            print(f'  {key}: {val[:200]}')
        elif isinstance(val, list):
            print(f'  {key}: [{len(val)}条]')
            for item in val[:3]:
                if isinstance(item, dict):
                    print(f'    title: {item.get("title","?")[:60]}')
        else:
            print(f'  {key}: {str(val)[:100]}')

# 3. 看决策文件
for fn in os.listdir(r'D:\super_frontier_radar\frontier_data'):
    if '_for_xiaotiantian' in fn:
        dd = json.load(open(os.path.join(r'D:\super_frontier_radar\frontier_data', fn), 'r', encoding='utf-8'))
        print(f'\n=== 决策文件 {fn} ===')
        for k in dd:
            v = dd[k]
            if isinstance(v, list):
                print(f'  {k}: [{len(v)}条]')
                for item in v[:2]:
                    if isinstance(item, dict):
                        for sk, sv in list(item.items())[:3]:
                            print(f'    {sk}: {str(sv)[:60]}')
            elif isinstance(v, str):
                print(f'  {k}: {v[:150]}')
            else:
                print(f'  {k}: {v}')
        break

# 4. 看实验平台有什么异常信号
exps_dir = r'D:\AISleepGen_Optimized\data\experiments'
cal_path = os.path.join(exps_dir, 'calibration.json')
if os.path.exists(cal_path):
    cal = json.load(open(cal_path, 'r', encoding='utf-8'))
    print('\n=== 校准参数信号 ===')
    for k, v in sorted(cal.items()):
        if '_experiment' in k.lower() or 'ab_test' in k.lower():
            print(f'  {k}: {v}')

# 5. 读今日闭环确认线
closed_dir = r'D:\AISleepGen_Optimized\data\closed_loop'
if os.path.exists(closed_dir):
    today = '2026-07-07'
    for fn in sorted(os.listdir(closed_dir)):
        if today in fn:
            print(f'\n闭环: {fn}')
            try:
                cl = json.load(open(os.path.join(closed_dir, fn), 'r', encoding='utf-8'))
                if isinstance(cl, dict):
                    for k, v in list(cl.items())[:5]:
                        print(f'  {k}: {str(v)[:80]}')
            except: pass
