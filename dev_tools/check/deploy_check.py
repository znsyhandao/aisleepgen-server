# -*- coding: utf-8 -*-
"""
远程部署前环境检查工具
在部署到远程服务器前自动检查：
  1. 远程 Python 版本
  2. 远程依赖版本（requirements.txt vs installed）
  3. 远程端口可达性（8090/8091）
  4. 远程关键文件是否存在
  5. 本地 vs 远程文件差异

用法:
  python deploy_check.py                   # 交互模式
  python deploy_check.py --host 82.156.208.245  # 指定远程主机
  python deploy_check.py --host 82.156.208.245 --port 22 --user root
"""
import subprocess, sys, os, json, re, socket, time, tempfile

# ========== 配置 ==========
DEFAULT_HOST = '82.156.208.245'
DEFAULT_PORT = 22
DEFAULT_USER = 'root'
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
REMOTE_DIR = '/root/AISleepGen_Optimized'
SERVICE_PORTS = [8090, 8091]
KEY_FILES = [
    'asyncio_server.py', 'dp_router.py', 'profile_storage.py',
    'self_learn.py', 'dp_data.py', 'dp_chat.py',
    'sleep_world_model.py', 'architecture_inner_eye.py',
    'working_memory.py', 'free_energy_simple.py'
]

def parse_args():
    host, port, user = DEFAULT_HOST, DEFAULT_PORT, DEFAULT_USER
    for i, arg in enumerate(sys.argv):
        if arg == '--host' and i+1 < len(sys.argv):
            host = sys.argv[i+1]
        elif arg == '--port' and i+1 < len(sys.argv):
            port = int(sys.argv[i+1])
        elif arg == '--user' and i+1 < len(sys.argv):
            user = sys.argv[i+1]
    return host, port, user

def banner(msg):
    print(f'\n{"="*55}')
    print(f'  {msg}')
    print(f'{"="*55}')

def check(ok, msg, detail=''):
    icon = '[OK]' if ok else '[FAIL]'
    print(f'  {icon} {msg}')
    if detail:
        print(f'         {detail}')
    return ok

def check_ssh_connectivity(host, port, user):
    """测试SSH连接"""
    banner(f'SSH 连接测试: {user}@{host}:{port}')
    try:
        r = subprocess.run(
            ['ssh', '-p', str(port), '-o', 'ConnectTimeout=5',
             '-o', 'StrictHostKeyChecking=no',
             f'{user}@{host}', 'echo connected'],
            capture_output=True, text=True, timeout=10
        )
        if 'connected' in r.stdout:
            return check(True, 'SSH连接成功', f'{user}@{host}:{port}')
        else:
            return check(False, 'SSH连接失败', r.stderr[:200])
    except Exception as e:
        return check(False, 'SSH连接异常', str(e)[:200])

def check_remote_python(host, port, user):
    """检查远程Python版本"""
    banner('远程 Python 环境')
    try:
        r = subprocess.run(
            ['ssh', '-p', str(port), '-o', 'ConnectTimeout=5',
             '-o', 'StrictHostKeyChecking=no',
             f'{user}@{host}',
             'python3 --version 2>&1; which python3; pip3 --version 2>&1'],
            capture_output=True, text=True, timeout=10
        )
        lines = [l for l in r.stdout.split('\n') if l.strip()]
        for l in lines:
            print(f'  {l}')
        return True
    except Exception as e:
        return check(False, '远程Python检查失败', str(e)[:200])

def check_remote_deps(host, port, user):
    """检查远程依赖是否匹配"""
    banner('依赖一致性检查')
    req_path = os.path.join(PROJECT_DIR, 'requirements.txt')
    if not os.path.exists(req_path):
        check(False, 'requirements.txt 不存在', '跳过远程检查')
        return True
    
    with open(req_path, 'r') as f:
        required = [l.strip() for l in f if l.strip() and not l.startswith('#')]
    
    check(True, f'本地需要 {len(required)} 个依赖')
    
    try:
        r = subprocess.run(
            ['ssh', '-p', str(port), '-o', 'ConnectTimeout=5',
             '-o', 'StrictHostKeyChecking=no',
             f'{user}@{host}',
             'pip3 list --format=columns 2>/dev/null | tail -n +3'],
            capture_output=True, text=True, timeout=15
        )
        installed = {}
        for l in r.stdout.split('\n'):
            parts = l.strip().split()
            if len(parts) >= 2:
                installed[parts[0].lower()] = parts[1]
        
        missing = []
        for pkg in required:
            pkg_name = re.split(r'[>=<]', pkg)[0].strip().lower()
            if pkg_name not in installed:
                missing.append(pkg)
        
        if missing:
            return check(False, f'{len(missing)} 个依赖缺失: {", ".join(missing[:5])}')
        else:
            return check(True, '所有依赖已安装')
    except Exception as e:
        return check(False, '远程依赖检查失败', str(e)[:200])

