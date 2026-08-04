#!/usr/bin/env python3
"""data_flywheel.py — 数据飞轮健康度检查器

受 2026-07-04 战略内参 Covariant 数据管道启发：
检查 AISleepGen 用户数据积累 → 个性化提升 → 留存增强 的三环飞轮是否健康。

检查项:
  1. 基础数据量: 活跃用户 / session / 干预次数
  2. 数据深度曲线: 用户使用次数 vs 评分趋势
  3. 留存分析: 按使用次数分桶
  4. 个性化衰减: 近期活跃 vs 沉默用户的评分趋势
  5. 飞轮闭环: 数据积累 → 评分改善 的关联性

用法:
  python dev_tools/check/data_flywheel.py --dir ./

依赖:
  user_profile.json (用户画像)
"""
import os, sys, json, glob, argparse, math, re
from datetime import datetime, timedelta
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

# ── 配置 ──
TODAY = datetime.now().strftime('%Y-%m-%d')
RECENT_DAYS = 30
RETENTION_COHORT_DAYS = [1, 7, 30]

# 从 SQLite（真实数据源）读取用户画像
def _load_profiles_from_db():
    """加载用户画像（优先 SQLite，fallback JSON）"""
    try:
        import sys
        # 确保能导入项目根目录的模块
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.normpath(os.path.join(script_dir, '..', '..'))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from db_sqlite import get_db
        db = get_db()
        profiles = db.load_all_profiles()
        if profiles and len(profiles) > 0:
            return profiles
    except Exception as e:
        print(f"  ⚠  SQLite 读取失败: {e}，降级到 JSON")

    # Fallback to JSON
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'user_profile.json')
    return safe_load_json(json_path, {})


def safe_load_json(path, default=None):
    """安全加载 JSON，失败返回默认值"""
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        return json.load(open(path, 'r', encoding='utf-8'))
    except (json.JSONDecodeError, Exception) as e:
        print(f"  ⚠  加载 {path} 失败: {e}")
        return default if default is not None else {}


def format_pct(v):
    """格式化百分比"""
    if isinstance(v, float) and not math.isnan(v):
        return f"{v*100:.1f}%"
    return "N/A"


def check_basic_metrics(workdir):
    """检查基础数据量"""
    print("\n━━━ [1/5] 基础数据量 ━━━")

    # 用户画像（从 SQLite 读取）
    profiles = _load_profiles_from_db()
    user_count = len(profiles) if isinstance(profiles, dict) else 0

    # 审计日志
    audit_dir = os.path.join(workdir, 'data', 'audit_logs')
    log_files = []
    recent_log_entries = 0
    if os.path.isdir(audit_dir):
        log_files = sorted(glob.glob(os.path.join(audit_dir, '**/*.jsonl'), recursive=True))
        cutoff = datetime.now() - timedelta(days=RECENT_DAYS)
        for lf in log_files[-20:]:
            try:
                fdate = os.path.basename(os.path.dirname(lf))
                if fdate >= (datetime.now() - timedelta(days=RECENT_DAYS)).strftime('%Y-%m-%d'):
                    with open(lf, 'r', encoding='utf-8', errors='replace') as f:
                        recent_log_entries += sum(1 for _ in f)
            except:
                pass

    # 睡眠数据
    sleep_dir = os.path.join(workdir, 'data', 'sleep_data')
    sleep_records = 0
    if os.path.isdir(sleep_dir):
        sleep_records = len(glob.glob(os.path.join(sleep_dir, '**/*.json'), recursive=True))

    print(f"  注册用户:            {user_count}")
    print(f"  近期审计日志文件:     {len(log_files)} 个")
    print(f"  近{RECENT_DAYS}天日志条目:    {recent_log_entries}")
    print(f"  睡眠记录:             {sleep_records}")
    print(f"  每日活跃用户(估算):   {recent_log_entries // RECENT_DAYS if RECENT_DAYS else 0}")

    return {
        'user_count': user_count,
        'log_files': len(log_files),
        'recent_log_entries': recent_log_entries,
        'sleep_records': sleep_records,
        'daily_active_est': recent_log_entries // max(RECENT_DAYS, 1),
    }


