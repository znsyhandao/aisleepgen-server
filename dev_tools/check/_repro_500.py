import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.getcwd())

os.chdir('D:\\AISleepGen_Optimized')

class Dummy:
    """模拟 _set_headers 等"""
    def __init__(self):
        self.headers = {}
        self.wfile = type('W', (), {'write': lambda s,x: None, 'flush': lambda: None})()

    def _set_headers(self, status=200):
        pass
    def _send_json(self, data):
        print('send_json:', json.dumps(data, ensure_ascii=False)[:200])
    def send_response(self, code):
        print('send_response:', code)
    def send_header(self, k, v):
        pass
    def end_headers(self):
        pass
    def log_request(self, code='-', size='-'):
        pass
    @property
    def requestline(self):
        return 'POST /api/chat HTTP/1.1'

dummy = Dummy()
ProxyHandler = type(dummy.__class__.__name__, (object,), {})

# 直接从模块导入
import importlib.util
spec = importlib.util.spec_from_file_location('deepseek_proxy', 'D:\\AISleepGen_Optimized\\deepseek_proxy.py')
mod = importlib.util.module_from_spec(spec)

# 修改全局变量以匹配
mod.requestline = 'POST /api/chat HTTP/1.1'
mod.headers = {'Content-Type': 'application/json'}
mod.command = 'POST'
mod.path = '/api/chat'

try:
    # 导入前设置 __file__
    spec.loader.exec_module(mod)
    
    # 调用 _build_history_context
    ctx = mod._build_history_context('default')
    print('OK:', ctx[0][:100] if ctx[0] else 'empty')
except Exception as e:
    import traceback
    traceback.print_exc()
