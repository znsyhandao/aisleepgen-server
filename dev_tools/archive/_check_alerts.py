# -*- coding: utf-8 -*-
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')

alert_file = r'D:\super_frontier_radar\_pending_alerts.json'
if os.path.exists(alert_file):
    with open(alert_file, 'r', encoding='utf-8') as f:
        alerts = json.load(f)
    print(f'共 {len(alerts)} 条待推送:')
    for a in alerts:
        severity = a.get('severity', '?')
        key = a.get('key', '')
        msg = a.get('message', '')[:100]
        print(f'  [{severity}] {key}: {msg}')
else:
    print('No alerts file')

db_path = r'D:\super_frontier_radar\frontier_data\scanned_papers_db.json'
if os.path.exists(db_path):
    with open(db_path, 'r', encoding='utf-8') as f:
        db = json.load(f)
    print(f'\n扫描数据库: last_scan={db.get("last_scan_ts","?")}')
    papers = db.get('scanned_papers', [])
    print(f'累计论文数: {len(papers)}')
    for p in papers[-3:]:
        pub = p.get('published', '?')
        title = p.get('title', '')[:60]
        print(f'  {pub} | {title}')
