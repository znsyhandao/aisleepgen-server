# -*- coding: utf-8 -*-
"""
前后端接口契约检查器
检查 dp_router.py/asyncio_server.py 中定义的路由 vs 前端.js文件中调用的API
自动检测：
  1. 后端定义了但前端没调用的路由（僵尸路由）
  2. 前端调用了但后端没定义的路由（404隐患）
  3. 请求方法不一致（GET vs POST）

用法:
  python api_contract_check.py                # 检查所有
  python api_contract_check.py --check-only   # 只检查不报错退出
  python api_contract_check.py --details      # 显示详细匹配信息

返回码: 0=一致  1=有不一致
"""
import os, re, sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(PROJECT_DIR) if os.path.exists(os.path.join(os.path.dirname(PROJECT_DIR), 'skill.py')) else PROJECT_DIR

# 后端路由源文件
ROUTE_SOURCES = ['dp_router.py', 'asyncio_server.py', 'deepseek_proxy.py']
# 前端文件目录
FRONTEND_DIRS = ['miniprogram', 'frontend', 'web', 'pages']  
FRONTEND_EXTS = ['.js', '.wxml', '.html', '.ts', '.vue']

IGNORE_DIRS = {'__pycache__', '.git', 'venv', 'node_modules', '.surgical_backups', 'memory'}

def banner(msg):
    print(f'\n{"="*55}')
    print(f'  {msg}')
    print(f'{"="*55}')

def extract_backend_routes():
    """从后端源文件提取路由定义"""
    routes = {}  # {route: methods_set}
    
    for fname in ROUTE_SOURCES:
        fpath = os.path.join(PROJECT_DIR, fname)
        if not os.path.exists(fpath):
            continue
        
        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        # 匹配各种路由定义模式
        patterns = [
            # @route('/api/xxx') 装饰器
            r"""@route\s*\(\s*['"](/api/[^'"]+)['"]\s*\)""",
            # @app.get('/api/xxx') / @app.post() 等
            r"""@app\.(get|post|put|delete)\s*\(\s*['"](/api/[^'"]+)['"]\s*\)""",
            # add_route('/api/xxx', handler)
            r"""add_route\s*\(\s*['"](/api/[^'"]+)['"]""",
            # Route('GET', '/api/xxx')
            r"""Route\s*\(\s*['"](GET|POST|PUT|DELETE)['"]\s*,\s*['"](/api/[^'"]+)['"]""",
            # self.routes = { '/api/xxx': handler }
            r"""['"](/api/[^'"]+)['"]\s*:""",
            # def handle_xxx 通过函数名推断
            r"""def (handle_[a-z_]+)""",
            # 路由注册 dict key
            r"""['"](/api/[^'"]+)['"]""",
        ]
        
        for pat in patterns:
            for m in re.finditer(pat, content):
                if m.lastindex >= 2:
                    route = m.group(2)
                    method = m.group(1).upper() if m.group(1).upper() in ('GET','POST','PUT','DELETE') else None
                else:
                    route = m.group(1)
                    method = None
                    # Check if this looks like a URL pattern
                    if not route.startswith('/api/'):
                        continue
                
                if route not in routes:
                    routes[route] = {'methods': set(), 'source': fname}
                if method:
                    routes[route]['methods'].add(method)
    
    return routes

def extract_frontend_api_calls():
    """从前端文件提取API调用"""
    calls = []  # [(file, line, route, method)]
    search_dirs = [PROJECT_DIR]
    for d in FRONTEND_DIRS:
        p = os.path.join(PROJECT_DIR, d)
        if os.path.isdir(p):
            search_dirs.append(p)
    
    api_pattern = re.compile(r"""['"](/api/[a-zA-Z0-9_/\-]+)['"]""")
    
    for sd in search_dirs:
        for root, dirs, files in os.walk(sd):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith('.')]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in FRONTEND_EXTS:
                    continue
                
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    lines = content.split('\n')
                except:
                    continue
                
                rel_path = os.path.relpath(fpath, PROJECT_DIR)
                
                for i, line in enumerate(lines):
                    for m in api_pattern.finditer(line):
                        route = m.group(1)
                        # 从上下文判断HTTP方法
                        line_lower = line.lower()
                        method = None
                        if 'wx.request' in line_lower:
                            method_match = re.search(r"method\s*:\s*[\x27\x22](GET|POST|PUT|DELETE)", line_lower)
                            if method_match:
                                method = method_match.group(1)
                        elif 'fetch(' in line_lower or 'axios.' in line_lower:
                            method_match = re.search(r'\b(get|post|put|delete)\b', line_lower)
                            if method_match:
                                method = method_match.group(1).upper()
                        
                        calls.append({
                            'file': rel_path,
                            'line': i + 1,
                            'route': route,
                            'method': method,
                        })
    
    return calls

def check():
    banner('前后端接口契约检查')
    
    backend_routes = extract_backend_routes()
    frontend_calls = extract_frontend_api_calls()
    
    if not backend_routes:
        print('  [WARN] 未找到后端路由定义 (检查 ROUTE_SOURCES 文件是否存在)')
        return True
    
    print(f'  后端路由: {len(backend_routes)} 个')
    print(f'  前端API调用: {len(frontend_calls)} 处')
    print()
    
    # 1. 前端调用了但后端没定义的 (最严重)
    frontend_routes = set(c['route'] for c in frontend_calls)
    backend_route_set = set(backend_routes.keys())
    
    undefined_routes = frontend_routes - backend_route_set
    if undefined_routes:
        print(f'  [FAIL] 前端调用但后端未定义 ({len(undefined_routes)} 个):')
        for route in sorted(undefined_routes):
            # 找到第一个调用的位置
            locs = [c for c in frontend_calls if c['route'] == route]
            for loc in locs[:2]:
                print(f'    {loc["file"]}:{loc["line"]}  {route}')
    
    # 2. 后端定义了但前端没调用的 (僵尸路由/老接口)
    unused_routes = backend_route_set - frontend_routes
    if unused_routes:
        print(f'\n  [WARN] 后端定义但前端未调用 ({len(unused_routes)} 个):')
        for route in sorted(unused_routes)[:10]:
            print(f'    {route} ({backend_routes[route]["source"]})')
        if len(unused_routes) > 10:
            print(f'    ... 还有 {len(unused_routes) - 10} 个')
    
    # 3. 方法不一致检测 (强匹配)
    method_mismatches = []
    for call in frontend_calls:
        if call['method'] and call['route'] in backend_routes:
            backend_methods = backend_routes[call['route']]['methods']
            if backend_methods and call['method'] not in backend_methods:
                method_mismatches.append(call)
    
    if method_mismatches:
        print(f'\n  [FAIL] 请求方法不一致 ({len(method_mismatches)} 处):')
        for m in method_mismatches[:5]:
            backend_methods_str = ','.join(sorted(backend_routes[m['route']]['methods']))
            print(f'    {m["file"]}:{m["line"]}  {m["route"]}  (前端: {m["method"]}, 后端: {backend_methods_str})')
    
    # 输出统计
    total_issues = len(undefined_routes) + len(method_mismatches)
    if total_issues == 0:
        print(f'  ✅ 接口契约一致')
        return True
    else:
        print(f'\n  ❌ {total_issues} 个问题')
        if undefined_routes:
            print(f'     - {len(undefined_routes)} 个前端调用了但后端没定义')
        if method_mismatches:
            print(f'     - {len(method_mismatches)} 个方法不一致')
        return False

if __name__ == '__main__':
    ok = check()
    if '--check-only' not in sys.argv and not ok:
        sys.exit(1)
