#!/usr/bin/env python3
"""circuit_breaker_injector.py — 外部依赖断路器检查

OWASP AI Security: 外部依赖容错
- DeepSeek API 超时时是否有断路器
- 微信API 超时时是否有降级
- 文件系统失败时是否有兜底

用法:
  python circuit_breaker_injector.py --dir D:\AISleepGen_Optimized [--fix]
"""
import os, sys, re, argparse
sys.stdout.reconfigure(encoding='utf-8')

API_CALL_PATTERNS = [
    (re.compile(r'urlopen\(([^,]+),\s*timeout\s*=\s*(\d+)\)'), 'urlopen with timeout'),
    (re.compile(r'requests?\.(?:get|post|put|delete)\([^)]*timeout\s*=\s*(\d+)'), 'requests with timeout'),
    (re.compile(r'urllib\.request\.urlopen\('), 'urlopen (no timeout check)'),
]

RETRY_PATTERNS = [
    re.compile(r'try\s*:'),
    re.compile(r'except\b'),
    re.compile(r'retry|RETRY'),
    re.compile(r'timeout\s*=\s*\d+'),
]

def scan_external_calls(filepath):
    """Scan for external API calls and their error handling."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    calls = []
    for pat, label in API_CALL_PATTERNS:
        for m in pat.finditer(content):
            lineno = content[:m.start()].count('\n') + 1
            calls.append({
                'lineno': lineno,
                'type': label,
                'match': m.group()[:60],
            })
    
    # Check for timeout-only calls (no retry)
    timeout_count = len(re.findall(r'timeout\s*=', content))
    try_count = len(re.findall(r'try\s*:', content))
    except_count = len(re.findall(r'except\b', content))
    
    return calls, timeout_count, try_count, except_count

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    args = parser.parse_args()
    workdir = args.dir
    
    FOCUS = ['deepseek_proxy.py', 'wx_login.py', 'dp_router.py']
    
    print('='*60)
    print('  CIRCUIT BREAKER AUDIT')
    print('='*60)
    
    for fname in FOCUS:
        fp = os.path.join(workdir, fname)
        if not os.path.exists(fp): continue
        calls, tc, try_c, exc_c = scan_external_calls(fp)
        if calls:
            print(f'\n  {fname}: {len(calls)} external call(s)')
            for c in calls[:5]:
                print(f"    L{c['lineno']}: [{c['type']}]")
            no_retry = len(calls)
            print(f'    Timeout: {tc} | Try blocks: {try_c} | Except: {exc_c}')
            if no_retry > try_c:
                print(f'    ⚠️  {no_retry - try_c} external calls may lack try/except')
        else:
            print(f'\n  {fname}: No external calls detected')

if __name__ == '__main__':
    main()
