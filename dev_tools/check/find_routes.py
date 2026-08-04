"""
find_routes.py — API 路由表扫描

从 deepseek_proxy.py 中用正则提取所有 if-elif 路由路径定义，
输出完整路由清单。
用法: python dev_tools/check/find_routes.py
"""
import sys, re
sys.stdout.reconfigure(encoding='utf-8')
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()
# 找所有路由路径字符串（在 self.path 判断中出现的）
paths = re.findall(r"(?:self\.path\s*==\s*['\"]|self\.path\.startswith\(['\"])([^'\"]+)", content)
for p in sorted(set(paths)):
    print(p)
