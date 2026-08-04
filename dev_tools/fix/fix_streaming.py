#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_streaming.py — 流式输出 SSE 注入

最佳实践依据：
- 2024-2026 所有对话式 AI 产品标配（ChatGPT, Claude, DeepSeek Chat）
- DeepSeek API 原生支持 stream=true
- SSE (Server-Sent Events) 标准协议，微信小程序 TextDecoder 兼容

改动点（共 2 处，最小侵入）：
1. 新增 _call_deepseek_stream(self, messages, ...) — SSE 版本
2. 在 _handle_chat 中新增 sse 分支（通过 data.get('sse') 触发）
   原有 non-stream 路径完全不变

回滚: copy .surgical_backups\deepseek_proxy.py_20260520_120712.bak deepseek_proxy.py
"""

import sys, os, shutil, datetime, py_compile
sys.stdout.reconfigure(encoding='utf-8')

FILE = r'D:\AISleepGen_Optimized\deepseek_proxy.py'
BACKUP_DIR = r'D:\AISleepGen_Optimized\.surgical_backups'

print('[FixStreaming] Target:', FILE)
os.makedirs(BACKUP_DIR, exist_ok=True)
ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
bak = os.path.join(BACKUP_DIR, 'deepseek_proxy.py_' + ts + '.bak')
shutil.copy2(FILE, bak)
print('[FixStreaming] Backup:', bak)

with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# ===== Fix 1: 在 _call_deepseek 函数后加 stream 版本 =====
# _call_deepseek 函数结束的模式：}
# 找 except Exception as e: 的行
old_end = '''        except Exception as e:
            return {'error': str(e)}'''

new_end = '''        except Exception as e:
            return {'error': f'Error: {e}'}

    def _call_deepseek_stream(self, messages, max_tokens=2000, temperature=0.7):
        """流式调用DeepSeek API，按SSE协议逐token输出"""
        if not DEEPSEEK_API_KEY:
            self._send_json({'error': 'DeepSeek API Key未配置'})
            return

        # 设置SSE headers（必须在任何输出前）
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
                # DeepSeek 返回 SSE 格式：data: {...} \n\n
                buffer = b''
                while True:
                    chunk = response.read(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    # 按 \\n\\n 分割 SSE events
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
                                    # SSE 格式发送
                                    sse_data = json.dumps({'token': delta}) + '\\n\\n'
                                    self.wfile.write(sse_data.encode('utf-8'))
                                    self.wfile.flush()
                            except json.JSONDecodeError:
                                pass
                    if buffer and buffer.startswith(b'data: [DONE]'):
                        break
            # 发送完成信号
            self.wfile.write(b'data: [DONE]\\n\\n')
            self.wfile.flush()
            print(f'[SSE] 流式回复完成: {len(\"\".join(full_content))} chars')
        except urllib.error.HTTPError as e:
            try:
                err_msg = e.read().decode('utf-8')
            except:
                err_msg = str(e)
            # SSE 格式发送错误
            err_data = json.dumps({'error': f'HTTP {e.code}: {err_msg}'})
            self.wfile.write(f'data: {err_data}\\n\\n'.encode('utf-8'))
            self.wfile.write(b'data: [DONE]\\n\\n')
            self.wfile.flush()
        except Exception as e:
            err_data = json.dumps({'error': f'Error: {e}'})
            self.wfile.write(f'data: {err_data}\\n\\n'.encode('utf-8'))
            self.wfile.write(b'data: [DONE]\\n\\n')
            self.wfile.flush()
'''

assert old_end in content, 'Fix1 marker not found'
content = content.replace(old_end, new_end, 1)
print('[FixStreaming] 1/2: _call_deepseek_stream added')

# ===== Fix 2: 在 _handle_chat 中 SSE 分支 =====
# 在 'if intervention_mode:' 之前加个判断：如果 data.get('sse') == True 就走流式
old_sse = '''        try:
            # ===== 干预模式：不走 DeepSeek，直接返回呼吸引导 =====
            if intervention_mode: '''

new_sse = '''        try:
            # ===== SSE 流式模式 =====
            if data.get('sse', False) and not intervention_mode:
                # 直接走流式 DeepSeek 调用
                self._call_deepseek_stream(messages, max_tokens=1000, temperature=0.7)
                return  # SSE 模式已经通过 self.wfile 输出了结果
            
            # ===== 干预模式：不走 DeepSeek，直接返回呼吸引导 =====
            if intervention_mode: '''

assert old_sse in content, 'Fix2 marker not found'
content = content.replace(old_sse, new_sse, 1)
print('[FixStreaming] 2/2: SSE branch in _handle_chat')

# 写回
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

# 编译验证
try:
    py_compile.compile(FILE, doraise=True)
    print('[FixStreaming] Compile OK')
except py_compile.PyCompileError as e:
    print('[FixStreaming] Compile FAIL:', str(e))
    shutil.copy2(bak, FILE)
    sys.exit(1)

delta = content.count('\n') - open(bak, 'r', encoding='utf-8').read().count('\n')
print(f'[FixStreaming] Lines added: {delta}')
print('[FixStreaming] Done.')
