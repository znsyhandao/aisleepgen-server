# -*- coding: utf-8 -*-
"""
sleep_resilience_analysis.py — SenNet 启示①：应变稳态分析
从 E:\\sleep_record 的体动时间序列分析动态恢复力

核心指标：
1. 安静-体动转移概率（Transition Entropy）：高应变稳态=清晰切换，低=碎片化
2. 恢复速度：体动后的回静时间分布
3. 夜间脆弱时段定位：哪个时段体动密度异常高

用法：
    python sleep_resilience_analysis.py                          # 标准分析
    python sleep_resilience_analysis.py --export-json            # 导出JSON到frontier_data
    python sleep_resilience_analysis.py --night 20260610_231333  # 指定单夜

输出：
    - stdout: 每夜 + 跨夜趋势
    - frontier_data/sleep_resilience_{date}.json: 持久化结果
"""
import sys, os, json, glob, math
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
SLEEP_RECORD_DIR = r'E:\sleep_record'
ANALYZED_DIR = os.path.join(SLEEP_RECORD_DIR, 'analyzed')
OUTPUT_DIR = os.path.join(BASE, 'frontier_data')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_analysis_files(night_id=None):
    """加载 analyzed/ 下的所有分析JSON"""
    files = []
    pattern = os.path.join(ANALYZED_DIR, '*_analysis.json')
    for fp in sorted(glob.glob(pattern)):
        fn = os.path.basename(fp)
        if night_id and night_id not in fn:
            continue
        # Skip short records (< 60 min) and test files
        try:
            data = json.load(open(fp, 'r', encoding='utf-8'))
            if data.get('total_minutes', 0) < 60:
                continue
            files.append((fn, data))
        except:
            pass
    return files


def load_from_profiles(profile_path=None):
    """从user_profiles数据加载跨夜体动数据（新通道）
    
    将 profile 的 sleep_data_list 转为 active_blocks + total_minutes 格式
    """
    if profile_path is None:
        pp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                          'user_profiles', 'zunyiba_sleep_record.json')
        if not os.path.exists(pp):
            # fallback: 找第一个profile
            import glob as _glb
            profiles = _glb.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                              'user_profiles', '*.json'))
            if profiles:
                pp = profiles[0]
            else:
                return []
    
    if not os.path.exists(pp):
        return []
    
    with open(pp, 'r', encoding='utf-8') as f:
        profile = json.load(f)
    
    sleep_data_list = profile.get('sleep_data_list', [])
    if not sleep_data_list:
        return []
    
    # 只消费独占数据（男方独睡录音），跳过双人混合数据
    exclusive_only = [e for e in sleep_data_list if e.get('source_type') == 'exclusive']
    if not exclusive_only:
        print('[Resilience] 没有独占数据，回退到全部数据')
        exclusive_only = sleep_data_list
    else:
        print(f'[Resilience] 使用 {len(exclusive_only)} 晚独占数据（排除{len(sleep_data_list)-len(exclusive_only)}晚双人混合）')
    
    files = []
    for entry in exclusive_only:
        date_str = entry.get('date', '')
        movements = entry.get('movement_densities', [])
        total_dur = entry.get('total_duration', 480)
        num_mv = entry.get('body_movement_blocks', 0)
        
        # 从movement_densities构造active_blocks格式
        active_blocks = []
        if movements and len(movements) > 0:
            for m in movements:
                start = m.get('start', 0)
                end = m.get('end', 0)
                dur = m.get('duration', 0)
                if dur > 0:
                    active_blocks.append({
                        'start': f'{int(start//60):02d}:{int(start%60):02d}',
                        'end': f'{int(end//60):02d}:{int(end%60):02d}',
                        'duration_min': dur,
                    })
        # 如果没有movement_densities（旧分析格式只有统计数据），用body_movement_blocks作为信号
        if not active_blocks:
            num_mv = entry.get('body_movement_blocks', 0)
            if num_mv > 0:
                # 分散分布模拟：将体动事件均匀分布到夜间（近似）
                import random as _rnd
                _rnd.seed(42)  # 可复现
                total_dur = entry.get('total_duration', 480)
                spacing = max(total_dur / max(num_mv, 1), 3)  # 至少3分钟间隔
                for i in range(min(num_mv, 200)):  # 最多200个
                    center = i * spacing
                    start = max(0, center - 1)
                    end = min(total_dur, center + 1)
                    dur = end - start
                    if dur > 0:
                        active_blocks.append({
                            'start': f'{int(start//60):02d}:{int(start%60):02d}',
                            'end': f'{int(end//60):02d}:{int(end%60):02d}',
                            'duration_min': dur,
                        })
        
        # 从movement_densities计算体动密度统计
        total_movement_min = sum(m.get('duration', 0) for m in movements)
        quiet_min = max(0, total_dur - total_movement_min)
        quiet_pct = round(quiet_min / max(total_dur, 1) * 100, 1)
        
        mock_data = {
            'date': date_str,
            'filename': f'profile_{date_str}',
            'total_minutes': total_dur,
            'quiet_pct': quiet_pct,
            'active_count': num_mv,
            'active_blocks': active_blocks,
        }
        
        files.append((date_str, mock_data))
    
    # 去重（同一天可能有多条，只保留最后一条）
    seen = {}
    for fn, data in files:
        seen[fn] = data
    deduped = [(k, v) for k, v in seen.items()]
    
    if deduped != files:
        pass  # dedup worked
    
    return deduped


