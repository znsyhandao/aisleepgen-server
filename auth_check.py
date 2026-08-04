# -*- coding: utf-8 -*-
"""
微信登录状态自动检测器
检查后端 session_key/openid 相关路由是否正常响应。
用于提交前确认登录流程没有被人为改动破坏。

用法:
  python auth_check.py                    # 本地localhost:8090检查
  python auth_check.py --remote           # 远程82.156.208.245:8090检查
  python auth_check.py --check-only       # 只检查不退出

返回码: 0=通过  1=失败
"""
import os, sys, json, urllib.request, urllib.error, socket
import http.client

LOCAL_URL = 'http://localhost:8090'
REMOTE_URL = 'http://82.156.208.245:8090'

# 要检查的登录相关路由
AUTH_ROUTES = [
    '/api/health',
    '/api/wx-login',
    '/api/user-profile',
    '/api/sleep-stats',
    '/api/history',
    '/api/sleep-coach',
]

def check_endpoint(base_url, route, method='GET', body=None):
    """检查单个端点"""
    url = base_url + route
    try:
        if method == 'GET':
            req = urllib.request.Request(url)
        else:
            req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'),
                                         headers={'Content-Type': 'application/json'})
        req.add_header('User-Agent', 'AuthCheck/1.0')
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            body = resp.read().decode('utf-8')
            return True, status, len(body)
    except urllib.error.HTTPError as e:
        return False, e.code, str(e.reason)
    except (urllib.error.URLError, socket.timeout, ConnectionRefusedError) as e:
        return False, 0, str(e)[:100]

def check(base_url, label):
    print(f'  [{label}]')
    all_ok = True
    for route in AUTH_ROUTES:
        ok, status, info = check_endpoint(base_url, route)
        icon = '[OK]' if ok else '[FAIL]'
        detail = f'HTTP {status}' if ok else f'({status}) {info}'
        print(f'    {icon} {route:25s} {detail}')
        if not ok:
            all_ok = False
    return all_ok

def main():
    print('=== 微信登录状态检测 ===')
    local_ok = check(LOCAL_URL, '本地 localhost:8090')
    
    if '--remote' in sys.argv:
        remote_ok = check(REMOTE_URL, '远程 82.156.208.245:8090')
    else:
        remote_ok = True
    
    overall = local_ok and remote_ok
    status_icon = '[OK]' if overall else '[FAIL]'
    status_text = '通过' if overall else '有故障'
    print(f'\n  {status_icon} 整体状态: {status_text}')
    
    if '--check-only' not in sys.argv and not overall:
        sys.exit(1)

if __name__ == '__main__':
    main()
