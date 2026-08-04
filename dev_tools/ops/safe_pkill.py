# -*- coding: utf-8 -*-
"""
safe_pkill.py — 精确杀进程工具
防止 pkill -9 -f python 误杀 jupyter/AISleepGen/其他服务

用法:
    python safe_pkill.py deepseek_proxy          # 杀匹配 deepseek_proxy 的进程
    python safe_pkill.py ai_furnace              # 杀匹配 ai_furnace 的进程
    python safe_pkill.py --dry-run python        # 预览不杀
    python safe_pkill.py --help                  # 显示帮助

安全规则:
    1. 永不执行 'pkill -9 -f python'（无差别杀）
    2. 只杀明确匹配模式（grep -F 精确匹配）
    3. --dry-run 默认先预览
    4. 杀进程前先打印匹配列表，要求二次确认
"""
import subprocess, sys, os, platform

def get_processes(pattern):
    """获取匹配的进程信息"""
    if platform.system() == 'Windows':
        cmd = f'wmic path win32_process where "name like \'%python%\'" get ProcessId,Commandline /format:csv'
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            results = []
            for line in r.stdout.split('\n'):
                if pattern.lower() in line.lower():
                    parts = line.strip().split(',')
                    if len(parts) >= 2:
                        pid = parts[-1].strip()
                        cmdline = ','.join(parts[1:-1]).strip()
                        if pid.isdigit():
                            results.append((int(pid), cmdline))
            return results
        except Exception as e:
            print(f'[safe_pkill] 获取进程列表失败: {e}')
            return []
    else:
        cmd = ['ps', 'aux']
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        results = []
        for line in r.stdout.split('\n'):
            if pattern.lower() in line.lower() and 'safe_pkill' not in line:
                parts = line.split()
                if len(parts) >= 11:
                    pid = parts[1]
                    if pid.isdigit():
                        results.append((int(pid), line.strip()))
        return results

def kill_processes(pid_list, pattern, dry_run=False):
    """杀进程"""
    if not pid_list:
        print(f'[safe_pkill] 未找到匹配 "{pattern}" 的进程')
        return True

    print(f'[safe_pkill] 将终止以下 {len(pid_list)} 个进程:')
    for pid, cmdline in pid_list:
        print(f'  PID {pid}: {cmdline[:120]}')

    if dry_run:
        print(f'[safe_pkill] --dry-run 模式，不执行杀进程')
        return True

    confirm = input(f'[safe_pkill] 确认杀这 {len(pid_list)} 个进程? (yes/no): ')
    if confirm.lower() not in ('yes', 'y'):
        print('[safe_pkill] 已取消')
        return False

    success = 0
    for pid, _ in pid_list:
        try:
            if platform.system() == 'Windows':
                subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                             capture_output=True, timeout=5)
            else:
                subprocess.run(['kill', '-9', str(pid)],
                             capture_output=True, timeout=5)
            success += 1
        except Exception as e:
            print(f'[safe_pkill] 杀 PID {pid} 失败: {e}')

    print(f'[safe_pkill] 成功终止 {success}/{len(pid_list)} 个进程')
    return True

if __name__ == '__main__':
    if '--help' in sys.argv or len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    pattern = None
    dry_run = False
    for arg in sys.argv[1:]:
        if arg == '--dry-run':
            dry_run = True
        elif arg == 'python':
            print('[safe_pkill] [FAIL] 禁止无差别杀所有 python 进程！请指定具体模式')
            print('   例如: python safe_pkill.py deepseek_proxy')
            sys.exit(1)
        else:
            pattern = arg

    if not pattern:
        print('[safe_pkill] 请指定进程模式')
        sys.exit(1)

    processes = get_processes(pattern)
    kill_processes(processes, pattern, dry_run=dry_run)
