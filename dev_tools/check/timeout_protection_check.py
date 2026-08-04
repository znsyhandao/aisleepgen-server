#!/usr/bin/env python3
"""timeout_protection_check.py — 超时保护完整性检查

OWASP: 所有外部调用必须有超时保护，防止资源耗尽
"""
import os, sys, re, argparse
sys.stdout.reconfigure(encoding='utf-8')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    args = parser.parse_args()
    workdir = args.dir
    
    FOCUS = ['deepseek_proxy.py', 'wx_login.py', 'dp_router.py', 'scheduler_daemon.py']
    
    print('='*60)
    print('  TIMEOUT PROTECTION CHECK')
    print('='*60)
    
    for fname in FOCUS:
        fp = os.path.join(workdir, fname)
        if not os.path.exists(fp): continue
        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        urlopen_no_timeout = len(re.findall(r'urlopen\(', content)) - len(re.findall(r'urlopen\(.*?timeout', content))
        timeout_values = [int(x) for x in re.findall(r'timeout\s*=\s*(\d+)', content)]
        
        status = '✅' if urlopen_no_timeout == 0 and all(t <= 30 for t in timeout_values) else '⚠️'
        print(f'\n  {status} {fname}:')
        print(f'     urlopen calls: {urlopen_no_timeout} without timeout')
        if timeout_values:
            print(f'     timeout values: {sorted(set(timeout_values))}')
    
    print()

if __name__ == '__main__':
    main()
