import ast
with open(r'D:\AISleepGen_Optimized\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    tree = ast.parse(f.read())

cls = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == 'ProxyHandler'][0]
print('Class body items:', len(cls.body))
print('Last 3 function defs:')
for item in cls.body[-3:]:
    name = getattr(item, 'name', '?')
    print(f'  L{item.lineno}: {type(item).__name__} {name}')

last_item = cls.body[-1]
print(f'\nLast item end_lineno: {last_item.end_lineno}')
print(f'My handlers at line ~6177: {6177 - last_item.end_lineno} lines OUTSIDE class')

# What's the actual last line of class?
for line_no in range(last_item.end_lineno, min(last_item.end_lineno + 5, 6185)):
    with open(r'D:\AISleepGen_Optimized\deepseek_proxy.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    if line_no < len(lines):
        print(f'  L{line_no+1}: {lines[line_no].rstrip()[:100]}')
