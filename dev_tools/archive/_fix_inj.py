import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复 _handle_update_profile 中 profile.latest 直接写入后，无条件画像注入代码的读取
# 找到 _inj_sd = _inj_latest.get('sleep_data', {}) or _inj_latest 这段
old = """        _inj_sd = _inj_latest.get('sleep_data', {}) or _inj_latest"""
new = """        _inj_sd = _inj_latest.get('sleep_data', {}) or _inj_latest
        if not _inj_sd.get('bedtime') and _inj_latest.get('bedtime'):
            _inj_sd = _inj_latest"""

content = content.replace(old, new, 1)
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('OK')
