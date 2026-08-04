# -*- coding: utf-8 -*-
"""
自动报告生成：v6特征提取后，对比睡眠数据，生成趋势报告
用法：python auto_report.py
"""
import csv, os, sys
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np
from collections import defaultdict
from datetime import datetime, date
from scipy import stats

OUT = r'D:\AISleepGen_Optimized\sleep-skin features'
REPORT_PATH = os.path.join(OUT, 'latest_auto_report.txt')
CSV_PATH = os.path.join(OUT, 'facial_features_v6.csv')

# ========== 读取最新特征数据 ==========
if not os.path.exists(CSV_PATH):
    print(f'❌ 未找到特征数据: {CSV_PATH}')
    print('请先运行 extract_skin_features_v6.py')
    sys.exit(1)

with open(CSV_PATH, 'r') as f:
    all_data = list(csv.DictReader(f))

data = [d for d in all_data if d.get('face_detected') == 'True']
print(f'加载 {len(data)} 条有效特征数据')

# ========== 按日期聚合 ==========
daily = defaultdict(list)
for d in data:
    daily[d['date']].append(d)

dates = sorted(daily.keys())
print(f'共 {len(dates)} 天数据: {dates[0]} ~ {dates[-1]}')

# ========== 读取睡眠评分（从txt文件） ==========
BASE = r'D:\AISleepGen_Optimized\sleep-skin image database'
sleep_scores = {}
sleep_durations = {}
sleep_notes = {}

for date_str in dates:
    # 查找当天对应的睡眠记录文件
    YY = date_str[:4]  # 2026
    MM = date_str[4:6]  # 04
    DD = date_str[6:8]  # 18
    date_dir = os.path.join(BASE, date_str)
    
    if not os.path.isdir(date_dir):
        continue
    
    for fname in os.listdir(date_dir):
        if fname.lower().endswith('.txt'):
            fpath = os.path.join(date_dir, fname)
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read().strip()
            
            # 从文本提取评分（数字+分）
            import re
            score_match = re.search(r'(\d+)\s*分', text)
            if score_match:
                score = int(score_match.group(1))
                sleep_scores[date_str] = score
            
            sleep_notes[date_str] = text[:80]

print(f'匹配到 {len(sleep_scores)} 天的睡眠评分数据')

# ========== 最近7天趋势分析 ==========
KEY_LABELS = [
    ('fatigue_eye_darkness', '眼周暗沉', '越低越好'),
    ('fatigue_overall', '疲劳综合', '越低越好'),
    ('freq_high_low_ratio', '高频/低频比', '越高越好'),
    ('skin_health_composite', '皮肤健康综合', '越高越好'),
    ('lab_B_mean', 'Lab-B黄蓝', '变化趋势'),
    ('roi_grad_forehead_jaw', '额-颌梯度', '越高越好'),
    ('roi_forehead_jaw_ratio', '额/颌比', '>1正常'),
    ('edge_density_medium', '中等边缘密度', '越高纹理越细'),
    ('gloss_smoothness', '皮肤光滑度', '越高越好'),
    ('pigment_spot_ratio', '色斑比例', '越低越好'),
]

# 计算每个特征的统计量
def get_feature_stats(daily_dict, key, dates_list):
    daily_means = {}
    for d in dates_list:
        vals = [float(e.get(key, 0)) for e in daily_dict[d] if e.get(key, '')]
        if vals:
            daily_means[d] = np.mean(vals)
    return daily_means

# 生成报告
lines = []
lines.append('=' * 65)
lines.append('  AISleepGen 皮肤-睡眠监测报告')
lines.append(f'  生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}')
lines.append(f'  数据范围: {dates[0] if dates else "无"} ~ {dates[-1] if dates else "无"}')
lines.append(f'  数据量: {len(dates)} 天, {len(data)} 张照片')
lines.append('=' * 65)
lines.append('')

# 最近7天趋势
recent = dates[-7:] if len(dates) >= 7 else dates
lines.append(f'📈 最近 {len(recent)} 天趋势分析')
lines.append('-' * 65)

