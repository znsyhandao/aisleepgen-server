"""检查 deepseek_proxy.py 的 import 情况"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

f = r'D:\AISleepGen_Optimized\deepseek_proxy.py'
with open(f, 'r', encoding='utf-8') as fh:
    lines = fh.readlines()

# 检查是否有 import sys
for i, line in enumerate(lines[:20]):
    print('L{}: {}'.format(i+1, line.rstrip()[:100]))

print()
has_sys = any('import sys' in l for l in lines[:50])
print('Has import sys:', has_sys)