def compute_transition_entropy(active_blocks, total_minutes):
    """计算安静-体动转移熵：标识体动模式的随机性"""
    if not active_blocks or total_minutes <= 0:
        return 0.0, 0, 0
    
    # 从体动block列表构建状态序列（1分钟粒度）
    n_buckets = max(1, int(total_minutes))
    state = [0] * n_buckets  # 0=安静, 1=体动
    
    for block in active_blocks:
        start_min = int(_time_to_minutes(block.get('start', '00:00')))
        end_min = int(_time_to_minutes(block.get('end', '00:00')))
        dur = int(block.get('duration_min', 1))
        for m in range(max(0, start_min), min(n_buckets, start_min + dur)):
            state[m] = 1
    
    # 转移计数
    n_00 = n_01 = n_10 = n_11 = 0
    for i in range(1, n_buckets):
        prev = state[i-1]
        cur = state[i]
        if prev == 0 and cur == 0:
            n_00 += 1
        elif prev == 0 and cur == 1:
            n_01 += 1
        elif prev == 1 and cur == 0:
            n_10 += 1
        elif prev == 1 and cur == 1:
            n_11 += 1
    
    # 转移概率
    total_0 = n_00 + n_01
    total_1 = n_10 + n_11
    p_0_to_0 = n_00 / max(total_0, 1)
    p_0_to_1 = n_01 / max(total_0, 1)
    p_1_to_0 = n_10 / max(total_1, 1)
    p_1_to_1 = n_11 / max(total_1, 1)
    
    # 转移熵：高=模式随机不可预测（应变稳态差）
    # 低=模式清晰可预测（高应变稳态：长安静偶尔体动）
    def _entropy(p):
        return -p * math.log2(p) if p > 0 else 0
    
    h_0 = _entropy(p_0_to_0) + _entropy(p_0_to_1)
    h_1 = _entropy(p_1_to_0) + _entropy(p_1_to_1)
    # 加权平均
    stationary_p0 = total_0 / max(n_buckets, 1)
    stationary_p1 = total_1 / max(n_buckets, 1)
    transition_entropy = stationary_p0 * h_0 + stationary_p1 * h_1
    
    return round(transition_entropy, 3), int(n_01), int(n_10)


def compute_recovery_speed(active_blocks, total_minutes):
    """计算每次体动后的回静时间分布"""
    if not active_blocks or len(active_blocks) < 2:
        return 0, []
    
    # 体动间隔 = recovery time
    intervals = []
    _prev_end = 0
    for block in active_blocks:
        start_min = _time_to_minutes(block.get('start', '00:00'))
        end_min = _time_to_minutes(block.get('end', '00:00'))
        if _prev_end > 0:
            gap = start_min - _prev_end
            if gap > 0:
                intervals.append(gap)
        _prev_end = end_min
    
    if not intervals:
        return 0, []
    
    avg_recovery = sum(intervals) / len(intervals)
    # 恢复速度变异系数：低=稳定恢复，高=恢复不稳定
    recovery_cv = (sum((i - avg_recovery)**2 for i in intervals) / len(intervals))**0.5 / max(avg_recovery, 1)
    return round(avg_recovery, 1), [round(i, 1) for i in intervals], round(recovery_cv, 2)


