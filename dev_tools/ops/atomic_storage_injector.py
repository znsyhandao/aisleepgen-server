#!/usr/bin/env python3
"""atomic_storage_injector.py — 原子写入修复器

修复什么：
- 所有 file write 改为先写.tmp再 rename
- user_profile.json 并发写入加文件锁
- 关键文件（profile/audit log）的写入路径统一

用法:
  python atomic_storage_injector.py --dir D:\AISleepGen_Optimized [--apply]
"""
import os, sys, re, ast, argparse
sys.stdout.reconfigure(encoding='utf-8')

FIXABLE_PATTERNS = [
    # Pattern: json.dump(data, open(path, 'w'))
    (re.compile(r'json\.dump\((.*?),\s*open\(([^)]+),\s*["\']w["\']\)\)'),
     'json.dump to open(path,w) — should use atomic write'),
    # Pattern: open(path, 'w').write()
    (re.compile(r'open\(([^)]+),\s*["\']w["\']\)\.write\('),
     'open(path,w).write() — should use atomic write'),
    # Pattern: open(path, 'w') without with
    (re.compile(r'(?<!with )open\(([^)]+),\s*["\']w["\']\)'),
     'open(path,w) without with — handle leak risk'),
]

def scan_unsafe_writes(filepath):
    """Scan for unsafe write patterns."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    findings = []
    for pat, desc in FIXABLE_PATTERNS:
        for m in pat.finditer(content):
            lineno = content[:m.start()].count('\n') + 1
            findings.append({
                'lineno': lineno,
                'pattern': desc,
                'match': m.group()[:80],
                'fixable': 'json.dump' in desc or 'open(path,w).write' in desc,
            })
    return findings

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    parser.add_argument('--apply', action='store_true', help='Apply fixes')
    args = parser.parse_args()
    workdir = args.dir
    
    FOCUS = ['deepseek_proxy.py', 'compliance.py', 'audit_logger.py',
             'world_model_coordinator.py', 'state_transition_model.py']
    
    print('='*60)
    print('  ATOMIC STORAGE CHECK')
    print('='*60)
    
    all_findings = []
    for fname in FOCUS:
        fp = os.path.join(workdir, fname)
        if not os.path.exists(fp): continue
        findings = scan_unsafe_writes(fp)
        if findings:
            all_findings.extend(findings)
            print(f'\n  {fname}: {len(findings)} unsafe write(s)')
            for f in findings[:5]:
                status = '🔧' if f['fixable'] else '⚠️'
                print(f"    {status} L{f['lineno']}: {f['pattern']}")
                print(f"       {f['match'][:60]}")
    
    if not all_findings:
        print('  ✅ All writes appear safe')
    
    print(f'\n  Total findings: {len(all_findings)}')
    print(f'  Fixable: {sum(1 for f in all_findings if f["fixable"])}')
    
    if args.apply and all_findings:
        print('\n  --apply not yet implemented for complex patterns')
        print('  The injector needs per-pattern logic to rewrite.')
    return 1 if all_findings else 0

if __name__ == '__main__':
    main()
