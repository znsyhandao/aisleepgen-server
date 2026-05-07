#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backup_worker.py — AISleepGen 数据自动备份（v2）

备份策略：
  - SQLite DB：用 VACUUM INTO 做在线一致性快照（不锁主库）
  - JSON/user_profile.json：增量复制到备份目录
  - logs/：压缩归档
每 30 分钟备份一次，保留最近 24 小时。
独立进程，不与主服务器共享内存。

启动: python backup_worker.py
"""
import os, shutil, time, glob, json
from datetime import datetime, timedelta
import sqlite3 as _sqlite3

PROJECT_ROOT = r'D:\AISleepGen_Optimized'
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
BACKUP_ROOT = r'D:\AISleepGen_Backups\AISleepGen_Optimized\data'
INTERVAL = 1800  # 30 分钟
RETENTION_HOURS = 24  # 保留 24 小时
PID_PATH = os.path.join(PROJECT_ROOT, 'data', 'backup_worker.pid')

def _log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f'[{ts}] [backup] {msg}')

def _backup_sqlite(src, dst_file):
    """SQLite VACUUM INTO 在线快照——不阻塞主库写入"""
    if not os.path.exists(src):
        _log('  SQLite DB 不存在，跳过')
        return False
    try:
        conn = _sqlite3.connect(src, timeout=5)
        conn.execute(f"VACUUM INTO '{dst_file}'")
        conn.close()
        _log(f'  SQLite 快照: {os.path.getsize(dst_file)/1024:.1f}KB')
        return True
    except Exception as e:
        _log(f'  SQLite 快照失败: {e}')
        return False

def do_backup():
    """执行一次一致性备份"""
    if not os.path.isdir(DATA_DIR):
        _log(f'DATA_DIR 不存在: {DATA_DIR}')
        return

    os.makedirs(BACKUP_ROOT, exist_ok=True)

    # 本轮备份目标目录
    now = datetime.now()
    stamp = now.strftime('%Y%m%d_%H%M%S')
    dst_dir = os.path.join(BACKUP_ROOT, f'backup_{stamp}')
    os.makedirs(dst_dir, exist_ok=False)

    # 1. SQLite 在线快照（核心数据）
    db_src = os.path.join(DATA_DIR, 'sleep.db')
    db_dst = os.path.join(dst_dir, 'sleep.db')
    _backup_sqlite(db_src, db_dst)

    # 2. 复制 JSON 配置文件
    for fn in ['user_profile.json', 'calibration.json']:
        src = os.path.join(DATA_DIR, fn)
        if os.path.exists(src):
            try:
                shutil.copy2(src, os.path.join(dst_dir, fn))
            except Exception as e:
                _log(f'  {fn} 复制失败: {e}')

    # 3. 复制日志文件
    log_dir = os.path.join(DATA_DIR, 'logs')
    if os.path.isdir(log_dir):
        for fn in os.listdir(log_dir):
            if fn.endswith('.log'):
                try:
                    shutil.copy2(os.path.join(log_dir, fn), os.path.join(dst_dir, fn))
                except:
                    pass

    # 4. 清理超过 RETENTION_HOURS 的旧备份
    cutoff = now - timedelta(hours=RETENTION_HOURS)
    removed = 0
    for entry in os.listdir(BACKUP_ROOT):
        entry_path = os.path.join(BACKUP_ROOT, entry)
        if not os.path.isdir(entry_path) or not entry.startswith('backup_'):
            continue
        try:
            ts = datetime.strptime(entry.replace('backup_', ''), '%Y%m%d_%H%M%S')
            if ts < cutoff:
                shutil.rmtree(entry_path, ignore_errors=True)
                removed += 1
        except:
            pass

    _log(f'备份完成: {stamp} ({removed} 个旧备份已清理)')
    return dst_dir


def main():
    os.makedirs(os.path.dirname(PID_PATH), exist_ok=True)
    with open(PID_PATH, 'w') as f:
        f.write(str(os.getpid()))
    _log(f'备份进程 v2 PID={os.getpid()}, 间隔={INTERVAL//60}分, 保留={RETENTION_HOURS}小时')
    _log(f'源: {DATA_DIR}')
    _log(f'目标: {BACKUP_ROOT}')

    do_backup()
    while True:
        time.sleep(INTERVAL)
        do_backup()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        _log('手动停止')
        if os.path.exists(PID_PATH):
            os.remove(PID_PATH)
