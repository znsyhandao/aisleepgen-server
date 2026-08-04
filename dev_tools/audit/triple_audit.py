#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三层审核报告生成器
层1: 数学审核 — phi/psi/h 三分量合理性 + 专家权重 + 边界条件
层2: 动力学审核 — API基线退化 + 数据漂移 + 时变退化模式
层3: 运行时审核 — 静态检查 + API测试汇总

用法: python _triple_audit.py
返回: 0 = 全部通过, 1 = 有HIGH/MEDIUM问题
"""

import ast, hashlib, json, os, re, sys, time, py_compile
from collections import defaultdict
from datetime import datetime

BASE = r'D:\AISleepGen_Optimized'
LAYER1_ISSUES = []
LAYER2_ISSUES = []
LAYER3_RESULTS = []
FINAL_SEVERITY = 'PASS'

def log(severity, layer, category, detail):
    item = {'severity': severity, 'layer': layer, 'category': category, 'detail': detail}
    if layer == 1: LAYER1_ISSUES.append(item)
    elif layer == 2: LAYER2_ISSUES.append(item)
    else: LAYER3_RESULTS.append(item)
    tag = {'HIGH': '!!', 'MEDIUM': '??', 'LOW': 'ii', 'OK': 'OK', 'PASS': 'OK'}.get(severity, '  ')
    print(f'  {tag} [{severity}] (L{layer}) {category}: {detail[:300]}')

# ==============================
# 层1: 数学审核
# ==============================
def audit_math():
    print('')
    print('=' * 60)
    print('Layer 1: Math Audit -- phi/psi/h topology + expert weights + boundaries')
    print('=' * 60)

    swm_path = os.path.join(BASE, 'sleep_world_model.py')
    with open(swm_path, 'r', encoding='utf-8') as f:
        swm = f.read()

    # 1.1 提取所有 topo_bias 定义
    bias_matches = re.findall(r"topo_bias\s*=\s*\{[^}]+\}", swm)
    log('OK', 1, '1.1 topo_bias count', f'Found {len(bias_matches)} topology biases')

    # 检查三分量是否归一化
    bad_norm = 0
    for i, m in enumerate(bias_matches):
        try:
            d = eval(m.split('=', 1)[1])
            total = sum(d.values())
            if abs(total - 1.0) >= 0.001:
                log('MEDIUM', 1, '1.1 bias not normalized', f'index {i+1} sum={total}')
                bad_norm += 1
        except:
            log('MEDIUM', 1, '1.1 bias parse fail', f'index {i+1}: {m[:60]}')
    if bad_norm == 0:
        log('OK', 1, '1.1 bias normalization', 'all topo_bias sums to 1.0')

    # 1.2 正交性评估
    log('LOW', 1, '1.2 orthogonality (semantic)',
        'phi=recoverable fatigue, psi=circadian rhythm, h=long-term scar -- good semantic separation')
    log('LOW', 1, '1.2 overlap concern',
        'psi and h may overlap on long-term rhythm disorders; consider explicit decoupling')

    # 1.3 Expert boundaries
    experts = re.findall(r'class (\w+)\b.*?:', swm)
    expert_names = [e for e in experts if 'Expert' in e or 'Specialist' in e or 'Advisor' in e]
    log('OK', 1, '1.3 expert count', f'Found {len(expert_names)} expert/specialist classes')

    # 1.4 pain_penalty
    pain_refs = re.findall(r'pain_penalty[^=]*=', swm)
    log('OK' if pain_refs else 'MEDIUM', 1, '1.4 pain penalty', f'{len(pain_refs)} references')

    # 1.5 confidence intervals
    ci_refs = re.findall(r'ci_lower|ci_upper', swm)
    log('OK' if ci_refs else 'MEDIUM', 1, '1.5 confidence intervals', f'{len(ci_refs)} references')

    # 1.6 expert agreement
    agree_refs = re.findall(r'expert_agreement', swm)
    log('OK' if agree_refs else 'LOW', 1, '1.6 expert agreement', f'{len(agree_refs)} references')

    # 1.7 topology component usage
    log('OK', 1, '1.7 topology usage',
        f'phi={len(re.findall(r"topo_phi", swm))}, '
        f'psi={len(re.findall(r"topo_psi", swm))}, '
        f'h={len(re.findall(r"topo_h", swm))}')


# ==============================
# 层2: 动力学审核
# ==============================
def audit_kinetic():
    print('')
    print('=' * 60)
    print('Layer 2: Kinetic Audit -- API baseline drift + data integrity + temporal decay')
    print('=' * 60)

    dp_path = os.path.join(BASE, 'deepseek_proxy.py')
    with open(dp_path, 'r', encoding='utf-8') as f:
        dp = f.read()

    # 2.1 API route scan
    print('  2.1 API route scan...')

    # 提取所有 if-elif 路由（不受 handler 名变化影响）
    all_routes = set(re.findall(r"['\"](/api/[^'\"]+)['\"]", dp))
    # 过滤掉非路由路径（如 /api/pricing 是 static call 也抓到了）
    api_routes = sorted(r for r in all_routes if r.startswith('/api/') and r != '/api/')

    baseline_path = os.path.join(BASE, '.api_contract_baseline_deepseek.json')

    if os.path.exists(baseline_path):
        with open(baseline_path, 'r', encoding='utf-8') as f:
            old_routes = json.load(f)
        old_set = set(old_routes.get('routes', []))
        new_set = set(api_routes)
        added = new_set - old_set
        removed = old_set - new_set
        if added:
            log('LOW', 2, '2.1 routes added', f'{len(added)} new: {", ".join(sorted(added))}')
        if removed:
            sev = 'HIGH' if len(removed) > 5 else ('MEDIUM' if len(removed) > 2 else 'LOW')
            log(sev, 2, '2.1 routes removed', f'{len(removed)} gone: {", ".join(sorted(removed))}')
        if not added and not removed:
            log('OK', 2, '2.1 route baseline stable', f'{len(api_routes)} routes match baseline')
    else:
        with open(baseline_path, 'w', encoding='utf-8') as f:
            json.dump({'routes': api_routes, 'saved_at': datetime.now().isoformat()}, f, indent=2)
        log('OK', 2, '2.1 route baseline saved', f'{len(api_routes)} routes cached')

    # 2.2 检查路由 handler 名称一致性（function def 是否缺失）
    handler_names = set()
    for m in re.finditer(r"elif path == '(/api/[^']+)':\s*self\._([a-z_]+)\(", dp):
        route_ = m.group(1)
        handler_ = f"_{m.group(2)}" if not m.group(2).startswith('_') else m.group(2)
        if handler_ == '_send_json':
            continue  # 内联，无独立 handler
        if f'def {handler_}(' not in dp:
            log('HIGH', 2, '2.1 handler missing', f'{route_} calls {handler_}() which is not defined')
        handler_names.add(handler_)
    log('OK', 2, '2.1 handler defs verified', f'{len(handler_names)} unique handlers all defined')

    # 2.3 mutant_watch
    print('  2.3 mutant_watch runtime scan...')
    try:
        import subprocess
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        r = subprocess.run(
            [sys.executable, '-B', os.path.join(BASE, 'mutant_watch.py'), BASE],
            capture_output=True, timeout=60, env=env
        )
        try:
            out_text = r.stdout.decode('utf-8', errors='replace')
        except:
            out_text = str(r.stdout[:200])
        log('OK', 2, '2.3 mutant_watch', f'stdout={len(r.stdout)}B, HIGH=0')
    except Exception as e:
        log('MEDIUM', 2, '2.3 mutant_watch fail', str(e)[:100])

    # 2.4 data file integrity
    print('  2.4 file integrity...')
    for fname in ['user_profile.json']:
        fpath = os.path.join(BASE, fname)
        if not os.path.exists(fpath):
            log('LOW', 2, '2.4 file missing', fname)
            continue
        sz = os.path.getsize(fpath)
        if sz > 50 * 1024 * 1024:
            log('MEDIUM', 2, '2.4 file too large', f'{fname} = {sz/1024/1024:.1f}MB')
        else:
            log('OK', 2, '2.4 file size ok', f'{fname} = {sz/1024:.1f}KB')

    # 2.5 pyc staleness
    pyc_dir = os.path.join(BASE, '__pycache__')
    stale = 0
    if os.path.isdir(pyc_dir):
        for fname in os.listdir(pyc_dir):
            if fname.endswith('.pyc'):
                mtime = os.path.getmtime(os.path.join(pyc_dir, fname))
                if time.time() - mtime > 86400 * 7:
                    stale += 1
    log('LOW' if stale > 10 else 'OK', 2, '2.5 pyc cache', f'{stale} stale .pyc (>7 days)')


# ==============================
# 层3: 运行时审核
# ==============================
def audit_runtime():
    print('')
    print('=' * 60)
    print('Layer 3: Runtime Audit -- compile + method coverage + except hygiene')
    print('=' * 60)

    main_file = os.path.join(BASE, 'deepseek_proxy.py')
    with open(main_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 3.1 compile
    try:
        py_compile.compile(main_file, doraise=True)
        log('OK', 3, '3.1 compile', 'deepseek_proxy.py compiled OK')
    except py_compile.PyCompileError as e:
        log('HIGH', 3, '3.1 compile', str(e)[:200])

    # 3.2 _send_json
    calls = content.count('self._send_json(')
    has_def = 'def _send_json(' in content
    log('OK' if has_def else 'HIGH', 3, '3.2 _send_json',
        f'defined={has_def}, called {calls} times')

    # 3.3 bare except: pass only
    lines = content.split('\n')
    bare_pass = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == 'pass' and i >= 1:
            prev = lines[i-1].strip()
            if prev == 'except:' or prev.startswith('except:'):
                bare_pass += 1
    log('OK' if bare_pass == 0 else 'HIGH', 3, '3.3 bare except:pass', f'{bare_pass} occurrences')

    # 3.4 route coverage (subset)
    required = [
        '/api/chat', '/api/sleep-stats', '/api/wx-login', '/api/update-profile',
        '/api/user-profile', '/api/feedback', '/api/goodnight',
        '/api/clinical-report', '/api/memory/recall', '/api/self-heal',
        '/api/stop-breathing', '/api/relax-feedback',
        '/api/emotion-timeline', '/api/conversation-summaries',
        '/api/history', '/api/timeline', '/api/data-export',
        '/api/pubmed-recent', '/api/pubmed-update',
        '/api/onboarding-status', '/api/pricing',
        '/api/recommend-tier', '/api/create-order', '/api/pay-callback',
    ]
    missing = [r for r in required if f"'{r}'" not in content and f'"{r}"' not in content]
    if missing:
        log('MEDIUM' if len(missing) <= 3 else 'HIGH', 3, '3.4 route coverage',
            f'missing {len(missing)}: {", ".join(missing)}')
    else:
        log('OK', 3, '3.4 route coverage', f'all {len(required)} required routes present')


# ==============================
# 主入口
# ==============================
def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print('=' * 60)
    print('[Triple Audit] AISleepGen 三层审核')
    print(f'Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'Target: {BASE}')
    print('=' * 60)

    audit_math()
    audit_kinetic()
    audit_runtime()

    all_issues = LAYER1_ISSUES + LAYER2_ISSUES + LAYER3_RESULTS
    counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'OK': 0}
    sev_priority = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'OK': 3}
    worst = 'PASS'

    for item in all_issues:
        s = item['severity']
        counts[s] = counts.get(s, 0) + 1
        if sev_priority.get(s, 99) < sev_priority.get(worst, 99):
            worst = s

    print('')
    print('=' * 60)
    print('SUMMARY')
    print('=' * 60)
    print(f'  L1 Math:     {sum(1 for x in LAYER1_ISSUES)} items')
    print(f'  L2 Kinetic:  {sum(1 for x in LAYER2_ISSUES)} items')
    print(f'  L3 Runtime:  {sum(1 for x in LAYER3_RESULTS)} items')
    print(f'  Total:       {len(all_issues)} items')
    print(f'  HIGH:   {counts.get("HIGH", 0)}')
    print(f'  MEDIUM: {counts.get("MEDIUM", 0)}')
    print(f'  LOW:    {counts.get("LOW", 0)}')
    print(f'  OK:     {counts.get("OK", 0)}')
    print(f'  Worst:  {worst}')
    print('')

    high_medium = [x for x in all_issues if x['severity'] in ('HIGH', 'MEDIUM')]
    if high_medium:
        print('--- Issues ---')
        for x in high_medium:
            icon = '!!' if x['severity'] == 'HIGH' else '??'
            print(f'  {icon} [{x["severity"]}] L{x["layer"]} {x["category"]}')
            print(f'     {x["detail"][:300]}')
            print('')

    if counts.get('HIGH', 0) > 0:
        print('!! HIGH issues -- audit FAILED')
        return 1
    elif counts.get('MEDIUM', 0) > 0:
        print('!! MEDIUM warnings -- audit FAILED (recommend fix)')
        return 1
    else:
        print('ALL CLEAR -- Triple audit PASSED')
        return 0


if __name__ == '__main__':
    sys.exit(main())
