# -*- coding: utf-8 -*-
"""OCR 提取华为手环睡眠截图的关键指标"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import pytesseract
from PIL import Image
import os, re, json

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
BASE = r'D:\AISleepGen_Optimized\sleep-skin image database'

BAND_FILES = [
    ('20260505', '华为手环11pro给的睡眠图_20260505_lastnight.jpg'),
    ('20260506', '华为手环11pro给的睡眠图_20260506_lastnight.jpg'),
    ('20260507', '华为手环11pro给的睡眠图_20260507.jpg'),
    ('20260508', '华为手环11pro给的睡眠图_20260508.jpg'),
    ('20260509', '华为手环11pro给的睡眠图_20260509_lastnight.jpg'),
    ('20260510', '华为手环11pro给的睡眠图_20260510_lastnight.jpg'),
]

def extract_band_data(text):
    """从OCR文本提取手环睡眠数据"""
    data = {}
    
    # 醒来时间 06:25
    m = re.search(r'(\d{1,2}:\d{2})', text)
    if m: data['wake_time'] = m.group(1)
    
    # 入睡时间 22:44
    times = re.findall(r'(\d{1,2}:\d{2})', text)
    if len(times) >= 2: data['sleep_time'] = times[-1]
    
    # 睡眠时长（分钟）- 找"数字 min"或"数字h数字min"
    m = re.search(r'(\d+)\s*h', text, re.I)
    m2 = re.search(r'(\d+)\s*(?:min|m)', text, re.I)
    if m and m2:
        data['sleep_duration_h'] = int(m.group(1))
        data['sleep_duration_min'] = int(m2.group(1))
        data['sleep_duration_total_min'] = data['sleep_duration_h'] * 60 + data['sleep_duration_min']
    
    # 深睡时长 - "小时 数字 分钟" 模式
    # 在英文OCR下可能是 "1 h 45 min" 或 "1 45"
    deep_pattern = re.findall(r'(?:deep|深睡|深)\s*(?:sleep|).*?(\d+)\s*(?:h|小时|)\s*(\d+)\s*(?:min|分钟)', text, re.I)
    if deep_pattern:
        h, m = deep_pattern[0]
        data['deep_sleep_min'] = int(h)*60 + int(m)
    
    # 百分比 - 通常是深睡占比
    pcts = re.findall(r'(\d+)\s*%', text)
    if pcts: data['percentages'] = [int(p) for p in pcts]
    
    # 睡眠评分 - "86 分" 模式
    m = re.search(r'(\d+)\s*(?:分|score|points)', text, re.I)
    if m: data['sleep_score'] = int(m.group(1))
    
    # 心率
    hr = re.findall(r'(?:heart|心率|HR)\s*(?:rate|).*?(\d+)', text, re.I)
    if hr: data['heart_rate'] = int(hr[0])
    
    return data

results = {}
for date, fname in BAND_FILES:
    fp = os.path.join(BASE, date, fname)
    if not os.path.exists(fp):
        print(f'  {date}: 文件不存在')
        continue
    
    img = Image.open(fp)
    w, h = img.size
    big = img.resize((w*3, h*3), Image.LANCZOS)
    crop = big.crop((0, 0, w*3, min(7500, h*3)))
    
    text = pytesseract.image_to_string(crop, lang='eng',
        config='-c tessedit_char_whitelist=0123456789.:/%ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz  ')
    
    data = extract_band_data(text)
    results[date] = data
    
    print(f'\n=== {date} ==')
    for k, v in data.items():
        print(f'  {k}: {v}')
    print(f'  RAW: {text[:200]}')

# 保存
out_path = os.path.join(BASE, 'band_sleep_data.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f'\n已保存: {out_path}')
