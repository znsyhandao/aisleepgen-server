# -*- coding: utf-8 -*-
"""
api_security.py — API 安全模块 v1.0
为 deepseek_proxy.py 提供 API Key 验证、速率限制、请求审计。

用法: from api_security import verify_api_key, rate_limit, audit_log

环境变量:
  API_KEYS:        逗号分隔的 API Key 列表（设置后才启用）
  RATE_LIMIT_RPM:  每分钟最大请求数（默认 60）
"""
import os, time, json, hashlib, threading, re
from datetime import datetime

# ── 配置 ──
API_KEYS = set()
_keys_env = os.environ.get("API_KEYS", "")
if _keys_env:
    API_KEYS = set(k.strip() for k in _keys_env.split(",") if k.strip())

RATE_LIMIT_RPM = int(os.environ.get("RATE_LIMIT_RPM", "60"))
API_SECURITY_ENABLED = bool(API_KEYS)

# ── 速率限制（滑动窗口） ──
_rate_lock = threading.Lock()
_rate_windows = {}  # client_ip_or_key -> [(timestamp, count)]

def _check_rate_limit(key, max_rpm):
    """滑动窗口速率检查"""
    now = time.time()
    window_start = now - 60
    with _rate_lock:
        if key not in _rate_windows:
            _rate_windows[key] = []
        # 清理过期记录
        _rate_windows[key] = [(t, c) for t, c in _rate_windows[key] if t > window_start]
        # 计算当前窗口总请求数
        total = sum(c for _, c in _rate_windows[key])
        if total >= max_rpm:
            return False, max_rpm, total
        # 记录请求
        _rate_windows[key].append((now, 1))
        return True, max_rpm, total + 1

# ── 审计日志（内存+文件） ──
_audit_lock = threading.Lock()
_audit_log = []

def audit_log(client_ip, endpoint, openid="", api_key="", status="ok", detail=""):
    """记录一次 API 请求审计"""
    entry = {
        "time": datetime.now().isoformat(),
        "ip": client_ip,
        "endpoint": endpoint[:60],
        "openid": openid[:20] if openid else "",
        "api_key": api_key[:8] if api_key else "",
        "status": status[:20],
        "detail": detail[:100]
    }
    with _audit_lock:
        _audit_log.append(entry)
        if len(_audit_log) > 10000:
            _audit_log[:] = _audit_log[-5000:]
    # 定期持久化（每 100 条写一次）
    if len(_audit_log) % 100 == 0:
        _persist_audit_log()

def _persist_audit_log():
    """持久化审计日志到文件"""
    try:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_log.json")
        with _audit_lock:
            existing = []
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            existing.extend(_audit_log)
            existing = existing[-20000:]
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            _audit_log.clear()
    except Exception:
# ── 公开 API ──

def verify_api_key(auth_header):
    """
    验证 API Key
    auth_header: Authorization 头的值（如 "Bearer sk-xxx"）
    返回: {success, key, error}
    """
    if not API_SECURITY_ENABLED:
        # 未配置 API_KEYS 时，使用内置的 openid 验证走小程序流程
        return {"success": True, "key": "internal", "mode": "openid"}

    if not auth_header:
        return {"success": False, "key": "", "error": "缺少 Authorization 头"}

    parts = auth_header.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return {"success": False, "key": "", "error": "Authorization 格式错误，应为 Bearer <key>"}

    key = parts[1]
    if key in API_KEYS:
        return {"success": True, "key": key, "mode": "apikey"}
    else:
        return {"success": False, "key": key[:8], "error": "无效的 API Key"}

def check_rate_limit(client_ip_or_key):
    """
    检查速率限制
    返回: {allowed, current_rpm, max_rpm}
    """
    max_rpm = RATE_LIMIT_RPM
    allowed, max_rpm, current = _check_rate_limit(client_ip_or_key, max_rpm)
    return {"allowed": allowed, "current_rpm": current, "max_rpm": max_rpm}

def get_audit_summary(minutes=60):
    """获取审计摘要"""
    cutoff = time.time() - minutes * 60
    recent = [e for e in _audit_log if e.get('_ts', 0) >= cutoff]
    errors = [e for e in recent if e['status'] != 'ok']
    return {
        "period_minutes": minutes,
        "total_requests": len(recent),
        "error_count": len(errors),
        "rate_limited": len([e for e in errors if 'rate' in e.get('detail','').lower()]),
        "unique_ips": len(set(e['ip'] for e in recent if e['ip']))
    }

def rate_limit_decorator(max_rpm=None):
    """速率限制装饰器（供 deepseek_proxy.py 使用）"""
    rpm = max_rpm or RATE_LIMIT_RPM
    def decorator(func):
        def wrapper(*args, **kwargs):
            # 从 args 或 kwargs 获取 client_ip 和 auth
            client_ip = kwargs.get('client_ip', '')
            auth_header = kwargs.get('auth_header', '')
            if not client_ip and args:
                client_ip = str(args[0]) if isinstance(args[0], str) else ''
            allowed, _, current = _check_rate_limit(client_ip or 'unknown', rpm)
            if not allowed:
                audit_log(client_ip or 'unknown', func.__name__, "", "", "rate_limited",
                          "超过速率限制 (%d req/min)" % rpm)
                return {"error": "rate_limited", "message": "请求过频，请稍后再试",
                        "current_rpm": current, "max_rpm": rpm}
            return func(*args, **kwargs)
        return wrapper
    return decorator

# ── 数据合规声明（用于隐私政策页面） ──
DATA_COMPLIANCE_STATEMENT = """
## 数据处理声明

1. **数据收集**: AISleepGen 收集用户的睡眠评分、音频特征、HRV数据、问卷填写内容
2. **数据用途**: 仅用于提供个性化睡眠分析和干预建议
3. **数据存储**: 数据存储在中国大陆服务器，使用 AES-256 加密
4. **数据保留**: 用户数据在账户停用后保留 90 天，之后自动删除
5. **数据删除**: 用户可通过 /api/delete-account 接口申请删除全量数据
6. **数据导出**: 用户可通过 /api/export-data 接口导出自己的数据
7. **第三方共享**: AISleepGen 不向任何第三方出售或共享用户数据
8. **联系方式**: 数据相关疑问请联系 cqs103@163.com

处理依据:《个人信息保护法》《数据安全法》《微信小程序运营规范》
"""

__all__ = ["verify_api_key", "check_rate_limit", "audit_log",
           "get_audit_summary", "rate_limit_decorator",
           "API_SECURITY_ENABLED", "DATA_COMPLIANCE_STATEMENT"]
