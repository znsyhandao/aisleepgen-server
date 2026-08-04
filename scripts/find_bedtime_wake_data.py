# 睡前-睡后差值计算（已有数据可用）
import numpy as np, pandas as pd, sys, os, re, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

CSV = r'D:/AISleepGen_Optimized/sleep-skin features/facial_features_v9.csv'
BASE = r'D:\AISleepGen_Optimized\sleep-skin image database'
SCORES = {'20260418':3,'20260419':8,'20260420':8,'20260421':6,'20260422':5,'20260423':7,'20260424':7,
          '20260425':4,'20260427':5,'20260428':3,'20260429':7,'20260430':4,
          '20260501':5,'20260502':5,'20260503':7,'20260504':5,'20260505':6,
          '20260506':4,'20260507':5,'20260508':4,'20260509':4,'20260510':7}
FEATS = ['freq_high_low_ratio', 'hsv_H_std', 'gabor_mean_00', 'gabor_std_00']

# 检查哪些日期有 22:xx（睡前）的照片
print('=== 检查每日照片时间 ===')
dates = sorted([d for d in os.listdir(BASE) if os.path.isdir(os.path.join(BASE, d)) and d.startswith('2026') or d.startswith('20260')])
for d in dates:
    dirpath = os.path.join(BASE, d)
    files = [f for f in os.listdir(dirpath) if f.endswith('.jpg') and '_man' not in f and not f.startswith('_')]
    if not files:
        continue
    hours = []
    for f in files:
        m = re.search(r'_(\d{6})\.jpg', f)
        if m:
            h = int(m.group(1)[:2])
            hours.append(h)
    if hours:
        # 女性照片
        female_files = [f for f in os.listdir(dirpath) if f.endswith('.jpg') and '_man' not in f]
        if female_files:
            min_h = min(hours)
            max_h = max(hours)
            has_late = any(h >= 20 for h in hours)
            has_early = any(5 <= h < 12 for h in hours)
            print(f'  {d}: {len(female_files)}张女照 时间范围={min_h}:00-{max_h}:00 晚间={has_late} 早晨={has_early}')
            if has_late and has_early:
                print(f'    *** 同一天既有睡前又有睡后数据！')

# 检查 0509 睡前 + 0510 睡后对照
print()
print('=== 0509(睡前) vs 0510(睡后) 对比 ===')
df = pd.read_csv(CSV)
df = df[df['face_detected'].astype(str).str.lower().str.strip()=='true'].copy()
df['date'] = df['date'].astype(str).str.strip()
df['gender'] = df['file'].str.contains('_man', case=False).map({True:'M', False:'F'})

def get_hour(fname):
    m = re.search(r'_(\d{6})\.jpg', fname)
    return int(m.group(1)[:2]) if m else None

df['hour'] = df['file'].apply(get_hour)

# 0509 的女性睡前照（20:00以后）
d509_bedtime = df[(df['date']=='20260509') & (df['gender']=='F') & (df['hour'] >= 18)]
# 0510 的女性睡后照（5:00~12:00）
d510_wake = df[(df['date']=='20260510') & (df['gender']=='F') & (df['hour'] >= 5) & (df['hour'] < 12)]

print(f'  0509 睡前: {len(d509_bedtime)}张')
print(f'  0510 睡后: {len(d510_wake)}张')

if len(d509_bedtime) > 0 and len(d510_wake) > 0:
    bt_mean = d509_bedtime[FEATS].astype(float).mean()
    wk_mean = d510_wake[FEATS].astype(float).mean()
    diff = wk_mean - bt_mean
    print()
    print('  差值（睡后-睡前，正值=改善↑）:')
    for f in FEATS:
        print(f'    {f:30s}: 睡前={bt_mean[f]:.4f}  睡后={wk_mean[f]:.4f}  差值={diff[f]:+.4f}')
    print(f'  对应睡眠评分: {SCORES.get("20260510", "?")}')

# 扩展到所有有"连续天"数据的情况
print()
print('=== 跨天对照（X日睡前 → X+1日睡后）===')
for i in range(len(dates)):
    d = dates[i]
    if i+1 >= len(dates): break
    d_next = dates[i+1]
    
    bedtime = df[(df['date']==d) & (df['gender']=='F') & (df['hour'] >= 18)]
    wake = df[(df['date']==d_next) & (df['gender']=='F') & (df['hour'] >= 5) & (df['hour'] < 12)]
    
    if len(bedtime) > 0 and len(wake) > 0:
        bt = bedtime[FEATS].astype(float).mean()
        wk = wake[FEATS].astype(float).mean()
        diff = wk - bt
        score = SCORES.get(d_next, '?')
        print(f'  {d}(睡前)→{d_next}(睡后) 评分={score}: ', 
              ' '.join([f'{f}={diff[f]:+.3f}' for f in FEATS[:2]]))
    else:
        reason = []
        if len(bedtime) == 0: reason.append(f'{d}无睡前')
        if len(wake) == 0: reason.append(f'{d_next}无睡后')
        print(f'  {d}→{d_next}: 跳过 ({", ".join(reason)})')
