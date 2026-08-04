import sys, json, os
sys.stdout.reconfigure(encoding='utf-8')

# ===== 1. 查看手环睡眠数据 =====
db_dir = 'sleep-skin image database'
with open(os.path.join(db_dir, 'band_sleep_data_verified.json'), 'r', encoding='utf-8') as f:
    ring_data = json.load(f)
print(f'=== 手环已验证数据 ({len(ring_data)}晚) ===')
for k, v in sorted(ring_data.items()):
    wt = v.get('wake_time', '?')
    st = v.get('sleep_time', '?')
    sc = v.get('sleep_score', '?')
    bp = v.get('better_than_pct', '?')
    print(f'  {k} 睡:{st} 醒:{wt} 分:{sc} 超:{bp}%')

# ===== 2. 查看每个文件夹的图片数量 =====
print(f'\n=== 皮肤数据 文件夹 ===')
dates = sorted(d for d in os.listdir(db_dir) if os.path.isdir(os.path.join(db_dir, d)))
print(f'共 {len(dates)} 天: {dates[0]} ~ {dates[-1]}')
total_imgs = 0
for d in dates:
    files = os.listdir(os.path.join(db_dir, d))
    imgs = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))]
    total_imgs += len(imgs)
    print(f'  {d}: {len(imgs)} 张图片')
print(f'总计: {total_imgs} 张图片')

# ===== 3. 查看 sleep_record 目录与手环数据的日期对齐 =====
print(f'\n=== 整晚录音与手环数据对齐 ===')
record_dir = 'sleep_record'
if os.path.exists(record_dir):
    rec_files = [f for f in os.listdir(record_dir) if f.endswith('.m4a') and len(f) >= 16]
    # 提取日期
    from collections import Counter
    rec_dates = set()
    for f in rec_files:
        fname = f.replace('_woman', '').replace('_womanside', '').replace('_tmp', '')
        # 文件名格式: YYYYMMDD_HHMMSS.m4a
        if fname[:8].isdigit():
            rec_dates.add(fname[:8])
    overlap = sorted(set(ring_data.keys()) & rec_dates)
    only_ring = sorted(set(ring_data.keys()) - rec_dates)
    only_rec = sorted(rec_dates - set(ring_data.keys()))
    print(f'同时有录音+手环数据: {len(overlap)} 天')
    for d in overlap:
        print(f'  {d}: 录音+手环')
    print(f'仅有手环: {len(only_ring)} 天')
    if only_ring:
        for d in only_ring:
            print(f'  {d}: 手环')
    print(f'仅有录音: {len(only_rec)} 天')
    if only_rec:
        for d in only_rec[:5]:
            print(f'  {d}: 录音')
        if len(only_rec) > 5:
            print(f'  ... 共 {len(only_rec)} 天')
