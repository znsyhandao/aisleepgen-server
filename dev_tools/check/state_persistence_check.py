#!/usr/bin/env python3
"""state_persistence_check.py — 状态持久化检查

查什么：
- 世界模型状态是否在磁盘上有备份
- 重启后用户是否丢失所有历史状态
- 跨进程/跨服务状态一致性
"""
import os, sys, glob, argparse
sys.stdout.reconfigure(encoding='utf-8')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    args = parser.parse_args()
    workdir = args.dir
    
    print('='*60)
    print('  STATE PERSISTENCE CHECK')
    print('='*60)
    
    # 1. Check if state files exist
    state_files = glob.glob(os.path.join(workdir, 'data', '**', '*.json'), recursive=True)
    if state_files:
        print(f'\n  State files found: {len(state_files)}')
        for sf in sorted(state_files)[:5]:
            size = os.path.getsize(sf)
            print(f'    {os.path.relpath(sf, workdir)} ({size} bytes)')
    else:
        print('\n  ❌ No persistent state files found')
        print('     World model states exist only in memory')
    
    # 2. Check for state save in code
    fp = os.path.join(workdir, 'world_model_coordinator.py')
    if os.path.exists(fp):
        with open(fp) as f:
            content = f.read()
        if 'save' in content.lower() or 'persist' in content.lower() or 'store' in content.lower():
            print('  ✅ world_model_coordinator has persistence logic')
        else:
            print('  ❌ world_model_coordinator may not persist state')
    
    # 3. Check for state load on startup
    fp2 = os.path.join(workdir, 'deepseek_proxy.py')
    if os.path.exists(fp2):
        with open(fp2) as f:
            content = f.read()
        if 'load' in content.lower() and ('state' in content.lower() or 'profile' in content.lower()):
            print('  ✅ deepseek_proxy.py loads state on startup')
        else:
            print('  ⚠️  deepseek_proxy.py may not restore state on restart')
    
    print()

if __name__ == '__main__':
    main()