def check_data_depth(workdir, metrics):
    """检查数据深度——用户使用天数 vs 评分趋势"""
    print("\n━━━ [2/5] 数据深度曲线 ━━━")

    profiles = _load_profiles_from_db()

    if not isinstance(profs := profiles, dict):
        print("  ⚠  用户画像格式异常，跳过")
        return {}

    # 统计每个用户的 session / history 数量
    depth_stats = {'1-3次': [], '4-10次': [], '11-30次': [], '30+次': []}
    depth_ranges = [(1, 3, '1-3次'), (4, 10, '4-10次'), (11, 30, '11-30次'), (31, 9999, '30+次')]

    total_with_depth = 0
    for openid, profile in profs.items():
        if not isinstance(profile, dict):
            continue
        raw = profile

        total_sessions = raw.get('total_sessions', 0) or 0
        if total_sessions <= 0:
            continue

        total_with_depth += 1

        # 归入深度区间
        for lo, hi, label in depth_ranges:
            if lo <= total_sessions <= hi:
                depth_stats[label].append(raw)
                break
        else:
            depth_stats['30+次'].append(raw)

    # 输出
    print(f"  有使用记录的用户: {total_with_depth}")
    for label in ['1-3次', '4-10次', '11-30次', '30+次']:
        group = depth_stats[label]
        if group:
            avg_sess = sum(g.get('total_sessions', 0) or 0 for g in group) / len(group)
            avg_hist = sum(len(g.get('history', [])) for g in group) / len(group)
            print(f"  {label:10s} {len(group):>4d}人 | 平均{avg_sess:.0f}次 | history{avg_hist:.0f}条")
            # 看最近 5 个 history 的评分趋势
            scores = []
            for g in group:
                hist = g.get('history', [])
                for h in hist[-5:]:
                    if isinstance(h, dict):
                        s = h.get('sleep_score', h.get('score', 0))
                        if s:
                            scores.append(s)
            if len(scores) >= 10:
                first_half = sum(scores[:len(scores)//2]) / (len(scores)//2)
                second_half = sum(scores[len(scores)//2:]) / (len(scores) - len(scores)//2)
                delta = second_half - first_half
                arrow = "📈" if delta > 1 else "📉" if delta < -1 else "➡️"
                print(f"  {'':10s} 评分趋势: {first_half:.0f} → {second_half:.0f} ({delta:+.0f}) {arrow}")
        else:
            print(f"  {label:10s}    0人")

    return {'depth_stats': {k: len(v) for k, v in depth_stats.items()}, 'total_with_depth': total_with_depth}


def check_retention(workdir, metrics):
    """检查留存——从审计日志推断"""
    print(f"\n━━━ [3/5] 留存分析 ━━━")

    # 从用户画像的 history 长度推断留存
    profiles = _load_profiles_from_db()

    if not isinstance(profs := profiles, dict):
        print("  ⚠  用户画像格式异常，跳过留存分析")
        return {}

    # 按 history 长度分桶（即 session 次数）
    buckets = {'1次': 0, '2-3次': 0, '4-10次': 0, '11-30次': 0, '30+次': 0}
    ranges = [(1, 1, '1次'), (2, 3, '2-3次'), (4, 10, '4-10次'), (11, 30, '11-30次'), (31, 9999, '30+次')]

    repeat_users = 0
    for openid, profile in profs.items():
        if not isinstance(profile, dict):
            continue
        sessions = profile.get('total_sessions', 0) or 0
        history_len = len(profile.get('history', []))

        usage = max(sessions, history_len)
        if usage <= 0:
            buckets.setdefault('0次', 0)
            buckets['0次'] = buckets.get('0次', 0) + 1
            continue

        if usage >= 2:
            repeat_users += 1

        for lo, hi, label in ranges:
            if lo <= usage <= hi:
                buckets[label] = buckets.get(label, 0) + 1
                break

    total_users = sum(buckets.values())
    print(f"  总用户: {total_users}")
    print(f"  回访用户(使用≥2次): {repeat_users}")
    for label in ['0次', '1次', '2-3次', '4-10次', '11-30次', '30+次']:
        count = buckets.get(label, 0)
        pct = count / max(total_users, 1) * 100
        bar = '█' * int(pct / 5) + '░' * (20 - int(pct / 5))
        print(f"  {label:10s} {count:>4d}人 {bar} {pct:.0f}%")

    return {
        'total_users': total_users,
        'repeat_users': repeat_users,
        'buckets': buckets,
    }





def check_personalization_decay(workdir, metrics):
    """检查个性化衰减——活跃 vs 沉默用户的评分趋势"""
    print(f"\n━━━ [4/5] 个性化衰减检测 ━━━")

    # 从用户画像判断活跃/沉默用户
    profiles = _load_profiles_from_db()

    if not isinstance(profs := profiles, dict) or not profs:
        print("  ⚠  用户画像数据不足，跳过衰减检测")
        return {}

    # 找活跃用户：有 history 且最近 history 的时间戳在7天内
    recent_logs = set()
    for openid, profile in profs.items():
        if not isinstance(profile, dict):
            continue
        hist = profile.get('history', [])
        if not hist:
            continue
        # 取最后一条 history 的时间戳
        last_entry = hist[-1]
        if isinstance(last_entry, dict):
            ts = last_entry.get('timestamp', last_entry.get('time', ''))
            if isinstance(ts, str):
                try:
                    dt = datetime.fromisoformat(ts)
                    if dt >= cutoff:
                        recent_logs.add(openid)
                except:
                    pass

    active_count = 0
    silent_count = 0
    active_scores = []
    silent_scores = []
    active_improvement = []
    silent_improvement = []

    for openid, profile in profs.items():
        if not isinstance(profile, dict):
            continue
        raw = profile
        is_active = openid in recent_logs
        hist = raw.get('history', [])

        # 从 history 里算评分趋势
        scores_list = []
        for h in hist:
            if isinstance(h, dict):
                s = h.get('sleep_score', h.get('score', 0))
                if s:
                    scores_list.append(s)

        if not scores_list:
            continue

        avg_s = sum(scores_list) / len(scores_list)
        first_s = scores_list[0]
        last_s = scores_list[-1]
        improvement = last_s - first_s

        if is_active:
            active_count += 1
            active_scores.append(avg_s)
            active_improvement.append(improvement)
        else:
            silent_count += 1
            silent_scores.append(avg_s)
            silent_improvement.append(improvement)

    print(f"  近7天活跃用户: {active_count}")
    print(f"  沉默用户(7天+): {silent_count}")

    if active_scores:
        avg_active_score = sum(active_scores) / len(active_scores)
        avg_active_impr = sum(active_improvement) / len(active_improvement) if active_improvement else 0
        print(f"  活跃用户平均评分: {avg_active_score:.0f} (改善{avg_active_impr:+.0f})")
    if silent_scores:
        avg_silent_score = sum(silent_scores) / len(silent_scores)
        avg_silent_impr = sum(silent_improvement) / len(silent_improvement) if silent_improvement else 0
        print(f"  沉默用户平均评分: {avg_silent_score:.0f} (改善{avg_silent_impr:+.0f})")

    if active_scores and silent_scores:
        gap = sum(active_scores)/len(active_scores) - sum(silent_scores)/len(silent_scores)
        if gap > 5:
            print(f"  ⚠  活跃 vs 沉默评分差距 {gap:.0f}分 —— 数据飞轮在转，但沉默用户掉队")
        elif gap < -5:
            print(f"  ⚠  沉默用户评分反超活跃用户 —— 可能活跃用户是新手")
        else:
            print(f"  ✅ 活跃/沉默评分差距 {gap:.0f}分，飞轮健康")

    return {
        'active': active_count,
        'silent': silent_count,
        'active_avg_score': round(sum(active_scores)/len(active_scores), 1) if active_scores else 0,
        'silent_avg_score': round(sum(silent_scores)/len(silent_scores), 1) if silent_scores else 0,
        'active_avg_impr': round(sum(active_improvement)/len(active_improvement), 1) if active_improvement else 0,
        'silent_avg_impr': round(sum(silent_improvement)/len(silent_improvement), 1) if silent_improvement else 0,
    }


def check_flywheel_closure(workdir, metrics):
    """检查飞轮闭环——数据深度 vs 留存的相关性"""
    print(f"\n━━━ [5/5] 飞轮闭环关联 ━━━")

    profiles = _load_profiles_from_db()

    if not isinstance(profs := profiles, dict) or not profs:
        print("  ⚠  数据不足，跳过闭环关联")
        return {}

    # 取有足够数据的用户
    samples = []
    for openid, profile in profs.items():
        if not isinstance(profile, dict):
            continue
        raw = profile
        sessions = raw.get('total_sessions', 0) or 0
        hist = raw.get('history', [])
        history_len = len(hist)

        if sessions < 2:
            continue

        # 从 history 里提取评分
        scores_list = []
        first_score = None
        last_score = None
        for h in hist:
            if isinstance(h, dict):
                s = h.get('sleep_score', h.get('score', None))
                if s is not None:
                    scores_list.append(s)
                    if first_score is None:
                        first_score = s
                    last_score = s

        if not scores_list:
            continue

        samples.append({
            'sessions': max(sessions, history_len),
            'avg_score': sum(scores_list) / len(scores_list),
            'hist_len': history_len,
            'first': first_score,
            'last': last_score,
            'improvement': (last_score or 0) - (first_score or 0),
        })

    if not samples:
        print("  ⚠  有效样本不足")
        return {}

    # 按数据深度分组看评分
    groups = {'浅度(2-3次)': [], '中度(4-10次)': [], '深度(11次+)': []}
    for s in samples:
        if s['sessions'] <= 3:
            groups['浅度(2-3次)'].append(s)
        elif s['sessions'] <= 10:
            groups['中度(4-10次)'].append(s)
        else:
            groups['深度(11次+)'].append(s)

    print(f"  有效样本: {len(samples)} 人 (使用≥2次且有评分)")
    for label in ['浅度(2-3次)', '中度(4-10次)', '深度(11次+)']:
        g = groups[label]
        if not g:
            continue
        avg_score = sum(s['avg_score'] for s in g) / len(g)
        avg_sess = sum(s['sessions'] for s in g) / len(g)
        avg_impr = sum(s['improvement'] for s in g) / len(g)
        print(f"  {label:16s} {len(g):>3d}人 | 评分{avg_score:6.0f} | {avg_sess:.0f}次 | 改善{avg_impr:+.0f}")

    # 简单相关性：评分 vs 使用次数
    if len(samples) >= 5:
        sorted_samples = sorted(samples, key=lambda s: s['sessions'])
        bottom = sorted_samples[:max(len(sorted_samples)//3, 3)]
        top = sorted_samples[-max(len(sorted_samples)//3, 3):]
        bottom_avg = sum(s['avg_score'] for s in bottom) / len(bottom)
        top_avg = sum(s['avg_score'] for s in top) / len(top)
        delta = top_avg - bottom_avg

        print(f"  使用次数低(1/3)平均评分: {bottom_avg:.0f}")
        print(f"  使用次数高(1/3)平均评分: {top_avg:.0f}")
        if delta > 5:
            print(f"  ✅ 飞轮正向闭环: 使用越多评分越高 (+{delta:.0f})")
        elif delta > 0:
            print(f"  ➡️ 飞轮微弱正向: 评分差距 {delta:.0f}")
        else:
            print(f"  ⚠  飞轮可能失效: 使用越多评分反而下降 ({delta:.0f})")

    return {
        'sample_size': len(samples),
        'group_scores': {k: round(sum(s['avg_score'] for s in v)/len(v), 1) if v else 0
                         for k, v in groups.items()},
    }


def main():
    parser = argparse.ArgumentParser(description='数据飞轮健康度检查器')
    parser.add_argument('--dir', default=os.getcwd(), help='项目根目录')
    args = parser.parse_args()
    workdir = args.dir

    print(f"{'='*60}")
    print(f"  🌀 数据飞轮健康度检查 — {TODAY}")
    print(f"  AISleepGen Data Flywheel Report")
    print(f"{'='*60}")

    print(f"\n  受 2026-07-04 战略内参 Covariant 数据管道启发")
    print(f"  检查数据积累 → 个性化 → 留存 闭环")
    print(f"  分析目录: {workdir}")

    results = {}

    # [1] 基础数据量
    m1 = check_basic_metrics(workdir)
    results['basic'] = m1

    # [2] 数据深度曲线
    m2 = check_data_depth(workdir, results)
    results['depth'] = m2

    # [3] 留存分析
    m3 = check_retention(workdir, results)
    results['retention'] = m3

    # [4] 个性化衰减
    m4 = check_personalization_decay(workdir, results)
    results['decay'] = m4

    # [5] 飞轮闭环
    m5 = check_flywheel_closure(workdir, results)
    results['closure'] = m5

    # ── 健康评分 ──
    print(f"\n{'='*60}")
    print(f"  📊 综合评分")
    print(f"{'='*60}")

    score = 100
    issues = []

    # 基础数据量
    uc = m1.get('user_count', 0)
    if uc < 10:
        score -= 20
        issues.append(f"用户量过少({uc})")
    elif uc < 100:
        score -= 10
        issues.append(f"用户量偏少({uc})")

    # 留存
    buckets = m3.get('buckets', {})
    repeat_users = m3.get('repeat_users', 0)
    if repeat_users < 5:
        score -= 20
        issues.append("重复用户不足5人")
    elif repeat_users < 20:
        score -= 10
        issues.append("重复用户偏少")

    # 飞轮闭环
    closure = m5.get('group_scores', {})
    deep_score = closure.get('深度(11次+)', 0)
    shallow_score = closure.get('浅度(2-3次)', 0)
    if deep_score and shallow_score and deep_score < shallow_score:
        score -= 15
        issues.append("深度用户评分低于浅度用户(飞轮可能失效)")

    # 评分
    print(f"\n  总分: {max(score, 0)}/100")
    if score >= 80:
        print(f"  评级: 🟢 健康")
    elif score >= 60:
        print(f"  评级: 🟡 需关注")
    else:
        print(f"  评级: 🔴 需紧急修复")

    if issues:
        print(f"  问题: {', '.join(issues)}")
    else:
        print(f"  问题: 无")

    print(f"\n  {'='*60}")
    print(f"  报告完成: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}")

    return 0 if score >= 60 else 1


if __name__ == '__main__':
    main()
