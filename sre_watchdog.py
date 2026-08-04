# -*- coding: utf-8 -*-
"""
SRE 运维专家 v1 — 自动守护 deepseek_proxy.py

三件事：
1. 检查服务器是否活着（HTTP健康检查）
2. 死了就重启（自动拉起）
3. 磁盘/内存/进程监控（报警）

调度官注册名：'🖥️ SRE运维专家 (sre_watchdog)'
"""

import os, sys, json, time, subprocess, socket
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
SLEEP_SKIN = os.path.join(BASE, 'sleep-skin features')
WATCHDOG_LOG = os.path.join(SLEEP_SKIN, 'sre_watchdog_log.json')
HEALTH_LOG = os.path.join(SLEEP_SKIN, 'health_check_log.json')

PROXY_PORT = 8090
PROXY_SCRIPT = os.path.join(BASE, 'deepseek_proxy.py')
PROXY_NAME = 'deepseek_proxy'

WATCHDOG_SCRIPT = os.path.abspath(__file__)

# ============================================================
# 1. 健康检查
# ============================================================

def is_server_alive(port=PROXY_PORT):
    """TCP连接检查，不依赖HTTP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(('127.0.0.1', port))
        s.close()
        return True
    except:
        return False


def is_process_running(process_name=PROXY_NAME):
    """检查进程是否存在"""
    try:
        if sys.platform == 'win32':
            r = subprocess.run(
                ['tasklist', '/FI', f'IMAGENAME eq python.exe', '/FO', 'CSV'],
                capture_output=True, text=True, timeout=5
            )
            # 检查命令行中是否包含进程名
            return 'deepseek_proxy' in r.stdout or 'deepseek' in r.stdout.lower()
        else:
            r = subprocess.run(
                ['pgrep', '-f', process_name],
                capture_output=True, text=True, timeout=5
            )
            return r.returncode == 0
    except:
        return False


# ============================================================
# 2. 自动重启
# ============================================================

def restart_server():
    """拉起 deepseek_proxy.py"""
    if not os.path.exists(PROXY_SCRIPT):
        return {'status': 'error', 'reason': f'脚本不存在: {PROXY_SCRIPT}'}
    
    try:
        # Windows上直接用 start /B 后台启动
        if sys.platform == 'win32':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            proc = subprocess.Popen(
                [sys.executable, PROXY_SCRIPT],
                cwd=BASE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                startupinfo=startupinfo,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {
                'status': 'ok',
                'pid': proc.pid,
                'note': f'已启动 deepseek_proxy (PID={proc.pid})',
            }
        else:
            proc = subprocess.Popen(
                [sys.executable, PROXY_SCRIPT],
                cwd=BASE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {
                'status': 'ok',
                'pid': proc.pid,
                'note': f'已启动 deepseek_proxy (PID={proc.pid})',
            }
    except Exception as e:
        return {'status': 'error', 'reason': str(e)[:200]}


# ============================================================
# 3. 磁盘监控 + 日志轮转建议
# ============================================================

def disk_status():
    """检查磁盘空间"""
    info = {}
    for path, label in [
        ('D:/', 'D盘(数据)'),
        ('C:/', 'C盘(系统)'),
    ]:
        try:
            usage = subprocess.run(
                ['wmic', 'logicaldisk', 'where', f'name="{path}"', 'get', 'size,freespace', '/format:csv'],
                capture_output=True, text=True, timeout=5
            )
            lines = [l.strip() for l in usage.stdout.split('\n') if l.strip() and ',' in l]
            for line in lines:
                parts = line.split(',')
                if len(parts) >= 3:
                    free = int(parts[1]) if parts[1].isdigit() else 0
                    total = int(parts[2]) if parts[2].isdigit() else 0
                    if total > 0:
                        pct = (total - free) / total * 100
                        info[label] = f'{pct:.0f}% 已用({free/1024**3:.0f}GB空闲/{total/1024**3:.0f}GB)'
        except:
            info[label] = '无法获取'
    return info


def memory_status():
    """检查内存"""
    try:
        r = subprocess.run(
            ['wmic', 'OS', 'get', 'TotalVisibleMemorySize,FreePhysicalMemory', '/format:csv'],
            capture_output=True, text=True, timeout=5
        )
        for line in r.stdout.split('\n'):
            if 'TotalVisibleMemorySize' in line:
                continue
            parts = line.strip().split(',')
            if len(parts) >= 3:
                total_kb = int(parts[1]) if parts[1].isdigit() else 0
                free_kb = int(parts[2]) if parts[2].isdigit() else 0
                if total_kb > 0:
                    used_pct = (total_kb - free_kb) / total_kb * 100
                    return f'{used_pct:.0f}% 已用({free_kb//1024}MB空闲/{total_kb//1024}MB)'
        return '无法获取'
    except:
        return '无法获取'


# ============================================================
# 4. 日志清理建议 + 自动清理
# ============================================================

def check_disk_hogs(threshold_mb=100):
    """检查大文件，建议清理"""
    hogs = []
    paths_to_check = [
        (BASE, '*.py'),
        (os.path.join(BASE, 'sleep_record'), '*.m4a'),
        (os.path.join(BASE, 'sleep_record', 'analyzed'), '*.json'),
        (os.path.join(BASE, 'sleep-skin features'), '*'),
    ]
    
    for base_path, pattern in paths_to_check:
        if not os.path.exists(base_path):
            continue
        try:
            r = subprocess.run(
                ['powershell', '-Command',
                 f'Get-ChildItem -Path "{base_path}" -Filter "{pattern}" -Recurse -ErrorAction SilentlyContinue | '
                 f'Where-Object {{ $_.Length -gt {threshold_mb * 1024 * 1024} }} | '
                 f'Select-Object Name, @{{N="MB";E={[math]::Round($_.Length/1MB,1)}}} | '
                 f'ConvertTo-Json -Compress'],
                capture_output=True, text=True, timeout=10
            )
            if r.stdout.strip() and r.stdout.strip() != '[]':
                hogs.append(f'{base_path}: {r.stdout.strip()[:200]}')
        except:
            pass
    
    return hogs


# ============================================================
# 5. SRE 主循环
# ============================================================

def _load_history():
    if os.path.exists(WATCHDOG_LOG):
        try:
            with open(WATCHDOG_LOG, encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {'restarts': [], 'failures': [], 'previous_status': True}


def _save_history(h):
    os.makedirs(os.path.dirname(WATCHDOG_LOG), exist_ok=True)
    with open(WATCHDOG_LOG, 'w', encoding='utf-8') as f:
        json.dump(h, f, ensure_ascii=False, indent=2)


def watch():
    """单次巡检"""
    history = _load_history()
    now = datetime.now().isoformat()
    
    report = {
        'ts': now,
        'server_alive': is_server_alive(),
        'process_running': is_process_running(),
    }
    
    # 磁盘和内存
    report['disk'] = disk_status()
    report['memory'] = memory_status()
    
    # 如果不活着，重启
    if not report['server_alive']:
        reason = 'TCP端口不通'
        result = restart_server()
        history['restarts'].append({
            'ts': now,
            'reason': reason,
            'result': result,
        })
        report['action_taken'] = f'服务器已重启: {result["note"]}'
        report['status'] = 'restarted'
    elif not report['process_running']:
        # TCP通但进程名不在tasklist里——重启
        result = restart_server()
        history['restarts'].append({
            'ts': now,
            'reason': '进程不存在(但端口通，可能被换端口)',
            'result': result,
        })
        report['action_taken'] = f'进程不存在，已重启: {result["note"]}'
        report['status'] = 'restarted'
    else:
        report['status'] = 'healthy'
        report['action_taken'] = '无'
    
    # 如果之前活着现在死了，记录失败
    if history.get('previous_status') and not report['server_alive']:
        history['failures'].append({'ts': now, 'duration': 'unknown'})
    history['previous_status'] = report['server_alive']
    
    # 只保留最近20条重启记录
    if len(history.get('restarts', [])) > 20:
        history['restarts'] = history['restarts'][-20:]
    if len(history.get('failures', [])) > 20:
        history['failures'] = history['failures'][-20:]
    
    _save_history(history)
    
    # 磁盘告警
    for drive, info in report['disk'].items():
        if '90%' in info:
            report['alert'] = f'磁盘告警: {drive} {info}'
    
    return report


def log_health_check():
    """健康检查日志（供调度官调用）"""
    report = watch()
    
    # 同时写入健康日志
    os.makedirs(os.path.dirname(HEALTH_LOG), exist_ok=True)
    health_log = []
    if os.path.exists(HEALTH_LOG):
        try:
            with open(HEALTH_LOG, encoding='utf-8') as f:
                health_log = json.load(f)
        except:
            health_log = []
    health_log.append(report)
    if len(health_log) > 100:
        health_log = health_log[-100:]
    with open(HEALTH_LOG, 'w', encoding='utf-8') as f:
        json.dump(health_log, f, ensure_ascii=False, indent=2)
    
    return report


# ============================================================
# 6. 持久化后台看护（可选）
# ============================================================

def run_daemon(interval=300):
    """后台持续看护，每5分钟检查一次"""
    print(f'[SRE] 后台看护启动，间隔={interval}s')
    while True:
        try:
            r = watch()
            if r['status'] == 'restarted':
                print(f'[SRE] {datetime.now().strftime("%H:%M:%S")} 服务器重启')
            time.sleep(interval)
        except KeyboardInterrupt:
            print('[SRE] 看护退出')
            break
        except Exception as e:
            print(f'[SRE] 异常: {e}')
            time.sleep(interval)


if __name__ == '__main__':
    print('=' * 60)
    print(f'  SRE 运维专家巡检  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('=' * 60)
    
    report = log_health_check()
    status = report['status']
    alive = report['server_alive']
    
    print(f'  🔌 服务器状态: {"✅ 运行中" if alive else "❌ 已宕机 → 已自动重启"}')
    print(f'  📋 本次操作: {report.get("action_taken", "无")}')
    print(f'  💾 磁盘:')
    for drive, info in report.get('disk', {}).items():
        print(f'    {drive}: {info}')
    print(f'  🧠 内存: {report.get("memory", "N/A")}')
    
    # 看重启历史
    try:
        with open(WATCHDOG_LOG, encoding='utf-8') as f:
            hist = json.load(f)
        restarts = hist.get('restarts', [])
        if restarts:
            print(f'  🔄 历史重启: {len(restarts)}次')
            for r in restarts[-3:]:
                print(f'    {r["ts"][:19]} {r.get("reason","")}')
    except:
        pass
    
    print()
    print(f'  ✅ SRE运维专家在线')
