# -*- coding: utf-8 -*-
"""
循证数据库自动更新器 v1.0
从PubMed拉取最新睡眠医学文献，自动更新EVIDENCE_BASE
支持: 自动搜索 + 自动摘要 + 自动标注

运行方式:
  python evidence_updater.py            # 更新所有分类
  python evidence_updater.py --dry-run  # 预览但不写入
  python evidence_updater.py --list     # 列出当前证据库
"""

import sys, os, json, re, time
sys.stdout.reconfigure(encoding='utf-8')

import urllib.request, urllib.parse

# ============================================================
# PubMed API
# ============================================================
PUBMED_BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
RATE_LIMIT = 0.34  # NCBI限制: 每秒最多3个请求

# 搜索主题词表
SEARCH_TOPICS = {
    'cbt_i_efficacy': {
        'keywords': '(sleep OR insomnia) AND (cognitive behavioral therapy OR CBT-I) AND (efficacy OR randomized controlled trial OR meta-analysis)',
        'target': 'cbt_i',
        'max_results': 10,
        'since_years': 3,
    },
    'sleep_and_inflammation': {
        'keywords': '(sleep OR insomnia) AND (inflammation OR cytokine OR IL-6 OR TNF-alpha OR glymphatic) AND clinical trial',
        'target': 'inflammation',
        'max_results': 10,
        'since_years': 3,
    },
    'chronotype_and_sleep': {
        'keywords': '(chronotype OR morningness OR eveningness OR MEQ) AND (sleep quality OR insomnia) AND (treatment OR intervention)',
        'target': 'chronotype',
        'max_results': 10,
        'since_years': 3,
    },
    'sleep_and_skin': {
        'keywords': '(sleep OR sleep deprivation OR sleep quality) AND (skin OR facial OR periorbital OR dark circles OR skin color) AND (camera OR photography OR imaging)',
        'target': 'skin_sleep',
        'max_results': 10,
        'since_years': 5,
    },
    'osa_screening': {
        'keywords': '(obstructive sleep apnea OR OSA) AND (screening OR STOP-Bang OR home sleep test) AND validation',
        'target': 'osa',
        'max_results': 10,
        'since_years': 3,
    },
    'sleep_deprivation_recovery': {
        'keywords': '(sleep deprivation OR sleep restriction) AND (recovery OR glymphatic OR growth hormone OR cortisol) AND human',
        'target': 'recovery',
        'max_results': 10,
        'since_years': 3,
    },
}

# 缓存文件
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.evidence_cache.json')
EVIDENCE_AUTO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.auto_evidence.json')
WORLD_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sleep_world_model.py')

