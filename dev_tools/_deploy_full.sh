#!/bin/bash
# 收集 deepseek_proxy.py imports 的所有本地模块
cd /mnt/d/AISleepGen_Optimized
# 用 Python 扫描真实依赖
python3 -c "
import ast, sys
with open('deepseek_proxy.py', 'r') as f:
    tree = ast.parse(f.read())
imports = set()
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom) and node.module:
        imports.add(node.module + '.py')
    elif isinstance(node, ast.Import):
        for alias in node.names:
            if '.' not in alias.name:
                imports.add(alias.name + '.py')
# 只输出本地存在的文件
local = [i for i in sorted(imports) if '__' not in i]
for f in local:
    try:
        open(f).close()
        print(f)
    except: pass
" | while read f; do
  echo "Copying $f"
  scp -o StrictHostKeyChecking=no "$f" ubuntu@82.156.208.245:/opt/aisleepgen/
done
