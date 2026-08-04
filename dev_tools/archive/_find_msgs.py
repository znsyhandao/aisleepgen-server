import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# system_content 后面找 messages 组装
in_section = False
for i, line in enumerate(lines):
    if 'system_content = f' in line:
        in_section = True
    if in_section and "messages = [" in line:
        for j in range(i, min(i+20, len(lines))):
            print(f'{j+1}: {lines[j].rstrip()[:150]}')
        break
