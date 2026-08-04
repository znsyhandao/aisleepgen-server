# -*- coding: utf-8 -*-
"""
deploy_aisleepgen.py — AISleepGen 一键部署管线 (阶段3)
本地 Dev (git 权威源) → tar 包 → 华为云生产 (备份+覆盖+重启+验证+回滚)

用法:
  python deploy_aisleepgen.py            # 全流程部署
  python deploy_aisleepgen.py --dry-run  # 只打包+diff 预览, 不部署
  python deploy_aisleepgen.py --no-restart  # 部署但不重启服务(只更新文件)

安全设计:
  - 部署前华为云备份将被覆盖的文件 (.deploy_backups/<ts>/)
  - 覆盖式解压, 不删除生产额外文件 (core_dev 算法/备份/日志全保留)
  - 部署后 py_compile 全量校验 + health/algo-list/algo-run 验证
  - 验证失败自动回滚 + 重启
"""
import os, sys, io, time, subprocess, tarfile, tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stdout.reconfigure(line_buffering=True)

# ===== 配置 =====
LOCAL_REPO = r'D:\AISleepGen_Optimized'
HW_HOST = "123.60.222.129"; HW_PORT = 22; HW_USER = "root"; HW_PWD = "Cqs591786"
HW_DIR = "/opt/aisleepgen"
TS = time.strftime('%Y%m%d_%H%M%S')

DRY_RUN = '--dry-run' in sys.argv
NO_RESTART = '--no-restart' in sys.argv

def log(msg):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), msg), flush=True)