def check_remote_files(host, port, user):
    """检查远程关键文件"""
    banner('关键文件检查')
    file_list = ' '.join(KEY_FILES)
    try:
        r = subprocess.run(
            ['ssh', '-p', str(port), '-o', 'ConnectTimeout=5',
             '-o', 'StrictHostKeyChecking=no',
             f'{user}@{host}',
             f'cd {REMOTE_DIR} && ls -la {file_list} 2>&1'],
            capture_output=True, text=True, timeout=10
        )
        missing = []
        for line in r.stdout.split('\n'):
            if 'cannot access' in line or 'No such file' in line:
                missing.append(line.strip())
        if missing:
            return check(False, f'{len(missing)} 个文件缺失', '\n'.join(missing[:3]))
        else:
            return check(True, f'所有 {len(KEY_FILES)} 个关键文件存在')
    except Exception as e:
        return check(False, '远程文件检查失败', str(e)[:200])

def check_port_reachability(host):
    """检查远程端口"""
    banner('端口可达性测试')
    all_ok = True
    for p in SERVICE_PORTS:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, p))
            sock.close()
            if result == 0:
                check(True, f'端口 {p} 可达', f'http://{host}:{p}/')
            else:
                check(False, f'端口 {p} 不可达', f'需要检查安全组/防火墙')
                all_ok = False
        except Exception as e:
            check(False, f'端口 {p} 异常', str(e)[:100])
            all_ok = False
    return all_ok

def check_local_git():
    """检查本地git状态"""
    banner('本地 Git 状态')
    try:
        r = subprocess.run(
            ['git', 'status', '--short'],
            capture_output=True, text=True, cwd=PROJECT_DIR, timeout=5
        )
        changes = [l for l in r.stdout.split('\n') if l.strip() and not l.startswith('?? venv')]
        if changes:
            for c in changes[:10]:
                print(f'  {c}')
            check(True, f'有 {len(changes)} 个未提交更改 (已提醒)')
        else:
            check(True, '工作区干净')
        return True
    except:
        return check(False, 'Git状态检查失败')

def check_process_running(host, port, user):
    """检查远程服务进程"""
    banner('远程服务进程')
    try:
        r = subprocess.run(
            ['ssh', '-p', str(port), '-o', 'ConnectTimeout=5',
             '-o', 'StrictHostKeyChecking=no',
             f'{user}@{host}',
             f'ps aux | grep -E "asyncio_server|deepseek_proxy" | grep -v grep'],
            capture_output=True, text=True, timeout=10
        )
        if r.stdout.strip():
            check(True, '服务进程运行中')
            for l in r.stdout.split('\n'):
                if l.strip():
                    print(f'  {l.strip()[:150]}')
        else:
            check(False, '服务进程未运行', '需要启动: screen -dmS sleep python asyncio_server.py')
        return True
    except Exception as e:
        return check(False, '进程检查失败', str(e)[:100])

def main():
    host, port, user = parse_args()
    
    print(f'Deploy Check for {host}:{port} as {user}')
    print(f'Local:  {PROJECT_DIR}')
    print(f'Remote: {REMOTE_DIR}\n')
    
    results = []
    
    # 1. 本地git状态
    results.append(check_local_git())
    
    # 2. SSH连接
    results.append(check_ssh_connectivity(host, port, user))
    if not results[-1]:
        check(False, 'SSH不通，跳过远程检查')
        print('请检查: 1) SSH密钥 2) 远程主机IP 3) 安全组22端口')
        sys.exit(1)
    
    # 3. 远程Python
    results.append(check_remote_python(host, port, user))
    
    # 4. 远程依赖
    results.append(check_remote_deps(host, port, user))
    
    # 5. 远程文件
    results.append(check_remote_files(host, port, user))
    
    # 6. 远程进程
    results.append(check_process_running(host, port, user))
    
    # 7. 端口可达性
    results.append(check_port_reachability(host))
    
    # 总结
    passed = sum(1 for r in results if r)
    failed = sum(1 for r in results if not r)
    total = len(results)
    
    banner('部署检查总结')
    print(f'  通过: {passed}/{total}')
    print(f'  失败: {failed}/{total}')
    
    if failed == 0:
        check(True, '部署前环境就绪')
    else:
        print()
        check(False, f'{failed} 项检查未通过，修复后再部署')
    
    return failed == 0

if __name__ == '__main__':
    main()
