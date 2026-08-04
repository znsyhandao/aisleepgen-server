# -*- coding: utf-8 -*-
"""批量分析5/21-5/28的新增m4a（跳过头10分钟）"""
import os, sys, json
sys.path.insert(0, r'D:\AISleepGen_Optimized')
from sleep_audio_analyzer import SleepAudioAnalyzer

RECORD = r'D:\AISleepGen_Optimized\sleep_record'
ANALYZED = os.path.join(RECORD, 'analyzed')
os.makedirs(ANALYZED, exist_ok=True)

# 已有分析的文件
existing = set(f.replace('_analysis.json','') for f in os.listdir(ANALYZED) if f.endswith('_analysis.json'))

# 要分析的m4a (5/21-5/28, 跳过已分析的)
files_to_analyze = sorted([f for f in os.listdir(RECORD) 
                          if f.endswith('.m4a') and f[:8] >= '20260521' 
                          and f.replace('.m4a','') not in existing])

print(f"已有分析: {len(existing)} 个")
print(f"待分析: {len(files_to_analyze)} 个")

ana = SleepAudioAnalyzer()
for fname in files_to_analyze:
    fp = os.path.join(RECORD, fname)
    size_mb = os.path.getsize(fp) / 1e6
    print(f"\n分析 {fname} ({size_mb:.0f}MB)...", flush=True)
    
    try:
        # 整夜录音跳过前600秒(10分钟)
        skip = 600 if size_mb > 100 else 0
        result = ana.analyze_file(fp, skip_seconds=skip)
        result['date'] = fname[:8]
        result['source'] = fname
        
        # 保存
        out_name = fname.replace('.m4a', '_analysis.json')
        out_path = os.path.join(ANALYZED, out_name)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        s = result['snore']
        m = result['movement']
        st = result['stability']
        print(f"  ✅ {fname[:8]}: {result['duration_hours']:.1f}h snore={s['snore_pct']:.0f}% mov={m['total_movement_min']:.0f}m stable={st['score']:.0f}/100 eff={result['sleep_efficiency']:.0f}%")
    except Exception as e:
        print(f"  ❌ {fname[:8]}: {e}")

print(f"\n✅ 完成! 分析文件保存在 {ANALYZED}")
