# -*- coding: utf-8 -*-
"""
循证追踪器 — 查看PubMed自动更新的结果和效果
用: python scripts/evidence_tracker.py
"""

import sys, os, json, time
sys.stdout.reconfigure(encoding='utf-8')

EVIDENCE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.evidence_cache.json')
AUTO_EVIDENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.auto_evidence.json')

def show_status():
    print('='*65)
    print('  AISleepGen 循证数据库状态')
    print('='*65)
    
    # 1. PubMed缓存状态
    if os.path.exists(EVIDENCE_CACHE):
        with open(EVIDENCE_CACHE, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        articles = cache.get('articles', {})
        last_update = cache.get('last_update', '未知')
        print(f'\n📚 PubMed文献缓存')
        print(f'  总文献数: {len(articles)} 篇')
        print(f'  上次更新: {last_update}')
        
        # 按年份分布
        years = {}
        for pmid, art in articles.items():
            y = art.get('year', '?')
            years[y] = years.get(y, 0) + 1
        if years:
            print(f'  年份分布: {", ".join(f"{y}:{n}" for y, n in sorted(years.items()))}')
        
        # 最近5篇
        sorted_pmids = sorted(articles.keys(), reverse=True)[:5]
        print(f'\n  最近5篇:')
        for pmid in sorted_pmids:
            art = articles[pmid]
            print(f'    [{art.get("year","?")}] {art["title"][:60]}...')
            print(f'    PMID: {pmid}, DOI: {art.get("doi","?")}')
    else:
        print('\n📚 PubMed文献缓存: 空（未运行过证据更新）')
    
    # 2. 自动证据状态
    if os.path.exists(AUTO_EVIDENCE):
        with open(AUTO_EVIDENCE, 'r', encoding='utf-8') as f:
            evidence = json.load(f)
        print(f'\n⚕️ 世界模型自动证据:')
        print(f'  已载入 {len(evidence)} 条')
        
        # 按置信度分类
        by_certainty = {}
        for e in evidence:
            c = e.get('certainty', 'unknown')
            by_certainty[c] = by_certainty.get(c, 0) + 1
        
        # 按时间分类
        added_dates = [e.get('added_on', '?') for e in evidence]
        last_added = max(added_dates) if added_dates else '无'
        
        print(f'  置信度分布: {", ".join(f"{k}:{v}" for k, v in sorted(by_certainty.items()))}')
        print(f'  最近添加: {last_added}')
        
        # 高置信度证据
        high_cert = [e for e in evidence if e.get('certainty') == 'high']
        if high_cert:
            print(f'\n  高确定性证据 (n={len(high_cert)}):')
            for e in high_cert[:3]:
                print(f'    [PMID {e.get("pmid","?")}] {e["name"][:50]}...')
                print(f'    证据: {e.get("evidence","")[:80]}...')
    else:
        print(f'\n⚕️ 世界模型自动证据: 空')
    
    # 3. 时间线
    print(f'\n⏰ 时间线')
    print(f'  当前时间: {time.strftime("%Y-%m-%d %H:%M")}')
    print(f'  下次自动更新: {time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + 604800))}')
    
    # 4. 下一次手动更新的建议
    print(f'\n💡 手动更新')
    print(f'  python scripts\\evidence_updater.py    # 拉取新证据')
    print(f'  python scripts\\evidence_tracker.py     # 查看本报告')
    print()

if __name__ == '__main__':
    show_status()
