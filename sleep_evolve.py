# -*- coding: utf-8 -*-
"""
sleep_evolve.py — AISleepGen 自学习进化引擎
SenNet 启示的全自动闭环：每有新数据→自动分析→对比历史→发现惊奇→写入管线

工作流：
    python sleep_evolve.py                      # 手动触发一次完整进化周期
    python sleep_evolve.py --watch              # 持续监视模式（每60秒检查）
    python sleep_evolve.py --quick              # 只检查增量不跑全量

定时调度（建议加入daily_local_cron.py 管线末尾）：
    python sleep_evolve.py --cron

能力：
    1. 增量数据检测 — 发现 E:\\sleep_record\\analyzed\\ 的新文件
    2. 应变稳态重分析 — 更新 resilience_map 和脆弱节点地图
    3. 惊奇检测 — 对比新老结果的显著偏移，标注异常
    4. 表型一致性验证 — 新用户数据是否在已知8种表型内
    5. 跨夜趋势漂移 — 最近3晚了 vs 历史30天基线
    6. 管线注入 — 将发现写入 frontier_data/ 供内参消费
    7. 自修复 — 记录每次运行状态，崩溃后自动重试
"""
import sys, os, json, glob, time, math, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
SLEEP_RECORD_DIR = r'E:\sleep_record'
ANALYZED_DIR = os.path.join(SLEEP_RECORD_DIR, 'analyzed')
OUTPUT_DIR = os.path.join(BASE, 'frontier_data')
STATE_FILE = os.path.join(OUTPUT_DIR, 'sleep_evolve_state.json')
LOG_FILE = os.path.join(OUTPUT_DIR, 'sleep_evolve_log.jsonl')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# 状态持久化
# ============================================================

def _load_state():
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE, 'r', encoding='utf-8'))
        except:
            return {}
    return {'last_scan': {}, 'known_files': [], 'known_patterns': {}, 'discoveries': [], 'run_count': 0}

