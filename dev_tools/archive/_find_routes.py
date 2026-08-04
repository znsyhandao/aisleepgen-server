import sys, re
sys.stdout.reconfigure(encoding='utf-8')
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()
# 找所有路由路径字符串（在 self.path 判断中出现的）
paths = re.findall(r"(?:self\.path\s*==\s*['\"]|self\.path\.startswith\(['\"])([^'\"]+)", content)
for p in sorted(set(paths)):
    print(p)
