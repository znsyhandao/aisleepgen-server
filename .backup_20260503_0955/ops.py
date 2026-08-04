#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ops.py — AISleepGen 运维模块

职责：日志系统 + 进程保活 + 版本号 + 健康上报
不依赖其他业务模块，启动时自动初始化。
"""
import os, sys, json, logging, threading, time, signal
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ===== 版本号 =====
VERSION = '2.2.0'
VERSION_TAG = 'calibrated'  # 评分校准 + AI调通
CHANGES = [
    'v2.2.0 Fixed UnboundLocalError (token_estimate) — DeepSeek API now works end-to-end',
    'v2.2.0 AI reply restored: real DeepSeek calls delivering 400-1055 chars',
    'v2.2.0 Score calibration applied to both chat and analyze endpoints',
    'v2.2.0 Fixed Event loop is closed — per-call aiohttp session isolation',
    'v2.1.1 Chat returns ai_score/quality/debate for frontend rendering',
    'v2.1.1 backup_worker v2 — SQLite VACUUM INTO consistent snapshots',
    'v2.1.1 Fallback reply engine — local templates when DeepSeek API unavailable',
    'v2.1.0 Expert debate synthesis + self-learn feedback loop',
    'v2.0.5 SQLite storage backend (was JSON single-file)',
    'v2.0.4 Async AI calls (aiohttp replaces sync urllib3)',
    'v2.0.3 NLP sleep field extractor (regex-based)',
    'v2.0.2 Fix total_score scaling bug (was 3522 on insufficient data)',
    'v2.0.1 Rate limiting + AI reply cache + trend analysis',
    'v2.0.0 Complete async server rewrite (asyncio + threadpool)',
]


# ===== 日志系统 =====
_LOGGER_INITIALIZED = False
_LOG_LEVELS = {'debug': logging.DEBUG, 'info': logging.INFO,
               'warn': logging.WARNING, 'error': logging.ERROR}


def init_logger(level='info', log_dir=None):
    """初始化统一日志系统。只应调用一次。
    level: debug/info/warn/error
    """
    global _LOGGER_INITIALIZED
    if _LOGGER_INITIALIZED:
        return logging.getLogger('aisleepgen')

    if log_dir is None:
        log_dir = os.path.join(PROJECT_ROOT, 'data', 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, 'aisleepgen.log')
    lvl = _LOG_LEVELS.get(level, logging.INFO)

    logger = logging.getLogger('aisleepgen')
    logger.setLevel(lvl)
    logger.handlers.clear()

    # 文件日志（轮转）
    try:
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    except ImportError:
        fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(lvl)
    fh.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(fh)

    # 控制台日志
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(lvl)
    ch.setFormatter(logging.Formatter(
        '[%(levelname)s] %(message)s'))
    logger.addHandler(ch)

    _LOGGER_INITIALIZED = True
    logger.info('AISleepGen v%s (%s) logger initialized', VERSION, VERSION_TAG)
    logger.info('Log file: %s', log_file)
    return logger


def get_logger():
    """获取日志器（惰性初始化）"""
    if not _LOGGER_INITIALIZED:
        return init_logger()
    return logging.getLogger('aisleepgen')


# ===== 进程保活 =====
_HEARTBEAT_THREAD = None
_HEARTBEAT_STOP = threading.Event()
_WATCHDOG_CALLBACKS = []


def register_watchdog(path, interval_seconds=3600, callback=None):
    """注册健康检查回调。返回控制函数。
    path: 检查的资源路径（如 /api/metrics）
    callback: 出问题时调用的函数
    """
    _WATCHDOG_CALLBACKS.append({
        'path': path,
        'interval': interval_seconds,
        'callback': callback or (lambda: None),
        'last_check': 0,
        'failures': 0,
    })
    return len(_WATCHDOG_CALLBACKS) - 1


def _heartbeat_loop():
    """保活线程：定期检查服务器健康"""
    import urllib.request
    get_logger().info('Heartbeat monitor started')
    while not _HEARTBEAT_STOP.is_set():
        for wd in _WATCHDOG_CALLBACKS:
            now = time.time()
            if now - wd['last_check'] < wd['interval']:
                continue
            wd['last_check'] = now
            try:
                url = 'http://127.0.0.1:8090' + wd['path']
                r = urllib.request.urlopen(url, timeout=5)
                body = r.read()
                wd['failures'] = 0
                get_logger().debug('Heartbeat OK: %s', wd['path'])
            except Exception as e:
                wd['failures'] += 1
                get_logger().error('Heartbeat FAIL (%d/%d): %s - %s',
                                   wd['failures'], 3, wd['path'], e)
                if wd['failures'] >= 3:
                    get_logger().critical('Server unhealthy after 3 failures! Running callback.')
                    try:
                        wd['callback']()
                    except Exception as cb_e:
                        get_logger().critical('Watchdog callback failed: %s', cb_e)
        _HEARTBEAT_STOP.wait(30)  # 每 30 秒检查一次


def start_heartbeat():
    """启动心跳保活线程"""
    global _HEARTBEAT_THREAD
    if _HEARTBEAT_THREAD and _HEARTBEAT_THREAD.is_alive():
        get_logger().warning('Heartbeat already running')
        return
    _HEARTBEAT_STOP.clear()
    _HEARTBEAT_THREAD = threading.Thread(target=_heartbeat_loop, daemon=True,
                                         name='heartbeat')
    _HEARTBEAT_THREAD.start()
    get_logger().info('Heartbeat monitor started')


def stop_heartbeat():
    """停止心跳"""
    _HEARTBEAT_STOP.set()
    if _HEARTBEAT_THREAD:
        _HEARTBEAT_THREAD.join(timeout=3)
    get_logger().info('Heartbeat monitor stopped')


# ===== 健康检查端点（供 server 注册路由） =====
def get_server_info():
    """返回服务器版本+状态快照"""
    return {
        'version': VERSION,
        'tag': VERSION_TAG,
        'uptime': time.time() - _SERVER_START_TIME,
        'started_at': datetime.fromtimestamp(_SERVER_START_TIME).isoformat(),
        'watchdogs': len(_WATCHDOG_CALLBACKS),
    }


_SERVER_START_TIME = time.time()


# ===== 初始化（import 时自动执行） =====
_init_logger = init_logger()
_init_logger.info('ops.py loaded — v%s %s', VERSION, VERSION_TAG)
