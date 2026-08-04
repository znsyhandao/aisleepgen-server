"""熔炉新专家生成管线 v3 — 稳定跟踪 + 条件部署"""
import sys, os, json, time, glob
sys.path.insert(0, 'D:/AISleepGen_Optimized')
sys.stdout.reconfigure(encoding='utf-8')

DEPLOY_DIR = 'D:/AISleepGen_Optimized/forge_experts'
TRACK_FILE = os.path.join(DEPLOY_DIR, '.discovery_track.json')

def load_track():
    try:
        with open(TRACK_FILE) as f:
            return json.load(f)
    except:
        return {'stability': {}, 'stable': [], 'deployed': []}

def save_track(track):
    os.makedirs(DEPLOY_DIR, exist_ok=True)
    with open(TRACK_FILE, 'w') as f:
        json.dump(track, f, indent=2)

def report_discovery(dimensions: list, fitness: float):
    """报告一次新发现，不急着生成专家"""
    track = load_track()
    key = tuple(sorted(dimensions))
    key_str = '+'.join(sorted(dimensions))
    
    if key_str not in track['stability']:
        track['stability'][key_str] = {
            'count': 0, 'fitnesses': [], 'first_seen': time.strftime('%H:%M:%S'),
        }
    
    entry = track['stability'][key_str]
    entry['count'] += 1
    entry['fitnesses'].append(fitness)
    entry['last_seen'] = time.strftime('%H:%M:%S')
    
    # 稳定判定：出现3次以上
    stable_count = 3
    if entry['count'] >= stable_count and key_str not in track['stable']:
        track['stable'].append(key_str)
        entry['stabilized_at'] = time.strftime('%H:%M:%S')
        print(f'  🔒 组合稳定! {key_str} ({entry["count"]}次)')
    
    save_track(track)
    
    is_stable = entry['count'] >= stable_count
    already_deployed = any(key_str == d.get('key') for d in track['deployed'])
    should_deploy = is_stable and not already_deployed
    
    return should_deploy, key_str

def generate_if_stable(genome, fitness):
    """只在组合稳定时才生成新专家"""
    dims = genome.genes['dimensions']
    should_deploy, key = report_discovery(dims, fitness)
    
    if should_deploy:
        code = genome.to_expert_code(fitness)
        name_parts = ''.join(d[0].upper() for d in dims)
        name = f'ForgeExpert_{name_parts}'
        
        fp = os.path.join(DEPLOY_DIR, f'{name}.py')
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(f'# -*- coding: utf-8 -*-\n# 熔炉v3 稳定部署 — {time.strftime("%Y-%m-%d %H:%M:%S")}\n# dims={dims} fitness={fitness:.3f}\n{code}\n')
        
        track = load_track()
        track['deployed'].append({'key': key, 'name': name, 'fitness': fitness, 'time': time.strftime('%H:%M:%S')})
        save_track(track)
        
        print(f'  ✅ 稳定部署: {name} ({key}) fitness={fitness:.3f}')
        return fp
    else:
        track = load_track()
        entry = track['stability'].get(key, {})
        print(f'  ⏳ 等待稳定: {key} ({entry.get("count", 0)}/{3}次)')
        return None

def status():
    """查看跟踪状态"""
    track = load_track()
    print(f'\n🔍 新专家发现跟踪')
    print(f'  {"="*40}')
    print(f'  {"组合":30s} {"次数":6s} {"稳定":6s} {"部署":6s}')
    print(f'  {"="*40}')
    for key, entry in sorted(track['stability'].items(), key=lambda x: x[1]['count'], reverse=True):
        stable = '✅' if key in track['stable'] else '⏳'
        deployed = '📦' if any(d.get('key') == key for d in track['deployed']) else ''
        print(f'  {key:30s} {entry["count"]:3d}次  {stable:4s} {deployed:4s}')
    print(f'  {"="*40}')
    stable_entries = [k for k in track['stable'] if not any(d.get('key') == k for d in track['deployed'])]
    if stable_entries:
        print(f'  ⏳ 已稳定未部署: {len(stable_entries)}个')
        for k in stable_entries:
            print(f'    {k}')
    print(f'  📦 已部署专家: {len(track["deployed"])}个')
    for d in track['deployed']:
        print(f'    {d["name"]:25s} ({d["key"]}) fit={d["fitness"]:.3f}')

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'status':
        status()
    else:
        print('用法: python expert_tracker.py status')
