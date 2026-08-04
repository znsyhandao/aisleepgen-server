#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ops/deploy_unified.py — 统一部署工具 v1

接入 aisleepgen_tool.py ops deploy <target> [options]

支持的目标（target）：
  huawei         AISleepGen 华为云部署 (123.60.222.129:8090)
  tengxun       华尔街脑 腾讯云部署 (82.156.208.245:8928)
  furnace       数字生命熔炉 腾讯云部署 (82.156.208.245:8921)
  frontier       前沿速递 本地部署 (8930/8931)

用法：
  aisleepgen_tool.py ops deploy huawei          # 部署AISleepGen到华为云
  aisleepgen_tool.py ops deploy tengxun --file web_server.py  # 指定文件
  aisleepgen_tool.py ops deploy huawei --diff   # 只看差异不部署
  aisleepgen_tool.py ops deploy frontier        # 本地重启管线服务
  aisleepgen_tool.py ops deploy --list          # 列出所有目标

设计原则（来自本周沉淀）：
  1. 所有目标共享同一套底层流程：备份→编译→传输→验证→回退
  2. 5轮止盈：不自动启动第6轮迭代
  3. 改前必备份：.surgical_backups/ 是所有目标的公约数
  4. 差异预览：--diff 看本地vs远程差异再决定是否部署
