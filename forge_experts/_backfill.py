"""回填历史发现到跟踪器"""
import sys, json, glob, re, os
sys.path.insert(0, 'D:/AISleepGen_Optimized')
sys.stdout.reconfigure(encoding='utf-8')

from forge_experts.expert_tracker import report_discovery, save_track, load_track, TRACK_FILE

# 扫 forge_experts/ 下的所有 ForgeExpert_*.py 提取维度
for fp in glob.glob('D:/AISleepGen_Optimized/forge_experts/ForgeExpert_*.py'):
    base = os.path.basename(fp)
    with open(fp, encoding='utf-8') as f:
        content = f.read()
    
    # 提取关注维度
    m = re.search(r"关注维度: \[(.+?)\]", content)
    if m:
        dims = [d.strip().strip("'").strip('"') for d in m.group(1).split(',')]
        m2 = re.search(r"fitness: (\d+\.\d+)", content)
        fitness = float(m2.group(1)) if m2 else 0.5
        
        stable, key = report_discovery(dims, fitness)
        print(f'{base:30s} dims={dims} fit={fitness:.3f} stable={stable}')

# 把历史已存在的设为已部署
track = load_track()
for fp in glob.glob('D:/AISleepGen_Optimized/forge_experts/ForgeExpert_*.py'):
    base = os.path.basename(fp).replace('.py', '')
    with open(fp, encoding='utf-8') as f:
        content = f.read()
    m = re.search(r"关注维度: \[(.+?)\]", content)
    if m:
        dims = [d.strip().strip("'").strip('"') for d in m.group(1).split(',')]
        key = '+'.join(sorted(dims))
        m2 = re.search(r"fitness: (\d+\.\d+)", content)
        fitness = float(m2.group(1)) if m2 else 0.5
        if not any(d.get('key') == key for d in track['deployed']):
            track['deployed'].append({'key': key, 'name': base, 'fitness': fitness, 'time': '历史'})

save_track(track)
print(f'\n已回填 {len(track["deployed"])} 个历史专家')

# 显示
from forge_experts.expert_tracker import status
status()
