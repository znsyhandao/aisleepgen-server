import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('D:/AISleepGen_Optimized/deepseek_proxy.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if '[Trace:' in line or '_trace_' in line:
        print('L{}: {}'.format(i, line.rstrip()[:150]))
