import py_compile, shutil
with open('.surgical_backups/deepseek_proxy.py_20260520_120712.bak', 'r', encoding='utf-8') as f:
    orig = f.read()

changes = []

# ===== Fix 1: 加 _call_deepseek_stream 方法 =====
old1 = '''        except Exception as e:
            return {'error': str(e)}'''

new1 = '''        except Exception as e:
            return {'error': str(e)}

    def _call_deepseek_stream(self, messages, max_tokens=2000, temperature=0.7):
        """流式调用DeepSeek API，按SSE协议逐token输出"""
        if not DEEPSEEK_API_KEY:
            self._send_json({'error': 'DeepSeek API Key未配置'})
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        payload = {
            'model': 'deepseek-chat',
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'stream': True
        }
        req = urllib.request.Request(
            f'{DEEPSEEK_BASE_URL}/chat/completions',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            },
            method='POST'
        )
        try:
            full_content = []
            with urllib.request.urlopen(req, timeout=120) as response:
                buffer = b''
                while True:
                    chunk = response.read(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    while b'\\n\\n' in buffer:
                        line, buffer = buffer.split(b'\\n\\n', 1)
                        if line.startswith(b'data: '):
                            data_str = line[6:].decode('utf-8').strip()
                            if data_str == '[DONE]':
                                break
                            try:
                                data_json = json.loads(data_str)
                                delta = data_json.get('choices', [{}])[0].get('delta', {}).get('content', '')
                                if delta:
                                    full_content.append(delta)
                                    sse_data = json.dumps({'token': delta}) + '\\n\\n'
                                    self.wfile.write(sse_data.encode('utf-8'))
                                    self.wfile.flush()
                            except json.JSONDecodeError:
                                pass
                    if buffer and buffer.startswith(b'data: [DONE]'):
                        break
            self.wfile.write(b'data: [DONE]\\n\\n')
            self.wfile.flush()
        except urllib.error.HTTPError as e:
            try:
                err_msg = e.read().decode('utf-8')
            except:
                err_msg = str(e)
            self.wfile.write(('data: ' + json.dumps({'error': 'HTTP ' + str(e.code) + ': ' + err_msg}) + '\\n\\n').encode('utf-8'))
            self.wfile.write(b'data: [DONE]\\n\\n')
            self.wfile.flush()
        except Exception as e:
            self.wfile.write(('data: ' + json.dumps({'error': str(e)}) + '\\n\\n').encode('utf-8'))
            self.wfile.write(b'data: [DONE]\\n\\n')
            self.wfile.flush()
'''

assert old1 in orig, 'Fix1 marker'
orig = orig.replace(old1, new1, 1)
changes.append('_call_deepseek_stream')

# ===== Fix 2: 路由 + SSE handler =====
old2 = "        elif path == '/api/chat':\n            self._handle_chat(data)\n        elif path == '/api/chat-report':"

new2 = "        elif path == '/api/chat':\n            self._handle_chat(data)\n        elif path == '/api/chat-sse':\n            self._handle_chat_sse(data)\n        elif path == '/api/chat-report':"

assert old2 in orig, 'Fix2 marker'
orig = orig.replace(old2, new2, 1)
changes.append('/api/chat-sse route')

# ===== Fix 3: _handle_chat_sse 方法 =====
sse_handler = '''
    def _handle_chat_sse(self, data):
        """SSE流式AI对话（独立路由）"""
        openid = self._get_openid(data)
        user_message = data.get('message', '')
        history = data.get('history', [])
        
        profile = _load_user_profile(openid)
        latest = profile.get('latest', {})
        context_lines = []
        
        if isinstance(latest, dict) and latest.get('sleep_data'):
            sd = latest['sleep_data']
            bt = sd.get('bedtime', '?')
            wt = sd.get('wake_time', '?')
            la = sd.get('sleep_latency', '?')
            at = sd.get('awake_times', '?')
            td = sd.get('total_duration', '?')
            sc = latest.get('score', '?')
            mi = profile.get('user_info', {}).get('main_issue', '')
            context_lines.append('base: bed=' + str(bt) + ' wake=' + str(wt) + ' latency=' + str(la) + ' woke=' + str(at) + ' dur=' + str(td))
            if sc:
                context_lines.append('score=' + str(sc))
            if mi:
                context_lines.append('issue=' + str(mi))
        
        system_content = 'You are a warm professional sleep assistant.\\n'
        if context_lines:
            system_content += 'User sleep data:\\n' + '\\n'.join(context_lines)
            system_content += '\\nUse this data directly instead of asking.'
        
        messages = [{'role': 'system', 'content': system_content}]
        for msg in history:
            messages.append(msg)
        messages.append({'role': 'user', 'content': user_message})
        
        self._call_deepseek_stream(messages)
'''

idx = orig.find('\n    def _handle_clinical_report(self, data):')
assert idx > 0, 'Fix3 marker'
orig = orig[:idx] + sse_handler + orig[idx:]
changes.append('_handle_chat_sse handler')

# 写回
with open('deepseek_proxy.py', 'w', encoding='utf-8') as f:
    f.write(orig)

try:
    py_compile.compile('deepseek_proxy.py', doraise=True)
    print('COMPILE OK')
except py_compile.PyCompileError as e:
    print('COMPILE FAIL:', str(e))

for c in changes:
    print('  +', c)