def locate_vulnerable_windows(active_blocks, total_minutes):
    """定位夜间体动密度异常高的时段（候选脆弱节点）"""
    if not active_blocks or total_minutes <= 0:
        return []
    
    # 按30分钟窗口统计体动密度
    window_min = 30
    n_windows = max(1, int(total_minutes / window_min))
    window_hits = [0] * n_windows
    
    for block in active_blocks:
        start_min = _time_to_minutes(block.get('start', '00:00'))
        dur = block.get('duration_min', 1)
        w_start = int(start_min / window_min)
        w_end = min(n_windows - 1, int((start_min + dur) / window_min))
        for w in range(w_start, w_end + 1):
            if w < n_windows:
                window_hits[w] += dur
    
    # 找到密度超过均值+1.5sigma的窗口
    mean_hits = sum(window_hits) / max(n_windows, 1)
    std_hits = (sum((h - mean_hits)**2 for h in window_hits) / max(n_windows, 1))**0.5
    threshold = mean_hits + 1.5 * std_hits
    
    vulnerable = []
    for w_idx, hits in enumerate(window_hits):
        if hits > threshold:
            w_start_min = w_idx * window_min
            vulnerable.append({
                'window_start': f'{int(w_start_min/60):02d}:{int(w_start_min%60):02d}',
                'hit_minutes': int(hits),
                'intensity': round(hits / window_min, 2),
            })
    
    return vulnerable


def _time_to_minutes(t_str):
    """将 'HH:MM' 转为当日分钟数"""
    parts = t_str.split(':')
    if len(parts) == 2:
        h, m = int(parts[0]), int(parts[1])
        return h * 60 + m
    return 0


def analyze_night(filename, data):
    """分析单夜数据"""
    active_blocks = data.get('active_blocks', [])
    total_min = data.get('total_minutes', 0)
    quiet_pct = data.get('quiet_pct', 0)
    active_count = data.get('active_count', 0)
    
    # 1. 转移熵
    te, n_01, n_10 = compute_transition_entropy(active_blocks, total_min)
    
    # 2. 恢复速度
    avg_recovery = 0
    intervals = []
    recovery_cv = 0
    if len(active_blocks) >= 2:
        avg_recovery, intervals, recovery_cv = compute_recovery_speed(active_blocks, total_min)
    
    # 3. 脆弱时段
    vulnerable = locate_vulnerable_windows(active_blocks, total_min)
    
    # 4. 应变稳态评分（0-100，越高越好）
    # 转移熵越低越好（体动模式清晰）
    # 恢复速度适中最好（太慢=僵化恢复差，太快=碎片化）
    # 脆弱时段少越好
    score = 70  # baseline
    # 转移熵扣分：>1.5 bits = 碎片化严重
    if te > 2.0:
        score -= 15
    elif te > 1.5:
        score -= 8
    elif te < 0.5:
        score += 5  # 模式过于单一也可能是僵化
    # 恢复速度扣分：<2min=碎片化, >15min=恢复慢
    if avg_recovery < 3:
        score -= 10
    elif avg_recovery < 5:
        score -= 3
    elif avg_recovery > 15:
        score -= 8
    elif 8 <= avg_recovery <= 12:
        score += 5  # 理想恢复速度
    # 脆弱时段扣分
    score -= len(vulnerable) * 5
    # 体动次数扣分
    expected_quiet = (quiet_pct / 100) * total_min
    if active_count > 30:
        score -= 10
    elif active_count > 20:
        score -= 5
        
    score = max(0, min(100, score))
    
    return {
        'transition_entropy': te,
        'quiet_to_active_transitions': n_01,
        'active_to_quiet_transitions': n_10,
        'avg_recovery_min': avg_recovery,
        'recovery_cv': recovery_cv,
        'vulnerable_windows': len(vulnerable),
        'vulnerable_details': vulnerable,
        'resilience_score': score,
        'quiet_pct': quiet_pct,
        'active_count': active_count,
    }


