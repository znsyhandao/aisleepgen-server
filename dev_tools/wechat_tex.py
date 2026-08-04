#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LaTeX公式 → 微信公众号 HTML 转换工具
=====================================
用法:
  python wechat_tex.py input.md [-o output.html]

功能:
  1. 自动检测 Markdown 中的 $...$ 和 $$...$$ LaTeX 公式
  2. 用 matplotlib mathtext 渲染为高清 PNG 图片
  3. 图片嵌入为 base64 HTML 内联，零外部依赖
  4. 输出可直接粘贴到微信公众号编辑器

依赖: matplotlib, Pillow, beautifulsoup4 (均已安装)
限制: 不支持 \\begin{align} 等复杂多行环境（会拆成单行公式渲染）
"""

import os, sys, re, base64, io, hashlib, argparse
from bs4 import BeautifulSoup
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# ======================================================================
# 配置
# ======================================================================
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.tex_cache')
DPI = 200
FONT_SIZE = 14
LINE_HEIGHT = 1.8  # em

os.makedirs(CACHE_DIR, exist_ok=True)

# ======================================================================
# LaTeX 渲染引擎
# ======================================================================

def _make_patchwork(latex_chunks):
    """
    将 LaTeX 拆成单段能渲染的小块。
    mathtext 不支持 \\begin{align}、\\text、\\hline 等，
    拆成多个独立 $...$ 分别渲染再拼图。
    """
    # 简单启发式: 看有没有 \begin 或 \text
    simplified = []
    for chunk in latex_chunks:
        # 去除外层 $$ 或 $
        clean = chunk.strip()
        if clean.startswith('$$') and clean.endswith('$$'):
            clean = clean[2:-2].strip()
        elif clean.startswith('$') and clean.endswith('$'):
            clean = clean[1:-1].strip()

        # 检查是否包含不支持的宏
        if re.search(r'\\begin|\\text|\\hline|\\tag|\\label|\\ref', clean):
            # 尝试按 \\ 拆分
            lines = re.split(r'\\\\\\\\|\\\\', clean)
            sub_chunks = []
            for line in lines:
                line = line.strip()
                if line:
                    # 去掉 & 对齐符号
                    line = re.sub(r'&', ' ', line)
                    sub_chunks.append(r'$' + line + r'$')
            simplified.extend(sub_chunks)
        else:
            simplified.append(r'$$' + clean + r'$$')
    return simplified


def render_latex(latex_str, fontsize=FONT_SIZE, dpi=DPI):
    """
    渲染 LaTeX 为 PNG base64 字符串。
    返回 (html_img_tag, width_em, height_em)
    """
    # 缓存 key
    key = hashlib.md5((latex_str + str(fontsize) + str(dpi)).encode()).hexdigest()
    cache_path = os.path.join(CACHE_DIR, key + '.png')

    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            img_data = f.read()
    else:
        # 用 matplotlib 渲染
        fig, ax = plt.subplots(figsize=(1, 1))
        ax.axis('off')

        # 尝试解析
        try:
            text_obj = ax.text(0.5, 0.5, latex_str, fontsize=fontsize,
                               ha='center', va='center',
                               transform=ax.transAxes)
            fig.canvas.draw()
            # 获取精确 bbox
            bbox = text_obj.get_window_extent(renderer=fig.canvas.get_renderer())
            width_px = int(bbox.width) + 10
            height_px = int(bbox.height) + 6
            plt.close(fig)

            # 重新创建精确大小的图片
            fig2, ax2 = plt.subplots(figsize=(width_px / dpi, height_px / dpi))
            ax2.axis('off')
            ax2.text(0.5, 0.5, latex_str, fontsize=fontsize,
                     ha='center', va='center',
                     transform=ax2.transAxes)
            fig2.savefig(cache_path, dpi=dpi, bbox_inches='tight',
                         pad_inches=0.02, transparent=True)
            plt.close(fig2)

            with open(cache_path, 'rb') as f:
                img_data = f.read()
        except Exception as e:
            plt.close('all')
            # 渲染失败，回退：显示纯文本
            clean = re.sub(r'[\$\{\}\\]', '', latex_str)
            return f'<code style="background:#f5f5f5;padding:2px 6px;border-radius:3px;font-size:{fontsize}px">{clean}</code>', 0, 0

    # base64 编码
    b64 = base64.b64encode(img_data).decode('ascii')
    # 真实尺寸（从缓存图片读）
    from PIL import Image
    img = Image.open(io.BytesIO(img_data))
    w_px, h_px = img.size

    # 转成 em（基于 fontsize）
    w_em = round(w_px / fontsize, 1)
    h_em = round(h_px / fontsize, 1)

    # HTML 标签，适合微信编辑器
    # 微信编辑器对 img 尺寸支持有限，用 style 控制
    html = (f'<img src="data:image/png;base64,{b64}" '
            f'style="width:{w_em}em;height:{h_em}em;vertical-align:middle;'
            f'max-width:90%;display:inline-block;" '
            f'alt="formula"/>')

    return html, w_em, h_em


# ======================================================================
# Markdown → 带公式图片的 HTML
# ======================================================================

def md_to_wechat_html(md_text):
    """
    将含 LaTeX 的 Markdown 转为微信公众号适用 HTML。
    """
    lines = md_text.split('\n')
    html_parts = []
    in_code_block = False
    in_math_block = False

    for line in lines:
        # 代码块保护
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            if in_code_block:
                html_parts.append('<pre><code>')
            else:
                html_parts.append('</code></pre>')
            continue

        if in_code_block:
            html_parts.append(line)
            continue

        # 空行
        if not line.strip():
            html_parts.append('<p style="margin:0.5em 0;"><br></p>')
            continue

        # 标题
        if line.startswith('### '):
            html_parts.append(f'<h3 style="font-size:1.1em;margin:1em 0 0.5em 0;">{line[4:]}</h3>')
            continue
        elif line.startswith('## '):
            html_parts.append(f'<h2 style="font-size:1.2em;margin:1em 0 0.5em 0;">{line[3:]}</h2>')
            continue
        elif line.startswith('# '):
            html_parts.append(f'<h1 style="font-size:1.3em;margin:1em 0 0.5em 0;">{line[2:]}</h1>')
            continue

        # 列表
        if re.match(r'^\s*[\-\*]\s', line):
            text = re.sub(r'^\s*[\-\*]\s', '', line)
            html_parts.append(f'<li style="margin:0.3em 0;">{text}</li>')
            continue

        # 表格行 (简单跳过表头分隔行)
        if re.match(r'^\|.+\|$', line.strip()):
            if re.match(r'^\|[\s\-:]+\|', line.strip()):
                continue  # 表头分隔行跳过
            # 表格行转为简单文本
            cells = [c.strip() for c in line.strip().split('|') if c.strip()]
            html_parts.append(f'<p style="margin:0.3em 0;font-size:0.9em;">| {" | ".join(cells)} |</p>')
            continue

        # 行间公式 $$...$$（可能跨行）
        # 先处理行内公式 $...$
        # 再处理行间公式

        # 简化的 Markdown → HTML 加公式渲染
        processed = _process_line(line)
        html_parts.append(f'<p style="margin:0.5em 0;line-height:{LINE_HEIGHT}em;">{processed}</p>')

    return '\n'.join(html_parts)


def _process_line(line):
    """处理单行：LaTeX → 图片"""
    # 如果是单独的行间公式，直接渲染整行
    line_stripped = line.strip()
    if line_stripped.startswith('$$') and line_stripped.endswith('$$'):
        math = line_stripped[2:-2].strip()
        return _render_math_to_img(math, display=True)

    # 保护行内代码
    parts = re.split(r'(`[^`]+`)', line)
    result = []

    for part in parts:
        if part.startswith('`') and part.endswith('`'):
            result.append(f'<code style="background:#f5f5f5;padding:1px 4px;border-radius:2px;'
                         f'font-size:0.9em;">{part[1:-1]}</code>')
            continue

        # 处理该段中的公式
        processed = _render_formulas_in_text(part)
        result.append(processed)

    return ''.join(result)


def _render_formulas_in_text(text):
    """将文本中的 $...$ 和 $$...$$ 替换为图片"""
    # 行间公式 $$...$$
    text = re.sub(
        r'\$\$(.*?)\$\$',
        lambda m: _render_math_to_img(m.group(1), display=True),
        text,
        flags=re.DOTALL
    )
    # 行内公式 $...$
    text = re.sub(
        r'(?<!\$)\$(?!\$)([^$]+?)(?<!\$)\$(?!\$)',
        lambda m: _render_math_to_img(m.group(1), display=False),
        text
    )
    return text


def _render_math_to_img(math_content, display=False):
    """渲染公式 → HTML img 标签"""
    latex = r'$' + math_content + r'$'
    if display:
        latex = r'$$' + math_content + r'$$'

    html_tag, w_em, h_em = render_latex(latex)

    if display:
        # 行间公式居中
        return f'<div style="text-align:center;margin:0.8em 0;">{html_tag}</div>'
    return html_tag


# ======================================================================
# 完整管线：Markdown 文件 → 微信 HTML 文件
# ======================================================================

def _read_file(path):
    """自动检测编码读取文件"""
    import codecs
    encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'utf-16']
    for enc in encodings:
        try:
            with codecs.open(path, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    # fallback: 二进制读+忽略错误
    with open(path, 'rb') as f:
        raw = f.read()
    return raw.decode('utf-8', errors='replace')


def convert_file(input_path, output_path=None):
    """转换整个 Markdown 文件"""
    if not os.path.exists(input_path):
        print(f'ERROR: 文件不存在: {input_path}')
        return

    md_content = _read_file(input_path)

    # 自动检测标题作为文件名
    title = os.path.splitext(os.path.basename(input_path))[0]

    html_body = md_to_wechat_html(md_content)

    # 生成完整的 HTML 页面
    full_html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 15px;
    line-height: {LINE_HEIGHT};
    color: #333;
    padding: 10px 15px;
    max-width: 680px;
    margin: 0 auto;
}}
img {{ max-width: 90% !important; height: auto; }}
code {{ font-family: "SF Mono", "Fira Code", monospace; }}
pre {{
    background: #f5f5f5;
    padding: 10px;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 13px;
}}
blockquote {{
    border-left: 3px solid #ddd;
    margin: 1em 0;
    padding: 0.5em 1em;
    color: #666;
}}
strong {{ font-weight: 600; }}
</style>
</head>
<body>
{html_body}
</body>
</html>'''

    if output_path is None:
        base = os.path.splitext(input_path)[0]
        output_path = base + '_wechat.html'

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_html)

    return output_path


# ======================================================================
# CLI
# ======================================================================

def main():
    parser = argparse.ArgumentParser(
        description='LaTeX Markdown → 微信公众号 HTML 转换工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python wechat_tex.py article.md
  python wechat_tex.py article.md -o output.html
  cat article.md | python wechat_tex.py -
        '''
    )
    parser.add_argument('input', help='输入 Markdown 文件路径（或 - 表示 stdin）')
    parser.add_argument('-o', '--output', help='输出 HTML 文件路径')

    args = parser.parse_args()

    if args.input == '-':
        import codecs
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
        md_content = sys.stdin.read()
        title = 'stdin'
        html_body = md_to_wechat_html(md_content)
        output_path = args.output or 'output_wechat.html'

        full_html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 15px; line-height: {LINE_HEIGHT}; color: #333; padding: 10px 15px; max-width: 680px; margin: 0 auto; }}
img {{ max-width: 90% !important; height: auto; }}
code {{ font-family: "SF Mono", "Fira Code", monospace; }}
pre {{ background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 13px; }}
blockquote {{ border-left: 3px solid #ddd; margin: 1em 0; padding: 0.5em 1em; color: #666; }}
strong {{ font-weight: 600; }}
</style></head><body>
{html_body}
</body></html>'''
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_html)
        print(f'输出: {output_path}')
        return

    output_path = convert_file(args.input, args.output)
    if output_path:
        print(f'[OK] 转换完成: {output_path}')
        print(f'  -> 用浏览器打开 -> 全选复制 -> 粘贴到微信公众号编辑器')
        print(f'  -> 提示: 微信编辑器可能压缩图片，公式较多时建议分批粘贴')


if __name__ == '__main__':
    main()