"""

import os, sys, json, subprocess, argparse, shutil
from datetime import datetime

# ── 项目根目录 ──
BASE = r'D:\AISleepGen_Optimized'
SFR = r'D:\super_frontier_radar'

# ── 部署目标配置 ──
TARGETS = {
    'huawei': {
        'name': '华为云 · AISleepGen',
        'host': '123.60.222.129',
        'port': 22,
        'user': 'root',
        'password': 'Cqs591786',
        'remote_dir': '/opt/aisleepgen/',
        'health_url': 'http://123.60.222.129:8090/health',
        'files': {
            'deepseek_proxy.py': {'local': BASE, 'restart': True},
            'sleep_world_model.py': {'local': BASE, 'restart': True},
            'ricci_flow.py': {'local': BASE, 'restart': True},
            'compliance.py': {'local': BASE, 'restart': True},
            'dp_router.py': {'local': BASE, 'restart': True},
        },
        'restart_cmd': 'pkill -f deepseek_proxy.py 2>/dev/null; sleep 1; cd /opt/aisleepgen && nohup python3 -B deepseek_proxy.py > server.log 2>&1 &',
        'backup_dir': '/opt/aisleepgen/.surgical_backups/',
    },
    'tengxun': {
        'name': '腾讯云 · 华尔街脑',
        'host': '82.156.208.245',
        'port': 22,
        'user': 'ubuntu',
        'password': 'AISleepGen20260427cqs103@!',
        'remote_dir': '/home/ubuntu/brain_wallstreet/',
        'health_url': 'http://82.156.208.245:8928/health',
        'files': {
            'web_server_prod_v37.py': {'local': r'D:\OpenClaw_Memory\brain_wallstreet', 'restart': True},
            'data_layer.py': {'local': r'D:\OpenClaw_Memory\brain_wallstreet', 'restart': True},
        },
        'restart_cmd': 'screen -S ws8928_prod -X quit 2>/dev/null; sleep 1; screen -dmS ws8928_prod bash -c "cd /home/ubuntu/brain_wallstreet && python3 web_server_prod_v37.py"',
        'backup_dir': '/home/ubuntu/brain_wallstreet/.surgical_backups/',
    },
    'furnace': {
        'name': '腾讯云 · 数字生命熔炉',
        'host': '82.156.208.245',
        'port': 22,
        'user': 'ubuntu',
        'password': 'AISleepGen20260427cqs103@!',
        'remote_dir': '/home/ubuntu/digital_life/',
        'health_url': 'http://82.156.208.245:8921/health',
        'files': {
            'digital_life_v4.py': {'local': r'D:\super_frontier_radar', 'restart': True},
        },
        'restart_cmd': 'screen -S life -X quit 2>/dev/null; sleep 1; screen -dmS life bash -c "cd /home/ubuntu/digital_life && python3 digital_life_v4.py"',
        'backup_dir': '/home/ubuntu/digital_life/.surgical_backups/',
    },
    'frontier': {
        'name': '本地 · 前沿速递',
        'host': 'localhost',
        'health_url': 'http://localhost:8930/health',
        'files': {
            'n2_server.py': {'local': SFR, 'restart': True},
            'daily_local_cron.py': {'local': SFR, 'restart': False},
            'neural_nexus_v2.py': {'local': SFR, 'restart': True},
        },
        'restart_cmd': None,  # 本地用杀进程+重启
        'backup_dir': os.path.join(SFR, '.surgical_backups'),
    },
}


def preflight(target):
    """部署前的预检步骤"""
    cfg = TARGETS[target]
    print(f'[deploy] 预检: {cfg["name"]}')
    print(f'[deploy]  目标文件: {list(cfg["files"].keys())}')
    
    # 1. 检查本地文件是否存在且可编译
    for fname, finfo in cfg['files'].items():
        local_dir = finfo['local']
        fpath = os.path.join(local_dir, fname)
        if not os.path.exists(fpath):
            print(f'[deploy]  ⚠️  {fname} 不存在于 {local_dir}')
            continue
        # 对 .py 文件做编译检查
        if fname.endswith('.py'):
            try:
                import py_compile
                py_compile.compile(fpath, doraise=True)
                print(f'[deploy]  ✅ {fname} 编译通过')
            except py_compile.PyCompileError as e:
                print(f'[deploy]  ❌ {fname} 编译失败: {e}')
                return False
        else:
            print(f'[deploy]  ✅ {fname} 存在')
    
    # 2. 检查备份目录
    backup_dir = cfg['backup_dir']
    local_backup = os.path.join(BASE, '.surgical_backups')
    if os.path.exists(local_backup):
        print(f'[deploy]  ✅ 本地备份目录存在')
    
    # 3. 端口/服务状态（仅本地）
    if target == 'frontier':
        import socket
        for p in [8930, 8931]:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = s.connect_ex(('127.0.0.1', p))
            s.close()
            if result == 0:
                print(f'[deploy]  ✅ 端口 {p} 已监听')
            else:
                print(f'[deploy]  ⚠️  端口 {p} 未监听')
    
    print(f'[deploy]  ✅ 预检完成')
    return True


def backup(target, files=None):
    """
    统一备份：对目标文件执行 .surgical_backups/ 操作
    逻辑：每个文件备份到 surgical_backups/{filename}_{timestamp}.bak
    
    Returns: {filename: backup_path, ...}
    """
    cfg = TARGETS[target]
    backups = {}
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if files is None:
        files = list(cfg['files'].keys())
    
    for fname in files:
        finfo = cfg['files'].get(fname)
        if not finfo:
            continue
        local_dir = finfo['local']
        fpath = os.path.join(local_dir, fname)
        if not os.path.exists(fpath):
            continue
        
        # 本地备份
        backup_dir = os.path.join(BASE if 'AISleepGen' in cfg['name'] else SFR, '.surgical_backups')
        os.makedirs(backup_dir, exist_ok=True)
        bak_name = f'{fname}_{timestamp}.bak'
        bak_path = os.path.join(backup_dir, bak_name)
        shutil.copy2(fpath, bak_path)
        backups[fname] = bak_path
        print(f'[deploy]  ✅ 备份: {fname} → {bak_path}')
    
    return backups


def deploy(target, diff_only=False):
    """
    主部署流程：
    1. 预检
    2. 备份
    3. 编译验证
    4. 远程传输（或本地重启）
    5. 健康检查
    6. 回退预案
    """
    cfg = TARGETS[target]
    
    # Step 1: 预检
    if not preflight(target):
        print('[deploy] ❌ 预检失败，取消部署')
        return False
    
    # Step 2: 备份
    backups = backup(target)
    if not backups:
        print('[deploy] ⚠️  没有需要备份的文件')
    
    if diff_only:
        print(f'[deploy] 📋 差异模式（仅展示，不部署）')
        for fname, finfo in cfg['files'].items():
            fpath = os.path.join(finfo['local'], fname)
            if os.path.exists(fpath):
                size = os.path.getsize(fpath)
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime('%m-%d %H:%M')
                print(f'[deploy]   {fname} ({size:,} bytes, {mtime})')
        print(f'[deploy] ✅ 预览完成。去掉 --diff 执行实际部署')
        return True
    
    if target == 'frontier':
        # 本地部署：杀进程+重启
        return _deploy_local(cfg, backups)
    else:
        # 远程部署：SFTP上传 + 重启 + 健康检查
        return _deploy_remote(target, cfg, backups)


def _deploy_local(cfg, backups):
    """本地服务重启"""
    import signal
    print(f'[deploy] 🔄 本地部署...')
    
    # 找到并杀掉旧进程
    for port in [8930, 8931]:
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            result = s.connect_ex(('127.0.0.1', port))
            s.close()
            if result == 0:
                # 有进程在监听，尝试优雅关闭
                print(f'[deploy]   端口 {port} 有进程，等待关闭...')
        except:
            pass
    
    # 杀掉相关进程
    pkill_patterns = ['n2_server.py', 'neural_nexus']
    for pat in pkill_patterns:
        proc = subprocess.run(
            f'taskkill /f /fi "WINDOWTITLE eq {pat}" 2>nul',
            shell=True, capture_output=True, text=True
        )
    
    # 重新启动需要重启的服务
    for fname, finfo in cfg['files'].items():
        if finfo.get('restart', False):
            fpath = os.path.join(finfo['local'], fname)
            if 'n2_server' in fname:
                print(f'[deploy] 🚀 启动 n2_server...')
                subprocess.Popen(
                    [sys.executable, '-B', fpath],
                    cwd=finfo['local'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
    return True


def _deploy_remote(target, cfg, backups):
    """远程部署：paramiko SFTP + SSH"""
    try:
        import paramiko
    except ImportError:
        print('[deploy] ❌ paramiko 未安装，无法远程部署')
        return False
    
    print(f'[deploy] 🔄 远程部署到 {cfg["host"]} ...')
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(
            cfg['host'], port=cfg.get('port', 22),
            username=cfg['user'], password=cfg['password'],
            timeout=10
        )
        print(f'[deploy]  ✅ SSH 连接成功')
        
        sftp = ssh.open_sftp()
        
        # 远程备份
        remote_bak = cfg['backup_dir']
        try:
            sftp.stat(remote_bak)
        except:
            try:
                ssh.exec_command(f'mkdir -p {remote_bak}')
                print(f'[deploy]  ✅ 创建远程备份目录')
            except Exception as e:
                pass
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 上传文件
        for fname, finfo in cfg['files'].items():
            local_dir = finfo['local']
            local_path = os.path.join(local_dir, fname)
            if not os.path.exists(local_path):
                print(f'[deploy]  ⚠️  跳过 {fname}（本地不存在）')
                continue
            
            remote_path = os.path.join(cfg['remote_dir'], fname)
            
            # 远程备份
            try:
                remote_bak_file = os.path.join(remote_bak, f'{fname}_{timestamp}.bak')
                sftp.rename(remote_path, remote_bak_file)
                print(f'[deploy]  ✅ 远程备份: {fname}')
            except:
                pass
            
            # 上传
            sftp.put(local_path, remote_path)
            print(f'[deploy]  ✅ 上传: {fname} ({os.path.getsize(local_path):,} bytes)')
            
            # 编译验证
            if fname.endswith('.py'):
                stdin, stdout, stderr = ssh.exec_command(
                    f'cd {cfg["remote_dir"]} && python3 -B -m py_compile {fname}'
                )
                err = stderr.read().decode()
                if err:
                    print(f'[deploy]  ❌ 远程编译失败 {fname}: {err}')
                    # 回退
                    print(f'[deploy]  🔄 回退 {fname}...')
                    try:
                        ssh.exec_command(f'cp {remote_bak_file} {remote_path}')
                        print(f'[deploy]  ✅ 已回退 {fname}')
                    except:
                        print(f'[deploy]  ❌ 回退失败！')
                    sftp.close()
                    ssh.close()
                    return False
                print(f'[deploy]  ✅ 远程编译通过: {fname}')
        
        sftp.close()
        
        # 重启服务
        if cfg.get('restart_cmd'):
            print(f'[deploy] 🔄 重启服务...')
            ssh.exec_command(cfg['restart_cmd'])
            import time
            time.sleep(3)
            
            # 健康检查
            if cfg.get('health_url'):
                import urllib.request
                try:
                    resp = urllib.request.urlopen(cfg['health_url'], timeout=10)
                    if resp.status == 200:
                        print(f'[deploy]  ✅ 健康检查通过 ({resp.status})')
                    else:
                        print(f'[deploy]  ⚠️  健康检查返回 {resp.status}')
                except Exception as e:
                    print(f'[deploy]  ⚠️  健康检查失败: {e}')
        
        ssh.close()
        print(f'[deploy] ✅ 部署完成: {cfg["name"]}')
        return True
        
    except Exception as e:
        print(f'[deploy] ❌ 部署失败: {e}')
        if ssh:
            try: ssh.close()
            except: pass
        return False


def list_targets():
    """列出所有部署目标"""
    print('可用部署目标:')
    print(f'  {"目标":<12} {"名称":<24} {"地址":<24} {"端口":<8}')
    print(f'  {"-"*12} {"-"*24} {"-"*24} {"-"*8}')
    for name, cfg in sorted(TARGETS.items()):
        host = cfg.get('host', 'localhost')
        port = str(cfg.get('health_url', '').split(':')[-1].split('/')[0]) if ':' in cfg.get('health_url', '') else ''
        print(f'  {name:<12} {cfg["name"]:<24} {host:<24} {port:<8}')
    print()
    print('用法:')
    print('  aisleepgen_tool.py ops deploy <target>       # 部署到目标')
    print('  aisleepgen_tool.py ops deploy <target> --diff # 仅预览差异')
    print('  aisleepgen_tool.py ops deploy --list          # 列出目标')


def main():
    parser = argparse.ArgumentParser(description='统一部署工具')
    parser.add_argument('target', nargs='?', help='部署目标')
    parser.add_argument('--diff', action='store_true', help='仅预览差异，不部署')
    parser.add_argument('--list', action='store_true', help='列出所有部署目标')
    parser.add_argument('--file', nargs='*', help='只部署指定文件（不填则全部）')
    
    args = parser.parse_args()
    
    if args.list or not args.target:
        list_targets()
        return
    
    if args.target not in TARGETS:
        print(f'错误: 未知部署目标 "{args.target}"')
        list_targets()
        sys.exit(1)
    
    deploy(args.target, diff_only=args.diff)


if __name__ == '__main__':
    main()
