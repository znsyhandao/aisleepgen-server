#!/usr/bin/env python3
"""hardcoded_secret_scanner.py — 密钥硬编码深度扫描

OWASP Top 10 for LLM Applications: 
- 敏感信息暴露（API key/secret/token 硬编码在代码中）
- 不在 .env 而在代码中的凭据
- 密钥轮换合规性

用法:
  python hardcoded_secret_scanner.py --dir D:\AISleepGen_Optimized [--fix]
"""
import os, re, sys, argparse
sys.stdout.reconfigure(encoding='utf-8')

SECRET_PATTERNS = [
    (re.compile(r'(?:api[_-]?key|apikey)\s*[:=]\s*["\']([^"\']{16,})["\']', re.I), 'API_KEY'),
    (re.compile(r'(?:secret|SECRET)\s*[:=]\s*["\']([^"\']{16,})["\']'), 'SECRET'),
    (re.compile(r'(?:token|TOKEN)\s*[:=]\s*["\']([^"\']{16,})["\']'), 'TOKEN'),
    (re.compile(r'(?:password|PASSWORD)\s*[:=]\s*["\']([^"\']{8,})["\']'), 'PASSWORD'),
    (re.compile(r'sk-[A-Za-z0-9]{20,}'), 'SK_KEY'),
    (re.compile(r'(?:private_key|PRIVATE_KEY)\s*[:=]\s*["\']'), 'PRIVATE_KEY'),
    (re.compile(r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----'), 'PEM_KEY'),
]

ENV_KEY_PATTERN = re.compile(r'["\']([A-Z][A-Z_]{5,})["\']')

def scan_file_for_secrets(filepath):
    """Scan a single file for hardcoded secrets."""
    findings = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception:
        return findings
    
    for pat, label in SECRET_PATTERNS:
        for m in pat.finditer(content):
            ctx_start = max(0, m.start()-20)
            ctx_end = min(len(content), m.end()+20)
            findings.append({
                'type': label,
                'file': os.path.basename(filepath),
                'lineno': content[:m.start()].count('\n') + 1,
                'match': m.group()[:20]+'...',
                'context': content[ctx_start:ctx_end].replace('\n',' ')[:100],
            })
    return findings

def scan_env_references(filepath):
    """Find environment variable references in code."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    return ENV_KEY_PATTERN.findall(content)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    parser.add_argument('--fix', action='store_true')
    args = parser.parse_args()
    workdir = args.dir
    
    FOCUS = ['deepseek_proxy.py', 'wx_login.py', 'compliance.py', 'config.py',
             'dp_router.py', 'audit_logger.py', 'scheduler_daemon.py']
    
    print('='*60)
    print('  HARDCODED SECRET SCANNER')
    print('='*60)
    
    all_secrets = []
    for fname in FOCUS:
        fp = os.path.join(workdir, fname)
        if not os.path.exists(fp): continue
        secrets = scan_file_for_secrets(fp)
        if secrets:
            all_secrets.extend(secrets)
            print(f'\n  {fname}: {len(secrets)} secret(s)')
            for s in secrets:
                print(f"    [{s['type']}] L{s['lineno']}: {s['match']} | {s['context'][:60]}")
    
    # Check .env key references vs definitions
    print('\n[Env key reference check]')
    dotenv = os.path.join(workdir, '.env')
    env_keys = set()
    if os.path.exists(dotenv):
        with open(dotenv) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    env_keys.add(line.split('=')[0].strip())
    
    code_keys = set()
    for fname in FOCUS:
        fp = os.path.join(workdir, fname)
        if os.path.exists(fp):
            code_keys.update(scan_env_references(fp))
    
    missing = {k for k in code_keys if k not in env_keys and 'KEY' in k.upper()}
    if missing:
        print(f'  ⚠️  {len(missing)} env key(s) referenced but not in .env:')
        for k in sorted(missing):
            print(f'     {k}')
    else:
        print('  ✅ All env keys accounted for')
    
    print(f'\n  Total secrets found: {len(all_secrets)}')
    return 1 if all_secrets else 0

if __name__ == '__main__':
    main()