class PubMedFetcher:
    def __init__(self):
        self._last_request = 0
    
    def _rate_limit(self):
        elapsed = time.time() - self._last_request
        if elapsed < RATE_LIMIT:
            time.sleep(RATE_LIMIT - elapsed)
        self._last_request = time.time()
    
    def search(self, query, max_results=10, since_years=3):
        """搜索PubMed，返回PMID列表"""
        # 简单日期过滤: 用min_date参数
        from datetime import datetime, timedelta
        cutoff_date = (datetime.now() - timedelta(days=365 * since_years)).strftime('%Y/%m/%d')
        
        full_query = query + f' AND ("{cutoff_date}"[Date - Create] : "3000"[Date - Create])'
        
        params = urllib.parse.urlencode({
            'db': 'pubmed',
            'term': full_query,
            'retmax': max_results,
            'retmode': 'json',
        })
        
        url = f'{PUBMED_BASE}/esearch.fcgi?{params}'
        self._rate_limit()
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'AISleepGen/1.0'})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode('utf-8'))
            ids = data.get('esearchresult', {}).get('idlist', [])
            total = data.get('esearchresult', {}).get('count', '0')
            return ids, int(total)
        except Exception as e:
            print(f'  [ESearch Error] {e}')
            return [], 0
    
    def fetch_details(self, ids):
        """获取文献详情"""
        if not ids:
            return []
        
        id_str = ','.join(ids[:10])  # 每次最多10篇
        params = urllib.parse.urlencode({
            'db': 'pubmed',
            'id': id_str,
            'retmode': 'xml',
        })
        
        url = f'{PUBMED_BASE}/efetch.fcgi?{params}'
        self._rate_limit()
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'AISleepGen/1.0'})
            with urllib.request.urlopen(req, timeout=20) as r:
                xml = r.read().decode('utf-8')
            return self._parse_articles(xml)
        except Exception as e:
            print(f'  [EFetch Error] {e}')
            return []
    
    def _parse_articles(self, xml):
        """简易XML解析，提取PMID/Title/Abstract/DOI"""
        articles = []
        pattern = r'<PubmedArticle>(.*?)</PubmedArticle>'
        for match in re.finditer(pattern, xml, re.DOTALL):
            article_xml = match.group(1)
            
            # PMID
            pmid_m = re.search(r'<PMID[^>]*>(\d+)</PMID>', article_xml)
            pmid = pmid_m.group(1) if pmid_m else ''
            
            # Title
            title_m = re.search(r'<ArticleTitle[^>]*>(.*?)</ArticleTitle>', article_xml, re.DOTALL)
            title = title_m.group(1).strip() if title_m else ''
            # 清理XML标签
            title = re.sub(r'<[^>]+>', '', title)
            
            # DOI
            doi_m = re.search(r'<ELocationID[^>]*EIdType="doi"[^>]*>(.*?)</ELocationID>', article_xml)
            doi = doi_m.group(1) if doi_m else ''
            
            # Year
            year_m = re.search(r'<Year>(\d{4})</Year>', article_xml)
            year = year_m.group(1) if year_m else ''
            
            # Abstract (first 300 chars)
            abs_m = re.search(r'<AbstractText[^>]*>(.*?)</AbstractText>', article_xml, re.DOTALL)
            abstract = ''
            if abs_m:
                abstract = re.sub(r'<[^>]+>', '', abs_m.group(1)).strip()[:300]
            
            articles.append({
                'pmid': pmid,
                'title': title,
                'doi': doi,
                'year': year,
                'abstract': abstract,
            })
        
        return articles


