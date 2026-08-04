with open('aisleepgen_tool.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

found_help = False
found_route = False

for i, line in enumerate(lines):
    if 'fix remaining-gaps' in line and not found_help:
        lines.insert(i+1, '  ops pre-op-js          前端JS/JSON预检（括号/双逗号/语法）\n')
        found_help = True
        break

for i, line in enumerate(lines):
    if "('ops', 'pre')" in line and not found_route:
        lines.insert(i+1, "    ('ops', 'pre-op-js'):         ('ops', 'pre_op_js.py'),\n")
        found_route = True
        break

with open('aisleepgen_tool.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

import py_compile
py_compile.compile('aisleepgen_tool.py', doraise=True)
print('OK')
