#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
frontier_scanner.py — 极轻量前沿扫描器

用途：每次心跳中快速扫描睡眠/AI领域新论文，不依赖每日管线
输出：_pending_alerts.json 中的 "frontier_scanner" 条目
"""

import json, os, time, urllib.request, urllib.error, re, html
import sys

BASE_DIR = r'D:\super_frontier_radar'
TARGET_DIR = os.path.join(BASE_DIR, 'frontier_data')
DB_PATH = os.path.join(TARGET_DIR, 'scanned_papers_db.json')
PENDING_FILE = os.path.join(BASE_DIR, '_pending_alerts.json')

# 固定查询: 睡眠科学 + AI 轻量扫描
ARXIV_QUERIES = [
    ('sleep+quality+prediction+AI', 'q-bio.NC'),
    ('sleep+stage+classification', 'eess.SP'),
    ('circadian+rhythm+model', 'q-bio.QM'),
]

# 落地的Alert模块
sys.path.insert(0, BASE_DIR)
try:
    from _pending_alerts import PendingAlerts
    ALERTS = PendingAlerts(BASE_DIR)
except ImportError:
    # fallback
    ALERTS = None


def _load_db():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {'last_scan_ts': 0, 'scanned_papers': []}


def _save_db(db):
    os.makedirs(TARGET_DIR, exist_ok=True)
    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    # 保持文件小
    db['scanned_papers'] = db['scanned_papers'][-100:]
    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def _fetch_arxiv(query, cat, max_results=5):
    url = f'http://export.arxiv.org/api/query?search_query=all:{query}&cat:{cat}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode('utf-8')
    except Exception as e:
        print(f'  [Scanner] arXiv fetch error: {e}')
        return None


def _parse_arxiv_atom(xml_text):
    papers = []
    for entry in re.finditer(r'<entry>(.*?)</entry>', xml_text, re.DOTALL):
        title_match = re.search(r'<title>(.*?)</title>', entry.group(1), re.DOTALL)
        id_match = re.search(r'<id>(.*?)</id>', entry.group(1), re.DOTALL)
        summary_match = re.search(r'<summary>(.*?)</summary>', entry.group(1), re.DOTALL)
        published_match = re.search(r'<published>(.*?)</published>', entry.group(1))
        
        if not title_match or not id_match:
            continue
        
        title = html.unescape(re.sub(r'\s+', ' ', title_match.group(1).strip()))
        paper_id = id_match.group(1).strip()
        summary = html.unescape(re.sub(r'\s+', ' ', summary_match.group(1).strip()[:200])) if summary_match else ''
        published = published_match.group(1)[:10] if published_match else ''
        
        papers.append({
            'id': paper_id,
            'title': title,
            'summary': summary,
            'published': published,
            'scanned_at': time.strftime('%Y-%m-%dT%H:%M:%S')
        })
    return papers


def _is_new(db, paper_id):
    return paper_id not in {p['id'] for p in db['scanned_papers']}


def scan():
    """
    执行一次扫描（约15-30秒）
    返回新论文列表
    """
    db = _load_db()
    new_papers = []
    
    for query, cat in ARXIV_QUERIES:
        xml = _fetch_arxiv(query, cat)
        if not xml:
            continue
        papers = _parse_arxiv_atom(xml)
        for p in papers:
            if _is_new(db, p['id']):
                new_papers.append(p)
                db['scanned_papers'].append(p)
                db['scanned_papers'] = db['scanned_papers'][-200:]  # 只保留200条
    
    db['last_scan_ts'] = time.time()
    _save_db(db)
    
    print(f'  [Scanner] arXiv扫描完成: {len(new_papers)} 篇新论文')
    
    if new_papers and ALERTS:
        titles = '; '.join(p['title'][:60] for p in new_papers[:3])
        if len(new_papers) > 3:
            titles += f' … +{len(new_papers)-3}篇'
        ALERTS.add('frontier_scanner',
                   f'新扫描到{len(new_papers)}篇论文: {titles}',
                   severity='INFO')
    
    return new_papers


def scan_relevant(sleep_context=None):
    """
    带上下文扫描（将来可扩展）
    sleep_context: dict — 当前用户睡眠数据关键词
    """
    return scan()


if __name__ == '__main__':
    print('Frontier Scanner 自测:')
    start = time.time()
    n = scan()
    elapsed = time.time() - start
    sys.stdout.reconfigure(encoding='utf-8')
    print(f'  [time] {elapsed:.1f}s')
    print(f'  [papers] {len(n)} neue')
