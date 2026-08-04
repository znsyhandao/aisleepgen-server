# -*- coding: utf-8 -*-
"""
API 安全集成层 v1.0 — 桥接 ai_defender + api_security

最佳实践：
  1. 通用速率限制 → 滑动窗口(api_security已有) + 指纹分析(ai_defender)
  2. 统一审计日志 → ai_defender的威胁记录写入api_security的audit_log
  3. 可查询的安全报告 → /api/security/logs 接口
"""

import sys, os, json, time, threading
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))

# 加载两个模块
try:
    from api_security import audit_log as sec_audit_log, _check_rate_limit, _rate_windows
    API_SEC_AVAILABLE = True
except ImportError:
    API_SEC_AVAILABLE = False

try:
    from ai_defender import get_defender
    AI_DEFENDER_AVAILABLE = True
except ImportError:
    AI_DEFENDER_AVAILABLE = False

# 安全日志持久化
SECURITY_LOG_PATH = os.path.join(BASE, 'sleep-skin features', 'security_audit_log.json')
_log_lock = threading.Lock()

def _load_security_log(limit=200):
    """加载安全日志"""
    if os.path.exists(SECURITY_LOG_PATH):
        try:
            with open(SECURITY_LOG_PATH, encoding='utf-8') as f:
                return json.load(f)[-limit:]
        except:
            return []
    return []

def _append_security_log(entry):
    """追加安全日志"""
    with _log_lock:
        log = []
        if os.path.exists(SECURITY_LOG_PATH):
            try:
                with open(SECURITY_LOG_PATH, encoding='utf-8') as f:
                    log = json.load(f)
            except:
                log = []
        log.append(entry)
        # 只保留最近1000条
        if len(log) > 1000:
            log = log[-1000:]
        os.makedirs(os.path.dirname(SECURITY_LOG_PATH), exist_ok=True)
        with open(SECURITY_LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump(log, f, ensure_ascii=False, indent=2)


def unified_security_check(ip, path, method, body='', user_agent='', openid=''):
    """
    统一安全检查入口 — 整合 ai_defender + api_security
    
    返回: (allow: bool, response: dict or None, reason: str)
      allow=False → 应立即返回错误response
      allow=True → 正常放行
    """
    reasons = []
    
    # 1. ai_defender 蜜罐 + 常规过滤
    if AI_DEFENDER_AVAILABLE:
        d = get_defender()
        allow, resp = d.inspect_request(ip, path, method, body, user_agent)
        if not allow:
            reason = resp.get('error', 'blocked')
            status = resp.get('status', 403)
            _log_event(ip, path, method, 'ai_defender', reason, status, openid)
            return False, resp, reason
    
    # 2. api_security 速率限制
    if API_SEC_AVAILABLE:
        allowed, max_rpm, current = _check_rate_limit(ip, 300)
        if not allowed:
            _log_event(ip, path, method, 'rate_limit', f'超过速率限制({current}/{max_rpm})', 429, openid)
            return False, {'error': 'rate_limited', 'status': 429, 'message': '请求过频'}, 'rate_limit'
    
    return True, None, ''


def _log_event(ip, endpoint, method, source, detail, status=403, openid=''):
    """统一写入安全日志"""
    entry = {
        'ts': datetime.now().isoformat(),
        'ip': ip,
        'endpoint': endpoint[:80],
        'method': method,
        'source': source,
        'detail': detail[:200],
        'status': status,
        'openid': openid[:20] if openid else '',
    }
    _append_security_log(entry)
    
    # 同步写入 api_security.audit_log（如果可用）
    if API_SEC_AVAILABLE:
        sec_audit_log(ip, endpoint, openid, '', f'blocked_{source}', detail)


def get_security_report(hours=24):
    """生成安全报告 — 供 /api/security/logs 接口"""
    log = _load_security_log()
    
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    recent = [e for e in log if str(e.get('ts', '')) >= cutoff]
    
    # 统计
    by_source = {}
    by_ip = {}
    by_endpoint = {}
    blocked_count = 0
    
    for e in recent:
        source = e.get('source', 'unknown')
        ip = e.get('ip', 'unknown')
        ep = e.get('endpoint', 'unknown')
        
        by_source[source] = by_source.get(source, 0) + 1
        by_ip[ip] = by_ip.get(ip, 0) + 1
        by_endpoint[ep] = by_endpoint.get(ep, 0) + 1
        
        # 类型兼容（status可能是int或str）
        st = e.get('status', 200)
        if isinstance(st, str):
            try:
                st = int(st)
            except:
                st = 200
        if st >= 400:
                st = 200
        if st >= 400:
            blocked_count += 1
    
    # 威胁IP排行
    threat_ips = sorted(by_ip.items(), key=lambda x: -x[1])[:10]
    
    # ai_defender 报告
    defender_report = {}
    if AI_DEFENDER_AVAILABLE:
        try:
            defender_report = get_defender().report_api_status()
        except:
            defender_report = {'status': 'error'}
    
    return {
        'status': 'active',
        'period_hours': hours,
        'total_events': len(recent),
        'blocked': blocked_count,
        'allowed': len(recent) - blocked_count,
        'by_source': dict(sorted(by_source.items(), key=lambda x: -x[1])),
        'top_threat_ips': [
            {'ip': ip, 'count': cnt, 'detail': _get_last_detail(log, ip)}
            for ip, cnt in threat_ips
        ],
        'top_endpoints': dict(sorted(by_endpoint.items(), key=lambda x: -x[1])[:5]),
        'defender': defender_report,
        'generated': datetime.now().isoformat(),
    }


def _get_last_detail(log, ip):
    """获取某个IP的最新一条详情"""
    for e in reversed(log):
        if e.get('ip') == ip:
            return e.get('detail', '')
    return ''


def get_recent_events(limit=50):
    """获取最近的安全事件"""
    log = _load_security_log(limit)
    return list(reversed(log))
