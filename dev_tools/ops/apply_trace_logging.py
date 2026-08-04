#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_trace_logging.py v2 — 注入 trace logging 到 deepseek_proxy.py

注入 3 个探针（都用 sys.stderr.write 避免缓冲）：
1. 入口：trace_id + openid
2. history_context 构建后：是否含睡眠数据
3. 发送前：system_content 完整性
"""

import sys, os, shutil, datetime, py_compile

FILE = r'D:\AISleepGen_Optimized\deepseek_proxy.py'
BACKUP_DIR = r'D:\AISleepGen_Optimized\.surgical_backups'
TRACE_IMPORT = 'import sys\n'

print('[TraceLog] Target:', FILE)

os.makedirs(BACKUP_DIR, exist_ok=True)
ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
bak = os.path.join(BACKUP_DIR, 'deepseek_proxy.py_' + ts + '.bak')
shutil.copy2(FILE, bak)
print('[TraceLog] Backup:', bak)

with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# 确保顶部有 import sys
if not content.startswith('import sys\n') and not content.startswith('import sys'):
    # 找到第一个 import 行后插入
    first_import = content.find('\nimport ')
    if first_import > 0:
        insert_pos = first_import + 1
        content = content[:insert_pos] + TRACE_IMPORT + content[insert_pos:]
        # 但我们会补全，不影响编译
    # 如果根本没有 import，加到文件头
    elif '\n' in content[:10]:
        content = TRACE_IMPORT + content
    print('[TraceLog] + added import sys at top')

# ===== 注入 1: 入口 trace_id + openid =====
marker1 = 'openid = self._get_openid(data)\n\n        # \u6bcf\u65e5\u61d2\u4f18\u5316'
replacement1 = '''        openid = self._get_openid(data)

        # [Trace] \u6570\u636e\u6d41\u8ffd\u8e2a
        _trace_id = datetime.now().strftime('%H%M%S') + '_' + os.urandom(3).hex()
        _trace_msg_preview = (data.get('message','') or '')[:80]
        _trace_hist_len = len(data.get('history',[]) or [])
        sys.stderr.write('[' + _trace_id + '] entry: openid=' + str(openid) + ' msg="' + _trace_msg_preview.replace(chr(10),' ').replace(chr(13),'') + '" hist=' + str(_trace_hist_len) + '\\n')

        # \u6bcf\u65e5\u61d2\u4f18\u5316'''

assert marker1 in content, 'marker1 NOT FOUND'
content = content.replace(marker1, replacement1, 1)
print('[TraceLog] + probe 1: entry trace')

# ===== 注入 2: history_context 构建后 =====
marker2 = 'history_context, expert_history = _build_history_context(openid)\n\n        # ===== \u524d\u6cbf\u8bc1\u636e\u6ce8\u5165'
replacement2 = '''history_context, expert_history = _build_history_context(openid)

        # [Trace] history_context \u5feb\u7167
        _trace_ctx = history_context or ''
        _trace_has_sleep = any(k in _trace_ctx for k in ['\u4e0a\u5e8a', '\u8d77\u5e8a', '\u5165\u7761', '\u9192', '\u603b\u65f6\u957f', '\u7761\u7720\u4e60\u60ef', '\u8bc4\u5206', '\u57fa\u7ebf', '\u538b\u529b']) if _trace_ctx else False
        if _trace_ctx and _trace_has_sleep:
            for _tl in _trace_ctx.split('\\n'):
                if any(k in _tl for k in ['\u7761\u7720', '\u8bc4\u5206', '\u538b\u529b', '\u4f5c\u606f', '\u4e3b\u8bc9', '\u57fa\u7ebf']):
                    sys.stderr.write('[' + _trace_id + '] >> ' + _tl.strip() + '\\n')
        elif _trace_ctx and not _trace_has_sleep:
            sys.stderr.write('[' + _trace_id + '] >> no sleep data in context (first 200): ' + _trace_ctx[:200].replace(chr(10),' ') + '\\n')
        else:
            sys.stderr.write('[' + _trace_id + '] >> EMPTY CONTEXT\\n')
        sys.stderr.write('[' + _trace_id + '] ctx len=' + str(len(_trace_ctx)) + ' has_data=' + str(_trace_has_sleep) + '\\n')

        # ===== \u524d\u6cbf\u8bc1\u636e\u6ce8\u5165'''

assert marker2 in content, 'marker2 NOT FOUND'
content = content.replace(marker2, replacement2, 1)
print('[TraceLog] + probe 2: history_context trace')

# ===== 注入 3: messages 构建后 =====
marker3 = "messages = [{'role': 'system', 'content': system_content}]\n\n        # \u6dfb\u52a0\u5386\u53f2\u5bf9\u8bdd"
replacement3 = "messages = [{'role': 'system', 'content': system_content}]\n\n        # [Trace] \u53d1\u9001\u524d\n        _trace_sc = system_content or ''\n        _trace_has_ud = any(k in _trace_sc for k in ['\u4e0a\u5e8a', '\u8d77\u5e8a', '\u5165\u7761', '\u9192', '\u603b\u65f6\u957f', '\u7528\u6237\u57fa\u7ebf', '\u7761\u7720\u4e60\u60ef'])\n        sys.stderr.write('[' + _trace_id + '] send sys_len=' + str(len(_trace_sc)) + ' hist=' + str(len(history)) + ' intv=' + str(intervention_mode) + ' has_ud=' + str(_trace_has_ud) + '\\n')\n        if _trace_has_ud:\n            for _tl in _trace_sc.split('\\n'):\n                if any(k in _tl for k in ['\u7528\u6237\u6570\u636e', '\u7528\u6237\u753b\u50cf', '\u7528\u6237\u57fa\u7ebf', '\u4e0a\u5e8a', '\u8d77\u5e8a']):\n                    sys.stderr.write('[' + _trace_id + ']   sc:' + _tl.strip()[:150] + '\\n')\n\n        # \u6dfb\u52a0\u5386\u53f2\u5bf9\u8bdd"

assert marker3 in content, 'marker3 NOT FOUND'
content = content.replace(marker3, replacement3, 1)
print('[TraceLog] + probe 3: pre-send trace')

# 回写
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

# 编译验证
try:
    py_compile.compile(FILE, doraise=True)
    print('[TraceLog] [OK] Compile passed')
except py_compile.PyCompileError as e:
    print('[TraceLog] [FAIL] Compile error, rolling back...')
    shutil.copy2(bak, FILE)
    sys.exit(1)

delta = content.count('\n') - open(bak, 'r', encoding='utf-8').read().count('\n')
print('[TraceLog] [OK] Lines added:', delta)
print('[TraceLog] Done. Rollback: copy "' + bak + '" "' + FILE + '"')