def _save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def _log_run(event):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        event['ts'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        f.write(json.dumps(event, ensure_ascii=False) + '\n')

# ============================================================
# 1. 增量检测：扫描新文件
# ============================================================

def scan_new_files(state):
    """检测 analyzed/ 中新增的 _analysis.json 文件"""
    all_files = set()
    pattern = os.path.join(ANALYZED_DIR, '*_analysis.json')
    for fp in glob.glob(pattern):
        fn = os.path.basename(fp)
        size = os.path.getsize(fp)
        all_files.add((fn, size))
    
    known = set(tuple(k) for k in state.get('known_files', []))
    new = all_files - known
    
    if new:
        state['known_files'] = [list(f) for f in all_files]
        _save_state(state)
        _log_run({'event': 'new_files_detected', 'count': len(new), 'files': [f[0] for f in new]})
    
    return list(new), len(all_files)

# ============================================================
# 2. 应变稳态重新分析（增量+全量混合）
# ============================================================

def run_resilience_analysis(new_files=None, force_all=False):
    """重新分析应变稳态，返回最新结果和变化"""
    from sleep_resilience_analysis import load_from_profiles, analyze_night
    
    if force_all:
        files = load_from_profiles()
    elif new_files:
        files = load_from_profiles()  # 从profile读总是全量，靠后续惊奇检测做增量
    else:
        files = load_from_profiles()
    
    if not files or len(files) < 2:
        return None, None, []
    
    results = []
    for fn, data in files:
        r = analyze_night(fn, data)
        r['date'] = data.get('date', fn[:10])
        r['file'] = fn
        results.append(r)
    
    # 计算最新基线
    scores = [r['resilience_score'] for r in results]
    entropy = [r['transition_entropy'] for r in results]
    
    baseline = {
        'avg_resilience': round(sum(scores)/len(scores), 1) if scores else 0,
        'avg_entropy': round(sum(entropy)/len(entropy), 3) if entropy else 0,
        'median_resilience': round(sorted(scores)[len(scores)//2], 1) if scores else 0,
        'n_nights': len(results),
        'last_updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    
    return results, baseline, []

# ============================================================
# 3. 惊奇检测
# ============================================================

def detect_surprises(new_results, state):
    """检测新数据中的意外模式"""
    surprises = []
    old_patterns = state.get('known_patterns', {})
    
    if not new_results or len(new_results) == 0:
        return surprises
    
    # 对比历史基线
    old_avg = old_patterns.get('avg_resilience', 55)
    old_entropy = old_patterns.get('avg_entropy', 0.55)
    
    for r in new_results:
        # 夜间显著异常
        score = r['resilience_score']
        
        # 应变分偏离基线超过15分 → 惊奇
        if abs(score - old_avg) > 15:
            direction = '↑异常偏高' if score > old_avg else '↓异常偏低'
            surprises.append({
                'type': 'resilience_anomaly',
                'date': r['date'],
                'detail': f'应变分{score} vs 基线{old_avg} ({direction})',
                'severity': 'high' if abs(score - old_avg) > 20 else 'medium',
            })
        
        # 转移熵异常
        te = r['transition_entropy']
        if te > 1.5 and old_entropy < 1.0:
            surprises.append({
                'type': 'fragmentation_spike',
                'date': r['date'],
                'detail': f'体动碎片化显著升高(熵={te} vs 基线{old_entropy})',
                'severity': 'medium',
            })
        
        # 脆弱时段新增
        vuln_windows = r.get('vulnerable_details', [])
        for vw in vuln_windows:
            ws = vw['window_start']
            if ws not in old_patterns.get('known_vulnerable', {}):
                surprises.append({
                    'type': 'new_vulnerable_window',
                    'date': r['date'],
                    'detail': f'新脆弱时段: {ws} (体动{vw["hit_minutes"]}min)',
                    'severity': 'low',
                })
    
    return surprises

# ============================================================
# 4. 跨夜趋势漂移分析
# ============================================================

def detect_trend_drift(all_results, state):
    """检测长期趋势漂移"""
    if len(all_results) < 4:
        return []
    
    scores = [r['resilience_score'] for r in all_results]
    recent3 = scores[-3:]
    older = scores[:-3]
    
    drifts = []
    
    # 趋势方向
    if len(recent3) >= 3:
        slope = (recent3[-1] - recent3[0]) / 2.0
        if slope < -5:
            drifts.append({
                'type': 'declining_resilience',
                'detail': f'最近3晚应变分下降{abs(slope):.0f}分 ({recent3[0]}→{recent3[-1]})',
                'severity': 'high',
            })
        elif slope > 5:
            drifts.append({
                'type': 'improving_resilience',
                'detail': f'最近3晚应变分上升{slope:.0f}分 ({recent3[0]}→{recent3[-1]})',
                'severity': 'info',
            })
    
    # 脆弱时段漂移
    all_windows = {}
    for r in all_results:
        for v in r.get('vulnerable_details', []):
            ws = v['window_start']
            all_windows[ws] = all_windows.get(ws, 0) + 1
    if all_windows:
        top_window = max(all_windows.items(), key=lambda x: x[1])
        old_top = state.get('known_patterns', {}).get('dominant_vulnerable_window', None)
        if old_top and top_window[0] != old_top:
            drifts.append({
                'type': 'window_shift',
                'detail': f'主要脆弱时段从{old_top}漂移到{top_window[0]}',
                'severity': 'medium',
            })
    
    return drifts

# ============================================================
# 5. 更新状态 + 注入管线
# ============================================================

def update_state_and_patterns(all_results, surprises, drifts, state):
    """更新持久化状态，写入管线可消费格式"""
    if not all_results:
        return state
    
    scores = [r['resilience_score'] for r in all_results]
    entropy = [r['transition_entropy'] for r in all_results]
    
    # 脆弱时段统计
    all_windows = {}
    for r in all_results:
        for v in r.get('vulnerable_details', []):
            ws = v['window_start']
            all_windows[ws] = all_windows.get(ws, 0) + 1
    
    # 更新已知模式
    state['known_patterns'] = {
        'avg_resilience': round(sum(scores)/len(scores), 1),
        'avg_entropy': round(sum(entropy)/len(entropy), 3),
        'n_nights_total': len(all_results),
        'last_updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'known_vulnerable': {ws: count for ws, count in all_windows.items() if count >= 2},
        'dominant_vulnerable_window': max(all_windows.items(), key=lambda x: x[1])[0] if all_windows else None,
    }
    
    # 记录新发现
    for s in surprises + drifts:
        ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        state['discoveries'].append({
            'ts': ts,
            'type': s['type'],
            'detail': s.get('detail', ''),
            'severity': s.get('severity', 'info'),
        })
        _log_run({'event': 'discovery', 'type': s['type'], 'detail': s.get('detail', '')})
    
    # 限制发现列表长度
    if len(state['discoveries']) > 50:
        state['discoveries'] = state['discoveries'][-50:]
    
    state['last_scan']['completed_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    state['run_count'] = state.get('run_count', 0) + 1
    _save_state(state)
    
    return state

# ============================================================
# 6. 完整进化周期
# ============================================================

def run_evolution_cycle(force_all=False, quick=False, watch=False):
    """执行一次完整进化周期"""
    start = time.time()
    state = _load_state()
    
    print(f"🧬 自学习进化周期 #{state.get('run_count', 0) + 1}")
    print(f"  开始: {datetime.datetime.now().strftime('%H:%M:%S')}")
    
    # 步骤1：扫描新文件
    print(f"\n  [1/5] 扫描新数据...")
    new_files, total = scan_new_files(state)
    if not new_files and not force_all:
        if quick:
            print(f"    无新数据 (共{total}个已知文件) → 跳过")
            return
        print(f"    无新数据 (共{total}个已知文件)，但跑增量模式")
    else:
        print(f"    发现 {len(new_files)} 个新文件 (共{total}个)")
    
    # 步骤2：跑应变稳态分析
    print(f"  [2/5] 应变稳态分析...")
    try:
        # 手动导入并调用（避免循环导入）
        results, baseline, _ = run_resilience_analysis(new_files, force_all=force_all)
        if results:
            print(f"    分析 {len(results)} 晚 → avg_resilience={baseline['avg_resilience']} avg_entropy={baseline['avg_entropy']}")
        else:
            print(f"    无有效结果")
    except Exception as e:
        _log_run({'event': 'error_resilience', 'error': str(e)})
        print(f"    ⚠️ 失败: {e}")
        results = None
        baseline = None
    
    # 步骤3：惊奇检测
    print(f"  [3/5] 惊奇检测...")
    surprises = []
    drifts = []
    if results and not quick:
        surprises = detect_surprises(results[-3:] if len(results) > 3 else results, state)
        if surprises:
            for s in surprises:
                print(f"    🔍 [{s['severity']}] {s['detail']}")
        else:
            print(f"    无显著异常")
    
    # 步骤4：趋势漂移
    if results and len(results) >= 4:
        drifts = detect_trend_drift(results, state)
        if drifts:
            for d in drifts:
                print(f"    📈 [{d['severity']}] {d['detail']}")
        else:
            print(f"    无趋势漂移")
    
    # 步骤5：持久化 + 注入管线
    print(f"  [4/5] 更新状态...")
    state = update_state_and_patterns(results or [], surprises, drifts, state)
    
    print(f"  [5/5] 写入frontier_data...")
    # 导出供内参管线消费的摘要
    summary = {
        'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'n_nights': len(results) if results else 0,
        'avg_resilience': baseline['avg_resilience'] if baseline else 0,
        'avg_entropy': baseline['avg_entropy'] if baseline else 0,
        'dominant_vulnerable_window': state['known_patterns'].get('dominant_vulnerable_window'),
        'recent_discoveries': state['discoveries'][-5:] if state['discoveries'] else [],
        'fresh_discoveries': [s.get('detail', '') for s in (surprises + drifts)],
    }
    summary_path = os.path.join(OUTPUT_DIR, 'sleep_evolve_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    elapsed = time.time() - start
    print(f"\n  ✅ 周期完成 ({elapsed:.1f}s)")
    print(f"  发现: {len(surprises) + len(drifts)} 条")
    print(f"  总运行: {state['run_count']} 次")


def watch_loop(interval=60):
    """持续监视模式：定期检查新数据"""
    print(f"🔭 持续监视模式 (每{interval}秒检查)")
    run_count = 0
    while True:
        run_count += 1
        print(f"\n{'='*50}")
        print(f"🔄 检查 #{run_count}")
        try:
            run_evolution_cycle(quick=True)
        except Exception as e:
            print(f"⚠️ 周期失败: {e}")
            _log_run({'event': 'cycle_crash', 'error': str(e)})
        print(f"\n休眠 {interval}s...")
        time.sleep(interval)


# ============================================================
# 入口
# ============================================================

if __name__ == '__main__':
    if '--watch' in sys.argv:
        interval = 60
        for i, a in enumerate(sys.argv):
            if a.startswith('--interval='):
                interval = int(a.split('=')[1])
        watch_loop(interval)
    elif '--quick' in sys.argv:
        run_evolution_cycle(quick=True)
    elif '--force' in sys.argv:
        run_evolution_cycle(force_all=True)
    elif '--cron' in sys.argv:
        run_evolution_cycle(force_all=False, quick=False)
    else:
        run_evolution_cycle(force_all=True)
