"""生成完整的中文工具手册（不依赖PowerShell编码）"""
import os, re

base = r'D:\AISleepGen_Optimized\dev_tools'
tools = []

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
                content = fh.read()
        except:
            content = ''

        # Full docstring
        doc_match = re.search(r'"""(.+?)"""', content, re.DOTALL)
        doc = doc_match.group(1).strip() if doc_match else '(无文档说明)'

        # Usage info
        usage = ''
        u_match = re.search(r'(用法|usage)[：:](.+?)[\r\n]', content, re.IGNORECASE)
        if u_match:
            usage = u_match.group(2).strip()

        # Imports
        imports = re.findall(r'^import (\w+)|^from (\w+)', content, re.MULTILINE)
        import_names = sorted(set(i[0] if i[0] else i[1] for i in imports))

        # File size and lines
        lines = content.count('\n') + 1
        size_kb = os.path.getsize(fpath) / 1024

        tools.append({
            'cat': dirname,
            'name': f.replace('.py', ''),
            'doc': doc,
            'usage': usage,
            'imports': import_names,
            'lines': lines,
            'size': round(size_kb, 1),
        })

# Generate markdown
out = []
out.append('# aisleepgen_tool 完整工具手册')
out.append('')
out.append(f'入口: `python D:\\AISleepGen_Optimized\\aisleepgen_tool.py <类别> <命令>`')
out.append(f'目录: `D:\\AISleepGen_Optimized\\dev_tools/`')
out.append(f'工具总数: {len(tools)}')
out.append('')

cats = ['audit', 'check', 'test', 'monitor', 'ops', 'fix']
cat_names = {
    'audit': '🔴 审核层 — 审计、分析、评估',
    'check': '🟡 检查层 — 静态检查、诊断、检测',
    'test': '🟢 测试层 — API测试、冒烟、验证',
    'monitor': '🟣 监控层 — 运行时监控、数据漂移',
    'ops': '🔵 运维层 — 备份、部署、转换',
    'fix': '⚪ 修复层 — 自动修复代码问题',
}

def extract_keywords(doc):
    """从文档中提取原理关键词"""
    kw_map = {
        'AST': '抽象语法树',
        '正则': '正则表达式',
        '编译': 'Python字节码编译',
        'HTTP': 'HTTP请求',
        'JSON': 'JSON解析',
        'sha256': 'SHA256哈希',
        '滑动窗口': '滑动窗口算法',
        '速率限制': '速率限制',
        '分层分流': '分层分流',
        '卡方': '卡方检验',
        '回归模型': '回归模型',
        '频谱': '频谱分析',
        'ffmpeg': 'ffmpeg转码',
        'md5': 'MD5校验',
        'AST': '抽象语法树',
    }
    found = []
    for kw, meaning in kw_map.items():
        if kw in doc:
            found.append(f'{kw}({meaning})')
    return found

for cat in cats:
    items = [t for t in tools if t['cat'] == cat]
    if not items:
        continue
    
    out.append(f'## {cat_names[cat]}')
    out.append('')
    
    for t in items:
        out.append(f'### {t["name"]}')
        out.append(f'- **文件**: `dev_tools/{t["cat"]}/{t["name"]}.py` ({t["lines"]}行, {t["size"]}KB)')
        out.append(f'- **命令**: `python aisleepgen_tool.py {t["cat"]} {t["name"]}`')
        
        # 功能描述
        doc_lines = t['doc'].split('\n')
        first_line = doc_lines[0]
        # Try to extract functional description (usually first 1-3 lines)
        func_desc = first_line
        if len(doc_lines) > 1:
            func_desc += ' ' + doc_lines[1][:100]
        out.append(f'- **功能**: {func_desc}')
        
        # Principle
        out.append(f'- **原理**: ')
        # Extract the detailed doc body
        doc_body = '\n'.join(doc_lines[2:]) if len(doc_lines) > 2 else ''
        if doc_body:
            out.append(f'  {doc_body[:200]}')
        else:
            out.append(f'  (详见文件内文档)')
        
        if t['usage']:
            out.append(f'- **用法**: `{t["usage"]}`')
        
        if t['imports']:
            out.append(f'- **核心依赖**: {", ".join(t["imports"][:8])}')
        
        out.append('')

out.append('---')
out.append('*生成时间: 2026-05-20*')

result = '\n'.join(out)

# Write to file
outpath = os.path.join(base, 'TOOL_MANUAL.md')
with open(outpath, 'w', encoding='utf-8') as f:
    f.write(result)
print(f'Written: {outpath} ({len(result)} chars, {len(tools)} tools)')
print('Done.')
