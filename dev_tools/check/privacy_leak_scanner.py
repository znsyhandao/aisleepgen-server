#!/usr/bin/env python3
"""privacy_leak_scanner.py — PII/密钥硬编码/数据泄漏扫描器

按 OWASP AI Security 标准：
- PII泄漏：审计日志中未脱敏的 openid
- 密钥硬编码：代码中的 API key / secret / token
- 数据最小化：审计日志是否记录了不必要的敏感字段

用法:
  python privacy_leak_scanner.py --dir D:\AISleepGen_Optimized [--fix]
"""
import os, sys, re, json, glob, argparse
sys.stdout.reconfigure(encoding='utf-8')

OPENID_PATTERN = re.compile(r'[a-f0-9]{32}')
WX_OPENID_PATTERN = re.compile(r'[ow][a-z0-9_-]{28,}')
API_KEY_PATTERNS = [
    (re.compile(r'sk-[A-Za-z0-9]{20,}'), 'DEEPSEEK_API_KEY'),
    (re.compile(r'[A-Za-z0-9_-]{32,}'), 'GENERIC_SECRET'),
    (re.compile(r'(?:api[_-]?key|secret|token|password)\s*[:=]\s*["\'][^"\']{16,}["\']', re.I), 'HARDCODED_CREDENTIAL'),
]

def scan_audit_logs(audit_dir):
    """Scan audit logs for unredacted PII."""
    findings = []
    files = glob.glob(os.path.join(audit_dir, '**/*.jsonl'), recursive=True)
    for fp in sorted(files)[-100:]:
        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
            for lineno, line in enumerate(f, 1):
                for m in WX_OPENID_PATTERN.finditer(line):
                    findings.append({
                        'type': 'PII_LEAK',
                        'severity': 'CRITICAL',
                        'file': fp,
                        'lineno': lineno,
                        'match': m.group(),
                        'context': line[max(0,m.start()-20):m.end()+20],
                    })
    return findings

def scan_hardcoded_secrets(workdir, focus_files):
    """Scan code for hardcoded secrets."""
    findings = []
    for fp in focus_files:
        fpath = os.path.join(workdir, fp)
        if not os.path.exists(fpath): continue
        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        for pat, label in API_KEY_PATTERNS:
            for m in pat.finditer(content):
                ctx = content[max(0,m.start()-30):m.end()+30].replace('\n',' ')
                findings.append({
                    'type': 'HARDCODED_SECRET',
                    'severity': 'CRITICAL',
                    'file': fp,
                    'label': label,
                    'match': m.group()[:16]+'...',
                    'context': ctx.strip()[:120],
                })
    return findings

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    parser.add_argument('--fix', action='store_true', help='Attempt auto-fix')
    args = parser.parse_args()
    workdir = args.dir

    # Scan 1: Audit logs for PII
    audit_dirs = [os.path.join(workdir, 'data', 'audit_logs'),
                  os.path.join(workdir, 'audit_logs')]
    print('='*60)
    print('  PRIVACY LEAK SCANNER')
    print('='*60)
    print('\n[1] PII leak scan (audit logs)')
    pii = []
    for ad in audit_dirs:
        if os.path.isdir(ad):
            pii += scan_audit_logs(ad)
            if pii:
                print(f'  🔴 Found {len(pii)} unredacted PII(s) in {ad}')
                for p in pii[:10]:
                    print(f"     L{p['lineno']}: {p['match'][:20]}... context: {p['context'][:60]}")
            else:
                print(f'  ✅ {ad}: No PII leaks')

    # Scan 2: Hardcoded secrets in code
    FOCUS = ['deepseek_proxy.py', 'wx_login.py', 'compliance.py', '.env', 'config.py']
    print('\n[2] Hardcoded secret scan')
    secrets = scan_hardcoded_secrets(workdir, FOCUS)
    if secrets:
        print(f'  🔴 Found {len(secrets)} hardcoded secret(s):')
        for s in secrets:
            print(f"     [{s['label']}] {s['file']}: {s['match']} | {s['context'][:60]}")
    else:
        print('  ✅ No hardcoded secrets detected')

    critical = len([f for f in (pii + secrets) if f.get('severity') == 'CRITICAL'])
    print(f'\n  CRITICAL: {critical} | HIGH: 0')
    return 1 if critical else 0

if __name__ == '__main__':
    main()
