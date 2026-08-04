import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 给 do_POST 加上顶层 try-catch
old = """    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_type = self.headers.get('Content-Type', '')"""

new = """    def do_POST(self):
        try:
            self._do_post_inner()
        except Exception as _post_e:
            import traceback as _tb
            _tb.print_exc()
            print(f'[do_POST] 未捕获异常: {_post_e}')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                self.wfile.write(json.dumps({'error': 'internal_error', 'detail': str(_post_e)}).encode('utf-8'))
            except: pass

    def _do_post_inner(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_type = self.headers.get('Content-Type', '')"""

content = content.replace(old, new, 1)

# 2. 添加 stop-breathing 路由（返回空成功即可）
old = """        elif path == '/api/goodnight':
            self._handle_goodnight(data)"""

new = """        elif path == '/api/stop-breathing':
            self._send_json({'success': True})
        elif path == '/api/goodnight':
            self._handle_goodnight(data)"""

content = content.replace(old, new, 1)

# 3. 给 do_GET 也加 try-catch
old = """    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path"""

new = """    def do_GET(self):
        try:
            self._do_get_inner()
        except Exception as _get_e:
            import traceback as _tb
            _tb.print_exc()
            print(f'[do_GET] 未捕获异常: {_get_e}')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                self.wfile.write(json.dumps({'error': 'internal_error', 'detail': str(_get_e)}).encode('utf-8'))
            except: pass

    def _do_get_inner(self):
        parsed = urlparse(self.path)
        path = parsed.path"""

content = content.replace(old, new, 1)

with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('OK - do_POST/do_GET 加 try-catch, stop-breathing 路由')