# ===== 1. 本地打包 =====
def build_package():
    """git archive 打包 + 白名单过滤 (只部署生产代码, 排除开发工具/数据)"""
    log('打包本地 HEAD 代码树 (白名单过滤)...')
    r = subprocess.run(['git', 'archive', '--format=tar', '-o', 'deploy_pkg_full.tar', 'HEAD'],
                       cwd=LOCAL_REPO, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        log('FATAL: git archive 失败: %s' % r.stderr[-300:])
        sys.exit(1)

    # 白名单: 华为云生产 36 个顶层模块 + core_dev/*.py + tools/*.py
    TOP_PY = {  # 华为云 master 生产依赖集 (2026-08-04 快照)
        '_insert_v3.py', 'api_security.py', 'auto_case_growth.py', 'big_transfer.py',
        'cache_layer.py', 'context_distiller.py', 'decision_cache.py', 'deepseek_proxy.py',
        'deepseek_watchdog.py', 'device_data_injector.py', 'differential_regression.py',
        'dpo_preference.py', 'effectiveness_loop.py', 'extractor.py', 'failure_aware_planner.py',
        'live_capture.py', 'long_haul_test.py', 'magi_client.py', 'payment_api.py',
        'post_edit_hook.py', 'quality_baseline.py', 'regression_scanner.py', 'request_routing.py',
        'safety_gate.py', 'security_bridge.py', 'self_evolve.py', 'self_healer.py',
        'semantic_scanner.py', 'shared_experience_memory.py', 'shared_fail_memory.py',
        'sleep_stage_analyzer.py', 'sleep_world_model.py', 'sleep_world_model_v4.2_new.py',
        'sqlite_db.py', 'tier_recommender.py', 'trajectory_model_db.py',
    }
    def is_prod_file(rel):
        if rel in TOP_PY:
            return True
        if rel.startswith('core_dev/') and rel.endswith('.py') and rel.count('/') == 1:
            return True
        if rel.startswith('tools/') and rel.endswith('.py') and rel.count('/') == 1:
            return True
        return False

    full = os.path.join(LOCAL_REPO, 'deploy_pkg_full.tar')
    out = os.path.join(LOCAL_REPO, 'deploy_pkg.tar.gz')
    kept = 0
    with tarfile.open(full, 'r:') as tin, tarfile.open(out, 'w:gz') as tout:
        for m in tin.getmembers():
            if not m.isfile():
                continue
            rel = m.name
            if is_prod_file(rel):
                f = tin.extractfile(m)
                data = f.read() if f else b''
                nm = tarfile.TarInfo(rel)
                nm.size = len(data)
                nm.mtime = int(time.time())
                tout.addfile(nm, io.BytesIO(data))
                kept += 1
    os.remove(full)
    sz = os.path.getsize(out) / 1e6
    log('白名单打包完成: %d 个生产文件 (%.1f MB)' % (kept, sz))
    return out

# ===== 2. 华为云部署 =====
def deploy_remote(pkg_path):
    import paramiko
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HW_HOST, HW_PORT, HW_USER, HW_PWD, timeout=20)

    def run(cmd, t=300):
        _, out, err = cli.exec_command(cmd, timeout=t)
        return out.read().decode('utf-8', 'replace').strip(), err.read().decode('utf-8', 'replace').strip()

    # 2a. 传输
    log('传输部署包到华为云...')
    sftp = cli.open_sftp()
    remote_pkg = '/tmp/deploy_pkg_%s.tar.gz' % TS
    sftp.put(pkg_path, remote_pkg)
    sftp.close()
    log('传输完成 -> %s' % remote_pkg)

    # 2b. 远端部署脚本 (独立文件避免引号问题)
    from string import Template
    remote_script = r'''
import os, sys, tarfile, shutil, time, subprocess
HW_DIR = '/opt/aisleepgen'
TS = '$TS'
pkg = '/tmp/deploy_pkg_$TS.tar.gz'
backup_dir = os.path.join(HW_DIR, '.deploy_backups', TS)
dry = $DRY
no_restart = $NO_RESTART

# 1. 解压到临时目录 (拿到文件清单)
extract_dir = '/tmp/deploy_extract_$TS'
os.makedirs(extract_dir, exist_ok=True)
with tarfile.open(pkg, 'r:gz') as t:
    t.extractall(extract_dir)
filelist = []
for root, dirs, files in os.walk(extract_dir):
    for f in files:
        rel = os.path.relpath(os.path.join(root, f), extract_dir)
        filelist.append(rel)
print('部署包文件数: %d' % len(filelist), flush=True)

# 2. 备份将被覆盖的文件
os.makedirs(backup_dir, exist_ok=True)
backed = 0
for rel in filelist:
    src = os.path.join(HW_DIR, rel)
    if os.path.exists(src):
        dst = os.path.join(backup_dir, rel)
        d = os.path.dirname(dst)
        if d:
            os.makedirs(d, exist_ok=True)
        shutil.copy2(src, dst)
        backed += 1
print('已备份将被覆盖文件: %d' % backed, flush=True)

if dry:
    print('DRY_RUN: 跳过应用', flush=True)
    sys.exit(0)

# 3. 应用 (覆盖同名文件, 保留生产额外文件)
applied = 0
for rel in filelist:
    src = os.path.join(extract_dir, rel)
    dst = os.path.join(HW_DIR, rel)
    d = os.path.dirname(dst)
    if d:
        os.makedirs(d, exist_ok=True)
    shutil.copy2(src, dst)
    applied += 1
print('已应用: %d' % applied, flush=True)

# 4. py_compile 全量校验
bad = []
for rel in filelist:
    if rel.endswith('.py'):
        p = os.path.join(HW_DIR, rel)
        try:
            import py_compile
            py_compile.compile(p, doraise=True)
        except Exception as e:
            bad.append('%s: %s' % (rel, e))
if bad:
    print('COMPILE_FAIL: %d 个文件编译失败' % len(bad), flush=True)
    for b in bad[:10]:
        print('  ' + b, flush=True)
    print('ROLLBACK_NEEDED', flush=True)
    sys.exit(2)
print('COMPILE_OK', flush=True)

# 5. 重启
if no_restart:
    print('NO_RESTART: 跳过重启', flush=True)
else:
    r = subprocess.run(['systemctl', 'restart', 'aisleepgen'], capture_output=True, text=True, timeout=60)
    time.sleep(8)
    r2 = subprocess.run(['systemctl', 'is-active', 'aisleepgen'], capture_output=True, text=True, timeout=30)
    print('服务状态: %s' % r2.stdout.strip(), flush=True)
    if r2.stdout.strip() != 'active':
        print('RESTART_FAIL', flush=True)
        sys.exit(3)

# 6. 验证
import urllib.request, json
def probe(path, payload=None, t=30):
    try:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request('http://127.0.0.1:8090' + path, data=data,
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=t) as resp:
            return resp.status, resp.read().decode('utf-8', 'replace')[:300]
    except Exception as e:
        return 0, str(e)

s1, b1 = probe('/health')
s2, b2 = probe('/api/sleep/algo-list', {})
s3, b3 = probe('/api/sleep/algo-run', {'algo': 'Mut_自组织临界性_v5', 'args': {}})
print('health: %s' % s1, flush=True)
print('algo-list: %s (%s)' % (s2, b2[:80]), flush=True)
print('algo-run: %s (%s)' % (s3, b3[:80]), flush=True)
if s1 == 200 and s2 == 200 and s3 == 200:
    print('DEPLOY_OK', flush=True)
else:
    print('VERIFY_FAIL', flush=True)
    sys.exit(4)
'''
    script = Template(remote_script).substitute(TS=TS, DRY=DRY_RUN, NO_RESTART=NO_RESTART)

    import base64
    b64 = base64.b64encode(script.encode('utf-8')).decode('ascii')
    o, e = run("echo %s | base64 -d > /tmp/deploy_run_%s.py && /usr/bin/python3 /tmp/deploy_run_%s.py" % (b64, TS, TS), t=600)
    print(o or e, flush=True)

    # 回滚 (如果远端脚本退出码非0)
    if 'ROLLBACK_NEEDED' in o or 'RESTART_FAIL' in o or 'VERIFY_FAIL' in o:
        log('⚠️ 部署验证失败, 执行回滚...')
        rollback_script = r'''
import os, shutil, subprocess, time
HW_DIR = '/opt/aisleepgen'
TS = '$TS'
backup_dir = os.path.join(HW_DIR, '.deploy_backups', TS)
restored = 0
for root, dirs, files in os.walk(backup_dir):
    for f in files:
        rel = os.path.relpath(os.path.join(root, f), backup_dir)
        dst = os.path.join(HW_DIR, rel)
        d = os.path.dirname(dst)
        if d:
            os.makedirs(d, exist_ok=True)
        shutil.copy2(os.path.join(root, f), dst)
        restored += 1
print('已恢复: %d' % restored, flush=True)
r = subprocess.run(['systemctl', 'restart', 'aisleepgen'], capture_output=True, text=True, timeout=60)
time.sleep(8)
r2 = subprocess.run(['systemctl', 'is-active', 'aisleepgen'], capture_output=True, text=True, timeout=30)
print('回滚后服务: %s' % r2.stdout.strip(), flush=True)
'''
        b64r = base64.b64encode(Template(rollback_script).substitute(TS=TS).encode('utf-8')).decode('ascii')
        o2, e2 = run("echo %s | base64 -d > /tmp/rollback_%s.py && /usr/bin/python3 /tmp/rollback_%s.py" % (b64r, TS, TS), t=300)
        print(o2 or e2, flush=True)
        log('回滚完成')
        cli.close()
        sys.exit(5)

    cli.close()
    log('部署成功 ✅')

if __name__ == '__main__':
    pkg = build_package()
    if DRY_RUN:
        log('DRY_RUN 模式: 仅打包完成, 未部署')
        sys.exit(0)
    deploy_remote(pkg)
    log('全流程完成')