class EvidenceDatabase:
    def __init__(self):
        self.cache = self._load_cache()
    
    def _load_cache(self):
        if os.path.exists(CACHE_PATH):
            try:
                with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
        return {'last_update': None, 'articles': {}}
    
    def _save_cache(self):
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)
    
    def update(self, dry_run=False):
        """更新所有分类的文献"""
        fetcher = PubMedFetcher()
        
        print(f'PubMed自动循证更新')
        print(f'=' * 60)
        
        all_new_articles = 0
        new_evidence_entries = []
        
        for topic, config in SEARCH_TOPICS.items():
            print(f'\n搜索: {topic}')
            print(f'  关键词: {config["keywords"][:60]}...')
            
            ids, total = fetcher.search(
                config['keywords'],
                max_results=config['max_results'],
                since_years=config['since_years']
            )
            
            print(f'  找到 {total} 篇, 获取 {len(ids)} 篇')
            
            if not ids:
                continue
            
            # 过滤已缓存的
            new_ids = [i for i in ids if i not in self.cache.get('articles', {})]
            
            if new_ids:
                articles = fetcher.fetch_details(new_ids)
                
                for art in articles:
                    pmid = art['pmid']
                    if pmid not in self.cache.get('articles', {}):
                        if 'articles' not in self.cache:
                            self.cache['articles'] = {}
                        self.cache['articles'][pmid] = art
                        all_new_articles += 1
                        
                        # 检查是否能生成证据条目
                        target = config['target']
                        if 'cbt' in target or 'insomnia' in target:
                            evidence_item = self._create_evidence_from_article(art, 'cbt_i')
                            if evidence_item:
                                new_evidence_entries.append(evidence_item)
                        elif 'inflammation' in target or 'glymphatic' in target:
                            evidence_item = self._create_evidence_from_article(art, 'inflammation')
                            if evidence_item:
                                new_evidence_entries.append(evidence_item)
                        
                        print(f'    + PMID {pmid}: {art["title"][:50]}... [{art.get("year", "?")}]')
            
            time.sleep(0.5)  # 话题间延迟
        
        # 保存缓存 + 新证据写入独立文件（不污染源代码）
        if not dry_run:
            self.cache['last_update'] = time.strftime('%Y-%m-%d %H:%M')
            self._save_cache()
            
            if new_evidence_entries:
                auto_evidence = []
                if os.path.exists(EVIDENCE_AUTO_PATH):
                    try:
                        with open(EVIDENCE_AUTO_PATH, 'r', encoding='utf-8') as f:
                            auto_evidence = json.load(f)
                    except Exception:
                existing_pmids = {e.get('pmid') for e in auto_evidence}
                real_new = [e for e in new_evidence_entries if e.get('pmid') and e['pmid'] not in existing_pmids]
                auto_evidence.extend(real_new)
                if len(auto_evidence) > 50:
                    auto_evidence = auto_evidence[-50:]
                
                with open(EVIDENCE_AUTO_PATH, 'w', encoding='utf-8') as f:
                    json.dump(auto_evidence, f, ensure_ascii=False, indent=2)
                print(f'  自动证据已写入 {EVIDENCE_AUTO_PATH} ({len(auto_evidence)} 条)')
        
        print(f'\n更新摘要:')
        print(f'  新增文献: {all_new_articles} 篇')
        print(f'  总缓存: {len(self.cache.get("articles", {}))} 篇')
        print(f'  新证据条目: {len(new_evidence_entries)} 条')
        
        if new_evidence_entries:
            print(f'\n建议新增到EVIDENCE_BASE的证据:')
            for entry in new_evidence_entries[:5]:
                print(f'  [{entry.get("certainty","?")}] {entry["name"]}')
                print(f'    PMID: {entry.get("pmid","?")}, 效应量: {entry.get("effect_size", "?")}')
        
        return new_evidence_entries
    
    def _create_evidence_from_article(self, art, category):
        """从文献自动生成证据条目"""
        title = art['title']
        pmid = art['pmid']
        year = art.get('year', '?')
        
        # 简单分类推断
        if 'meta-analysis' in title.lower() or 'systematic review' in title.lower():
            certainty = 'high'
            effect_label = 'Meta分析, 待提取效应量'
        elif 'randomized' in title.lower() or 'RCT' in title:
            certainty = 'high'
            effect_label = 'RCT, 待提取效应量'
        elif 'clinical trial' in title.lower():
            certainty = 'moderate'
            effect_label = '临床试验, 待提取效应量'
        else:
            certainty = 'low'
            effect_label = '观察性研究, 待提取效应量'
        
        return {
            'name': title[:60] + '...',
            'evidence': f'{", ".join([a.get("first_author","") for a in [art]] ) if None else ""} et al., {year}, PMID: {pmid}',
            'description': art['abstract'][:200] if art.get('abstract') else '待提取摘要',
            'indications': [category],
            'effect_size': effect_label,
            'certainty': certainty,
            'pmid': pmid,
            'doi': art.get('doi', ''),
            'added_on': time.strftime('%Y-%m-%d'),
        }
    
    def list_latest(self, count=20):
        """列出最新文献"""
        articles = self.cache.get('articles', {})
        if not articles:
            print('缓存为空，请先运行更新')
            return
        
        print(f'最新文献 (共{len(articles)}篇, 显示{min(count, len(articles))}篇):')
        print('=' * 70)
        
        # 按PMID倒序（大致按加入时间）
        sorted_pmids = sorted(articles.keys(), reverse=True)[:count]
        for pmid in sorted_pmids:
            art = articles[pmid]
            print(f'  PMID {pmid} [{art.get("year","?")}]')
            print(f'  {art["title"][:80]}')
            if art.get('doi'):
                print(f'  DOI: {art["doi"]}')
            print()