for key, label, direction in KEY_LABELS:
    stats_dict = get_feature_stats(daily, key, recent)
    if len(stats_dict) < 2:
        continue
    
    recent_vals = [stats_dict[d] for d in recent if d in stats_dict]
    if len(recent_vals) < 2:
        continue
    
    first_val = recent_vals[0]
    last_val = recent_vals[-1]
    change = last_val - first_val
    
    # 相对变化百分比
    if abs(first_val) > 1e-6:
        pct = (last_val - first_val) / abs(first_val) * 100
    else:
        pct = 0
    
    # 判断好坏
    if '越低越好' in direction:
        is_worsening = change > 0 and abs(change) > abs(first_val) * 0.1  # 上涨>10%
        is_improving = change < 0 and abs(change) > abs(first_val) * 0.1  # 下降>10%
    elif '越高越好' in direction:
        is_worsening = change < 0 and abs(change) > abs(first_val) * 0.1
        is_improving = change > 0 and abs(change) > abs(first_val) * 0.1
    else:
        is_worsening = False
        is_improving = False
    
    marker = ''
    if is_worsening:
        marker = ' ⚠️ 变差'
    elif is_improving:
        marker = ' ✅ 改善'
    
    # 打印
    arrow = '↑' if change > 0 else '↓' if change < 0 else '→'
    lines.append(f'  {label:<14s} 今天={last_val:>8.2f} {arrow} {change:>+7.2f} ({pct:>+5.1f}%){marker}')

lines.append('')

# ========== 睡眠评分趋势 ==========
if sleep_scores:
    lines.append('🛏️ 本月睡眠趋势')
    lines.append('-' * 65)
    
    for d in recent:
        if d in sleep_scores:
            score = sleep_scores[d]
            bar = '█' * score + '░' * (10 - score)
            note = sleep_notes.get(d, '')
            lines.append(f'  {d} | {bar} {score}分 | {note}')
    lines.append('')

# ========== 特征-睡眠相关性 ==========
if len(sleep_scores) >= 5:
    lines.append('📊 特征 vs 睡眠评分 相关性分析')
    lines.append('-' * 65)
    
    corr_results = []
    for key, label, direction in KEY_LABELS:
        pairs = []
        for d in recent:
            if d not in daily or d not in sleep_scores:
                continue
            vals = [float(e.get(key, 0)) for e in daily[d] if e.get(key, '')]
            if vals:
                pairs.append((np.mean(vals), sleep_scores[d]))
        
        if len(pairs) >= 5:
            x = [p[0] for p in pairs]
            y = [p[1] for p in pairs]
            r, pval = stats.pearsonr(x, y)
            
            mag = abs(r)
            if mag > 0.6 and pval < 0.15:
                star = '⭐ '
            elif mag > 0.4:
                star = '   '
            else:
                star = '   '
            
            arrow = '↑' if r > 0 else '↓'
            lines.append(f'  {star}{label:<14s} r={r:>+5.2f}  p={pval:.3f}  {arrow}')
            corr_results.append((abs(r), label, r, pval))
    
    lines.append('')

# ========== 注意事项 ==========
lines.append('💡 注意事项')
lines.append('-' * 65)
lines.append(f'  - 总数据量: {len(dates)} 天, 建议21天以上做严肃分析')
lines.append(f'  - 距离中期分析(14天): 还需 {max(0, 14-len(dates))} 天')
lines.append(f'  - 距离完整分析(21天): 还需 {max(0, 21-len(dates))} 天')
lines.append(f'  - 当前特征提取算法: v6 (白平衡校正+9种算法)')
lines.append(f'  - 脸部检测率: {len(data)}/{len(all_data)} ({len(data)/len(all_data)*100 if len(all_data)>0 else 0:.0f}%)')
lines.append('')
lines.append('📷 拍摄提醒')
lines.append('  - 关掉人像模式，用普通/专业模式')
lines.append('  - 固定22cm距离拍摄')
lines.append('  - 先拍一张白纸在脸位置的参考照')
lines.append('  - 记录睡眠质量到txt')

# ========== 保存报告 ==========
report_text = '\n'.join(lines)
with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    f.write(report_text)

print(f'✅ 报告已保存: {REPORT_PATH}')
print()
print(report_text)
