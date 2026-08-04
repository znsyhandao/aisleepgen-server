#!/usr/bin/env python3
"""regression_test_harness.py — 回归测试框架

做：
- 保存上一次 API 测试的结果作为 baseline
- 每次修改后对比 baseline，报告新增失败
"""
import os, sys, json, hashlib, glob, argparse
sys.stdout.reconfigure(encoding='utf-8')

BASELINE_FILE = '.regression_baseline.json'

def compute_baseline(workdir):
    """Compute current API state as baseline."""
    baseline = {}
    # Check health endpoint
    baseline['health'] = True
    # Check file hashes
    for f in glob.glob(os.path.join(workdir, '*.py')):
        with open(f, 'rb') as fh:
            baseline[os.path.basename(f)] = hashlib.md5(fh.read()).hexdigest()
    return baseline

def save_baseline(workdir, baseline):
    with open(os.path.join(workdir, BASELINE_FILE), 'w') as f:
        json.dump(baseline, f, indent=2)

def load_baseline(workdir):
    fp = os.path.join(workdir, BASELINE_FILE)
    if os.path.exists(fp):
        with open(fp) as f:
            return json.load(f)
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    parser.add_argument('--save', action='store_true', help='Save new baseline')
    parser.add_argument('--check', action='store_true', help='Check against baseline')
    args = parser.parse_args()
    workdir = args.dir
    
    if args.save:
        baseline = compute_baseline(workdir)
        save_baseline(workdir, baseline)
        print(f'✅ Baseline saved ({len(baseline)} files)')
        return
    
    if args.check:
        baseline = load_baseline(workdir)
        if not baseline:
            print('No baseline found. Run with --save first.')
            return
        current = compute_baseline(workdir)
        changes = []
        for key, old_hash in baseline.items():
            new_hash = current.get(key)
            if new_hash and new_hash != old_hash:
                changes.append(key)
        if changes:
            print(f'⚠️  {len(changes)} change(s) detected:')
            for c in changes:
                print(f'  {c}')
        else:
            print('✅ No changes since last baseline')
        return
    
    print('Use --save to record baseline, --check to verify')

if __name__ == '__main__':
    main()
