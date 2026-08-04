"""扫描dev_tools所有工具的头信息，输出结构化清单"""
import os, re

base = r'D:\AISleepGen_Optimized\dev_tools'
output = []

for root, dirs, files in os.walk(base):
    dirname = os.path.basename(root)
    if dirname == 'archive':
        continue
    for f in sorted(files):
        if not f.endswith('.py') or f.startswith('_'):
            continue
        fpath = os.path.join(root, f)
        try:
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as fh:
                content = fh.read(3000)
        except:
            content = ''

        # Extract docstring
        doc_match = re.search(r'"""(.+?)"""', content, re.DOTALL)
        doc = doc_match.group(1).strip().split('\n')[0] if doc_match else '(无文档)'

        # Extract principle keywords
        keywords = []
        for kw in ['核心', '原理', '检测', 'AST', '正则', '编译', 'HTTP', 'sqlite', 'JSON', 
                   'ffmpeg', 'spectrum', 'checksum', 'hash', 'token', 'API', 'urlib',
                   '滑动窗口', '速率限制', '分层分流', '卡方', '回归', '谱分析']:
            if kw in content:
                keywords.append(kw)

        # Extract import dependencies
        imports = re.findall(r'^import (\w+)|^from (\w+)', content, re.MULTILINE)
        import_names = sorted(set(i[0] if i[0] else i[1] for i in imports if i[0] or i[1]))

        # File size and line count
        lines = content.count('\n') + 1
        size_kb = os.path.getsize(fpath) / 1024

        output.append({
            'category': dirname,
            'name': f.replace('.py', ''),
            'file': f'{dirname}/{f}',
            'desc': doc[:150],
            'lines': lines,
            'size_kb': round(size_kb, 1),
            'imports': ', '.join(import_names[:8]),
            'keywords': ', '.join(keywords[:5]),
        })

# Print structured output
print(f'| 类别 | 工具名 | 行数 | 大小 | 核心依赖 | 功能 |')
print(f'|------|--------|------|------|----------|------|')
for t in output:
    print(f'| {t["category"]} | {t["name"]} | {t["lines"]} | {t["size_kb"]}KB | {t["imports"][:40]} | {t["desc"][:100]} |')

print(f'\n总计: {len(output)} 个工具')
