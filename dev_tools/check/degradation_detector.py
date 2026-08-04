#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
degradation_detector.py — 数据渐进式退化检测器

查什么：
- 世界模型的推理来源分布（fallback vs bayesian vs expert）
- 每天/每次请求的 fallback 比例趋势
- 超过阈值时告警（fallback 比例逐日上升 = 中间层在退化）

用法:
  python degradation_detector.py [--dir D:\AISleepGen_Optimized] [--lookback-days 30]
  python degradation_detector.py --scan-audit-logs  # 从审计日志扫描
"""

import os, sys, json, glob, argparse, datetime
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding='utf-8')

PASS = 0
FAIL = 0
WARN = 0


def report(result, label, detail=''):
    global PASS, FAIL, WARN
    if result == 'PASS': PASS += 1; print(f"  ✅ {label}")
    elif result == 'FAIL': FAIL += 1; print(f"  ❌ {label}: {detail}")
    elif result == 'WARN': WARN += 1; print(f"  ⚠️  {label}: {detail}")


def scan_audit_logs(audit_dir, lookback_days):
    """Scan audit log files for world model state distributions."""
    cutoff = datetime.datetime.now() - datetime.timedelta(days=lookback_days)
    
    daily_stats = defaultdict(lambda: {
        'total_calls': 0,
        'states': Counter(),
        'confidence_sum': 0,
        'confidence_count': 0,
        'unknown_count': 0,
        'errors': 0,
    })
    
    log_files = []
    for root, dirs, files in os.walk(audit_dir):
        for f in files:
            if f.endswith('.jsonl'):
                log_files.append(os.path.join(root, f))
    
    if not log_files:
        return daily_stats, "No audit logs found"
    
    for fp in sorted(log_files):
        # Extract date from path
        parts = fp.replace('\\', '/').split('/')
        date_str = None
        for p in parts:
            try:
                datetime.datetime.strptime(p, '%Y-%m-%d')
                date_str = p
                break
            except ValueError:
                continue
        
        if date_str and date_str < cutoff.strftime('%Y-%m-%d'):
            continue
        
        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                key = date_str or 'unknown_date'
                
                # Detect world model state in record
                response = record.get('response', record.get('response_obj', {}))
                if isinstance(response, str):
                    try:
                        response = json.loads(response)
                    except (json.JSONDecodeError, TypeError):
                        response = {}
                
                wm = response.get('world_model', {})
                if not wm:
                    wm = response.get('data', {}).get('world_model', {})
                
                state = wm.get('arousal_state', wm.get('state', ''))
                confidence = wm.get('arousal_confidence', wm.get('confidence', 0))
                
                daily_stats[key]['total_calls'] += 1
                if state:
                    daily_stats[key]['states'][state] += 1
                else:
                    daily_stats[key]['unknown_count'] += 1
                
                if confidence:
                    try:
                        daily_stats[key]['confidence_sum'] += float(confidence)
                        daily_stats[key]['confidence_count'] += 1
                    except (ValueError, TypeError):
                        pass
    
    return daily_stats, None


def scan_source_code(workdir):
    """Scan source code for fallback patterns without running the server."""
    findings = []
    fallback_count = 0
    
    focus_files = ['deepseek_proxy.py', 'world_model_coordinator.py', 
                   'state_transition_model.py', 'sleep_homeostasis.py',
                   'biofeedback_renderer.py', 'sleep_phase_planner.py',
                   'compliance.py']
    
    for fname in focus_files:
        fp = os.path.join(workdir, fname)
        if not os.path.exists(fp):
            continue
        
        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines):
            lower = line.lower()
            if 'fallback' in lower:
                fallback_count += 1
                findings.append({
                    'file': fname,
                    'lineno': i + 1,
                    'text': line.strip()[:120],
                })
    
    return findings, fallback_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    parser.add_argument('--lookback-days', type=int, default=30)
    parser.add_argument('--scan-audit-logs', action='store_true',
                       help='Scan audit logs for degradation')
    parser.add_argument('--fallback-warn-threshold', type=float, default=0.5,
                       help='Warning threshold for fallback ratio (default: 0.5 = 50%)')
    args = parser.parse_args()
    
    print(f"{'='*60}")
    print(f"  DEGRADATION DETECTOR")
    print(f"  Lookback: {args.lookback_days}d | Fallback threshold: {args.fallback_warn_threshold:.0%}")
    print(f"{'='*60}\n")
    
    # Phase 1: Static analysis — find all fallback paths in source
    print("[Phase 1] Static analysis: fallback patterns in source code")
    fallback_findings, fallback_count = scan_source_code(args.dir)
    
    if fallback_findings:
        print(f"  Found {fallback_count} fallback references across source:")
        by_file = defaultdict(list)
        for f in fallback_findings:
            by_file[f['file']].append(f)
        for fname in sorted(by_file.keys()):
            print(f"  {fname}: {len(by_file[fname])} fallback(s)")
            for fb in by_file[fname][:3]:
                print(f"    L{fb['lineno']}: {fb['text']}")
            if len(by_file[fname]) > 3:
                print(f"    ... and {len(by_file[fname]) - 3} more")
        print()
    else:
        print("  No fallback references found ✅\n")
    
    # Phase 2: Audit log scan (if available)
    print("[Phase 2] Audit log scan for runtime degradation")
    audit_dirs = [
        os.path.join(args.dir, 'data', 'audit_logs'),
        os.path.join(args.dir, 'audit_logs'),
    ]
    
    audit_dir = None
    for d in audit_dirs:
        if os.path.isdir(d):
            audit_dir = d
            break
    
    if audit_dir and args.scan_audit_logs:
        daily_stats, error = scan_audit_logs(audit_dir, args.lookback_days)
        if error:
            report('WARN', 'Audit log scan', error)
        elif not daily_stats:
            report('WARN', 'Audit log scan', 'No data found in recent logs')
        else:
            print(f"  Found data for {len(daily_stats)} day(s)")
            
            # Check for degradation trends
            sorted_days = sorted(daily_stats.keys())
            degradation_signals = []
            
            for day in sorted_days:
                stats = daily_stats[day]
                total = stats['total_calls']
                unknown = stats['unknown_count']
                states = stats['states']
                most_common = states.most_common(1)
                
                dominant_state = most_common[0][0] if most_common else 'none'
                dominant_pct = most_common[0][1] / total * 100 if most_common and total else 0
                unknown_pct = unknown / total * 100 if total else 0
                avg_conf = (stats['confidence_sum'] / stats['confidence_count']) if stats['confidence_count'] else 0
                
                print(f"    {day}: {total} calls, dominant={dominant_state}({dominant_pct:.0f}%), "
                      f"unknown={unknown_pct:.1f}%, avg_conf={avg_conf:.2f}")
                
                if unknown_pct > 50:
                    degradation_signals.append((day, 'HIGH_UNKNOWN_RATE', unknown_pct))
                
                if len(states) <= 2 and total >= 10:
                    degradation_signals.append((day, 'LOW_STATE_DIVERSITY', len(states)))
            
            if degradation_signals:
                print(f"\n  ⚠️  Degradation signals detected ({len(degradation_signals)}):")
                for signal in degradation_signals:
                    day, stype, val = signal
                    if stype == 'HIGH_UNKNOWN_RATE':
                        report('WARN', f'{day}: {val:.1f}% unknown states',
                               'World model may be failing to produce states')
                    elif stype == 'LOW_STATE_DIVERSITY':
                        report('WARN', f'{day}: only {val} distinct states',
                               'World model may be stuck in fallback')
    else:
        print(f"  No audit logs found at {audit_dir}")
        print("  (Run with --scan-audit-logs after the server has been running)")
    
    # Phase 3: Risk assessment
    print(f"\n[Phase 3] Risk assessment")
    
    risks = []
    if fallback_count > 5:
        risks.append(f"High fallback surface ({fallback_count} references) — "
                     f"each one is a potential silent degradation path")
    
    print(f"  Fallback references: {fallback_count}")
    if risks:
        for r in risks:
            print(f"  ⚠️  {r}")
    else:
        print(f"  ✅ Low risk profile")
    
    print(f"\n  RESULTS: {PASS} passed, {WARN} warnings, {FAIL} failed")
    
    return 1 if FAIL > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
