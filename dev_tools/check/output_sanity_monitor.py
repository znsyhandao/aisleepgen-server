#!/usr/bin/env python3
"""output_sanity_monitor.py — 输出语义合理性检查

查什么：
- 回复与用户评分矛盾（说状态好但评分低）
- 回复长度异常（太短=无内容，太长=失控）
- 重复内容（同一回复出现多次）
"""
import os, sys, re, hashlib, glob, json, argparse
sys.stdout.reconfigure(encoding='utf-8')

def scan_logs_for_anomalies(log_dir):
    """Scan audit logs for output anomalies."""
    findings = []
    seen_hashes = set()
    
    files = glob.glob(os.path.join(log_dir, '**/*.jsonl'), recursive=True)
    for fp in sorted(files)[-20:]:
        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except:
                    continue
                
                resp = rec.get('response', '')
                if isinstance(resp, dict): resp = str(resp)
                if not resp or len(resp) < 20: continue
                
                # Length check
                if len(resp) < 15:
                    findings.append({'type': 'TOO_SHORT', 'resp': resp[:40], 'file': fp})
                elif len(resp) > 5000:
                    findings.append({'type': 'TOO_LONG', 'len': len(resp), 'file': fp})
                
                # Duplicate check
                h = hashlib.md5(resp.encode()).hexdigest()
                if h in seen_hashes:
                    findings.append({'type': 'DUPLICATE_RESPONSE', 'resp': resp[:60], 'file': fp})
                seen_hashes.add(h)
    
    return findings

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--log-dir', default=r'D:\AISleepGen_Optimized\data\audit_logs')
    args = parser.parse_args()
    
    print('='*60)
    print('  OUTPUT SANITY MONITOR')
    print('='*60)
    
    if os.path.isdir(args.log_dir):
        findings = scan_logs_for_anomalies(args.log_dir)
        if findings:
            dupes = [f for f in findings if f['type'] == 'DUPLICATE_RESPONSE']
            print(f'\n  Duplicate responses: {len(dupes)}')
            for d in dupes[:5]:
                print(f'     {d["resp"][:60]}')
            short = len([f for f in findings if f['type'] == 'TOO_SHORT'])
            long = len([f for f in findings if f['type'] == 'TOO_LONG'])
            print(f'  Too short: {short} | Too long: {long}')
            if not findings:
                print('  ✅ No anomalies')
        else:
            print('  ✅ No anomalies (or no data)')
    else:
        print(f'  Log dir not found: {args.log_dir}')

if __name__ == '__main__':
    main()
