import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('def _update_user_profile')
sub = content[idx:idx+4000]
# 找所有profile['latest']或profile["latest"]
import re
for m in re.finditer(r"profile\s*\[\s*['\"]latest['\"]\s*\]", sub):
    print(f'Offset {m.start()}: {sub[max(0,m.start()-200):m.start()+200]}')
    print('===')
