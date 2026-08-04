"""
find_stories.py — 晚安故事检索

遍历 miniprogram 目录的 JS 文件，搜索故事/助眠/晚安相关文本，
用于确认故事 prompt 是否被正确配置。
用法: python dev_tools/check/find_stories.py
"""
# -*- coding: utf-8 -*-
"""Find sleep story prompt in JS files"""
import os, sys

sys.stdout.reconfigure(encoding='utf-8')

for root, dirs, files in os.walk(r'D:\AISleepGen_Optimized\miniprogram'):
    for f in files:
        if not f.endswith('.js'):
            continue
        path = os.path.join(root, f)
        with open(path, 'r', encoding='utf-8') as fh:
            try:
                c = fh.read()
            except:
                continue
        for word in ['故事', '助眠', '晚安', 'story', 'sleep']:
            if word in c.lower():
                lines = c.split('\n')
                for i, line in enumerate(lines):
                    if word in line.lower():
                        print(f'{path}:{i}: {line.strip()[:120]}')
                        break