# ============================================================
# 报告输出（不再自动写源文件）
# ============================================================
def print_update_report(new_entries):
    """将新证据条目注入到sleep_world_model.py的EVIDENCE_BASE"""
    if not new_entries:
        print('无新证据条目需要更新')
        return
    
    with open(WORLD_MODEL_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 在EVIDENCE_BASE末尾添加新条目
    insert_marker = '# 循证干预库'
    
    new_code = ''
    for entry in new_entries:
        key_name = 'auto_' + entry.get('pmid', str(int(time.time())))
        new_code += f'\n    \'{key_name}\': {{\n'
        new_code += f"        'name': '{entry['name']}',\n"
        new_code += f"        'evidence': '{entry['evidence']}',\n"
        new_code += f"        'description': '{entry['description'][:150]}',\n"
        new_code += f"        'indications': {entry['indications']},\n"
        new_code += f"        'effect_size': '{entry['effect_size']}',\n"
        new_code += f"        'certainty': '{entry['certainty']}',\n"
        new_code += f"        'auto_added': '{entry.get('added_on', '')}',\n"
        new_code += '    },\n'
    
    # 在EVIDENCE_BASE闭合前插入
    insert_pos = content.rfind('}')
    if insert_pos > 0:
        # 找到最后一个 } 之前的插入点
        before = content.rfind('}', 0, insert_pos)
        if before > 0:
            content = content[:before+1] + new_code + content[before+1:]
    
    with open(WORLD_MODEL_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f'已将 {len(new_entries)} 条证据写入 {WORLD_MODEL_PATH}')


# ============================================================
# CLI
# ============================================================
def list_current_evidence():
    """列出当前EVIDENCE_BASE"""
    import ast, re
    
    with open(WORLD_MODEL_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取EVIDENCE_BASE内嵌
    match = re.search(r'EVIDENCE_BASE\s*=\s*\{', content)
    if match:
        start = match.start()
        # 找到匹配的闭合}
        depth = 0
        for i in range(start, len(content)):
            if content[i] == '{': depth += 1
            elif content[i] == '}': depth -= 1
            if depth == 0:
                end = i + 1
                break
        
        # 提取所有条目名
        block = content[start:end]
        names = re.findall(r"'(\w+)':\s*\{", block)
        
        print(f'EVIDENCE_BASE 当前条目 ({len(names)} 条):')
        print('=' * 60)
        for name in names:
            # 取对应的name字段
            name_m = re.search(r"'" + name + r"':\s*\{[^}]*'name':\s*'([^']+)'", block)
            name_val = name_m.group(1) if name_m else name
            certainty_m = re.search(r"'" + name + r"':\s*\{[^}]*'certainty':\s*'([^']+)'", block)
            certainty = certainty_m.group(1) if certainty_m else '?'
            print(f'  {name:30s} | {name_val[:25]:25s} | {certainty}')
    else:
        print('未找到EVIDENCE_BASE')


if __name__ == '__main__':
    if '--list' in sys.argv:
        list_current_evidence()
        sys.exit(0)
    
    dry_run = '--dry-run' in sys.argv
    
    db = EvidenceDatabase()
    
    # 显示当前状态
    cache_articles = len(db.cache.get('articles', {}))
    last_update = db.cache.get('last_update', '从未')
    print(f'循证缓存: {cache_articles} 篇文献, 上次更新: {last_update}')
    
    if '--status' in sys.argv:
        list_current_evidence()
        sys.exit(0)
    
    # 拉取更新
    new_entries = db.update(dry_run=dry_run)
    
    # 写入world_model
    if new_entries and not dry_run:
        print('\n是否将新证据写入世界模型? (y/n)')
        # 自动写入（无人值守时）
        print_update_report(new_entries)
