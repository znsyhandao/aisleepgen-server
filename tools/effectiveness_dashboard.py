#!/usr/bin/env python3
"""
干预效果仪表盘 v1.0
从感知图和用户 profile 提取干预效果数据，输出结构化报告

用法:
  python effectiveness_dashboard.py [--openid openid] [--days 30]
  
输出:
  每个用户每种干预的成功率、平均评分、建议次数、趋势
"""
import sys, os, json, glob, time
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, r'D:\AISleepGen_Optimized')

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
if not os.path.exists(DATA_DIR):
    DATA_DIR = r'D:\AISleepGen_Optimized\data'

def load_perception_graph():
    """从 wm_memory.jsonl 重建感知图"""
    pg_path = os.path.join(DATA_DIR, 'wm_memory.jsonl')
    if not os.path.exists(pg_path):
        return None
    nodes = {}
    with open(pg_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                entry = json.loads(line)
                if 'nodes' in entry:
                    nodes.update(entry['nodes'])
            except:
                pass
    return nodes

def load_user_profiles():
    """从 user_profile.json 加载所有用户"""
    profile_path = os.path.join(os.path.dirname(DATA_DIR), 'user_profile.json')
    if not os.path.exists(profile_path):
        # 也检查数据目录
        profile_path = os.path.join(DATA_DIR, 'user_profile.json')
    if not os.path.exists(profile_path):
        return {}
    with open(profile_path, encoding='utf-8') as f:
        return json.load(f)

def analyze_interventions(pg_nodes, profiles, days=30):
    """分析干预效果"""
    now = time.time()
    cutoff = now - days * 86400
    
    # 用户列表
    all_openids = set()
    for nid, n in pg_nodes.items():
        if n.get('type') == 'intervention_record':
            all_openids.add(n.get('openid', ''))
    all_openids.update(profiles.keys())
    all_openids.discard('')
    
    reports = {}
    for openid in sorted(all_openids):
        # 收集这个用户的所有干预记录
        records = [
            n for nid, n in pg_nodes.items()
            if n.get('type') == 'intervention_record' and n.get('openid', '') == openid[:8]
            and n.get('ts', 0) >= cutoff
        ]
        
        if not records:
            # 从 user_profile 的 relax_log 补充
            profile = profiles.get(openid, {})
            relax_log = profile.get('relax_log', [])
            for entry in relax_log:
                if isinstance(entry, dict) and entry.get('pattern'):
                    records.append({
                        'action_id': f'breath_{entry["pattern"]}',
                        'completed': entry.get('completed', True),
                        'score_delta': (entry.get('score', 5) - 5) / 5.0,
                        'arousal': entry.get('stress_type', 'unknown'),
                        'ts': time.mktime(datetime.strptime(entry.get('date', '2026-01-01')[:10], '%Y-%m-%d').timetuple()) if entry.get('date') else now,
                    })
        
        # 按干预类型聚合
        by_action = defaultdict(list)
        for r in records:
            by_action[r.get('action_id', 'unknown')].append(r)
        
        action_stats = {}
        for action_id, recs in sorted(by_action.items()):
            total = len(recs)
            completed = sum(1 for r in recs if r.get('completed', False))
            score_deltas = [r.get('score_delta', 0) for r in recs if r.get('score_delta', 0) != 0]
            avg_delta = sum(score_deltas) / len(score_deltas) if score_deltas else 0
            
            # 名称映射
            name_map = {
                'breath_4_7_8': '4-7-8 呼吸', 'breath_box': '箱式呼吸',
                'rain_sound': '雨声白噪音', 'cool_down': '降温',
                'do_nothing': '无干预', 'breath_478': '4-7-8 呼吸',
            }
            display_name = name_map.get(action_id, action_id.replace('_', ' '))
            
            action_stats[action_id] = {
                'name': display_name,
                'total_suggestions': total,
                'completed': completed,
                'completion_rate': round(completed / total * 100, 1) if total > 0 else 0,
                'avg_score_delta': round(avg_delta, 2),
                'effectiveness': '良好' if avg_delta > 0.2 else ('一般' if avg_delta > 0 else '需改进'),
            }
        
        # 用户汇总
        behavior = profiles.get(openid, {}).get('behavior_stats', {})
        relax_log = profiles.get(openid, {}).get('relax_log', [])
        recent_relax = [e for e in relax_log if isinstance(e, dict) and e.get('date','').startswith(datetime.now().strftime('%Y-%m-%d'))]
        
        reports[openid] = {
            'total_sessions': behavior.get('total_relax_sessions', 0),
            'completed_sessions': behavior.get('total_completed_sessions', 0),
            'streak_days': behavior.get('relax_streak_days', 0),
            'avg_duration': behavior.get('avg_relax_duration', 0),
            'today_sessions': len(recent_relax),
            'top_action': max(action_stats.items(), key=lambda x: x[1]['completion_rate'])[0] if action_stats else None,
            'actions': action_stats,
        }
    
    return reports

def print_report(reports):
    """打印结构化报告"""
    print()
    print('=' * 65)
    print('  AISleepGen 干预效果仪表盘')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('=' * 65)
    
    if not reports:
        print('\n  无数据。请先使用 AISleepGen 小程序。')
        return
    
    for openid, report in sorted(reports.items()):
        top_name = report.get('actions', {}).get(report.get('top_action', ''), {}).get('name', '—')
        print(f'\n📊 用户: {openid[:12]}')
        print(f'   总干预: {report["total_sessions"]}次 | '
              f'完成: {report["completed_sessions"]}次 | '
              f'连续: {report["streak_days"]}天 | '
              f'今日: {report["today_sessions"]}次')
        if top_name != '—':
            print(f'   最佳干预: {top_name}')
        
        actions = report.get('actions', {})
        if actions:
            print()
            print(f'   {"干预":20s} {"建议":>4s} {"完成率":>7s} {"效果分":>7s} {"评价":>8s}')
            print(f'   {"-"*20} {"-"*4} {"-"*7} {"-"*7} {"-"*8}')
            for aid, stats in sorted(actions.items()):
                print(f'   {stats["name"]:20s} {stats["total_suggestions"]:>4d} '
                      f'{stats["completion_rate"]:>6.1f}% '
                      f'{stats["avg_score_delta"]:>+6.2f}  '
                      f'{stats["effectiveness"]:>8s}')
        
        print(f'   {"-"*52}')

def main():
    import time  # noqa: used in record timestamp check
    args = sys.argv[1:]
    days = 30
    if '--days' in args:
        idx = args.index('--days')
        if idx + 1 < len(args):
            days = int(args[idx + 1])
    
    print(f'📊 分析最近 {days} 天干预效果...')
    
    pg_nodes = load_perception_graph()
    if pg_nodes is None:
        print('  ⚠️ 感知图未找到 (data/wm_memory.jsonl)')
        pg_nodes = {}
    else:
        print(f'  感知图: {len(pg_nodes)} 个节点')
    
    profiles = load_user_profiles()
    if profiles:
        print(f'  用户配置: {len(profiles)} 个用户')
    
    reports = analyze_interventions(pg_nodes, profiles, days=days)
    print_report(reports)
    
    # 保存 JSON
    out_path = os.path.join(DATA_DIR, '_effectiveness_report.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)
    print(f'\n  报告已保存: {out_path}')
    
    # 生成简短摘要（给小甜甜用）
    summary_lines = []
    for openid, r in sorted(reports.items()):
        top = r.get('top_action', '')
        top_name = r.get('actions', {}).get(top, {}).get('name', '无数据')
        completion_pct = r['completed_sessions'] / max(1, r['total_sessions']) * 100
        summary_lines.append(f'  {openid[:8]}: {r["total_sessions"]}次干预, '
                            f'完成率{completion_pct:.0f}%, '
                            f'最佳={top_name}')
    
    summary_path = os.path.join(DATA_DIR, '_effectiveness_summary.txt')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(f'AISleepGen 干预效果摘要 ({datetime.now().strftime("%Y-%m-%d")})\n')
        f.write(f'用户数: {len(reports)}\n')
        for line in summary_lines:
            f.write(line + '\n')
    print(f'  摘要已保存: {summary_path}')

if __name__ == '__main__':
    main()