def analyze_all(from_profile=True):
    """分析所有夜晚，给出趋势
    
    Args:
        from_profile: True 从 user_profiles 读取, False 从旧 analyzed/ 读取
    """
    if from_profile:
        files = load_from_profiles()
        src = "user_profiles"
    else:
        files = load_analysis_files()
        src = "analyzed"
    print(f"📊 从 {src} 加载了 {len(files)} 晚睡眠分析数据")
    
    results = []
    for fn, data in files:
        date_str = data.get('date', fn[:8])
        r = analyze_night(fn, data)
        r['date'] = date_str
        r['file'] = fn
        results.append(r)
        total_h = data.get('total_hours', data.get('total_minutes', 0) / 60)
        
        # 打印单夜结果
        hits = r.get('vulnerable_windows', 0)
        vuln_str = f" ⚠️{hits}脆弱时段" if hits else ""
        rec_str = f" 恢复均{round(r['avg_recovery_min'],1)}min CV={r.get('recovery_cv', 0)}" if r.get('avg_recovery_min') else ""
        print(f"  {date_str}: 转移熵{r['transition_entropy']} 应变分{r['resilience_score']}{rec_str}{vuln_str}")
    
    if len(results) >= 3:
        # 趋势分析
        scores = [r['resilience_score'] for r in results]
        latest3 = scores[-3:]
        trend = '上升' if latest3[-1] > latest3[0] else ('下降' if latest3[-1] < latest3[0] else '稳定')
        print(f"\n📈 最近3晚趋势: {trend} ({' → '.join(str(s) for s in latest3)})")
        
        best = max(results, key=lambda r: r['resilience_score'])
        worst = min(results, key=lambda r: r['resilience_score'])
        print(f"  最佳夜: {best['date']} ({best['resilience_score']}分)")
        print(f"  最差夜: {worst['date']} ({worst['resilience_score']}分)")
        
        # 跨夜脆弱时段一致性分析
        all_windows = {}
        for r in results:
            for v in r.get('vulnerable_details', []):
                ws = v['window_start']
                all_windows[ws] = all_windows.get(ws, 0) + 1
        if all_windows:
            recurrent = sorted(all_windows.items(), key=lambda x: -x[1])
            print(f"\n🔍 跨夜脆弱时段（出现次数≥2）：")
            for ws, count in recurrent:
                if count >= 2:
                    print(f"  {ws} — {count}/{len(results)} 晚出现")
    
    return results


def export_json(results):
    """导出结果到frontier_data"""
    output = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'total_nights': len(results),
        'nights': results,
        'summary': {}
    }
    if results:
        scores = [r['resilience_score'] for r in results]
        output['summary'] = {
            'avg_resilience': round(sum(scores)/len(scores), 1),
            'min_resilience': min(scores),
            'max_resilience': max(scores),
            'recent_trend': 'up' if len(scores) >= 3 and scores[-1] > scores[-3] else ('down' if len(scores) >= 3 and scores[-1] < scores[-3] else 'stable'),
        }
    
    path = os.path.join(OUTPUT_DIR, 'sleep_resilience.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n💾 已导出: {path} ({len(results)} 晚)")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='应变稳态分析')
    parser.add_argument('--export-json', action='store_true')
    parser.add_argument('--night', type=str, default=None)
    parser.add_argument('--from-profile', action='store_true', default=True,
                        help='从 user_profiles 读取（默认开启）')
    parser.add_argument('--from-old', action='store_true',
                        help='从旧 analyzed/ 读取')
    args = parser.parse_args()
    
    print("=" * 60)
    print("🧬 应变稳态分析 (SenNet 启示①)")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    from_profile = not args.from_old  # 默认True
    results = analyze_all(from_profile=from_profile)
    
    if args.export_json and results:
        export_json(results)
    
    print(f"\n{'='*60}")
    print("✅ 完成")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
