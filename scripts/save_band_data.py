# -*- coding: utf-8 -*-
"""华为手环睡眠截图数据（人工校验自OCR结果）"""
import json

BAND_DATA = {
    "20260505": {
        "wake_time": "05:52",
        "sleep_time": "22:54",
        "sleep_score": 83,       # 手环评分（十分制换算：8.3）
        "score_10": 8.3,
        "better_than_pct": 87,   # 超过87%用户
        "deep_sleep_str": "1h51min",
        "deep_sleep_min": 111,
        "total_sleep_score_text": "83分 睡眠时长 (04/29-05/05)"
    },
    "20260506": {
        "wake_time": "06:22",
        "sleep_time": "22:27",
        "sleep_score": 82,
        "score_10": 8.2,
        "better_than_pct": 82,
        "deep_sleep_str": "2h03min",
        "deep_sleep_min": 123,
        "total_sleep_score_text": "82分 睡眠时长 (04/30-05/06)"
    },
    "20260507": {
        "wake_time": "06:06",
        "sleep_time": "22:33",
        "sleep_score": 83,
        "score_10": 8.3,
        "better_than_pct": 87,
        "deep_sleep_str": "1h43min",
        "deep_sleep_min": 103,
        "awake_count": 3,
        "total_sleep_score_text": "83分 清醒次数 (05/01-05/07)"
    },
    "20260508": {
        "wake_time": "07:16",
        "sleep_time": "23:06",
        "sleep_score": 78,
        "score_10": 7.8,
        "deep_sleep_str": "1h19min",
        "deep_sleep_min": 79,
        "awake_count": 3,
        "total_sleep_score_text": "78分 清醒次数 (05/02-05/08)"
    },
    "20260509": {
        "wake_time": "06:33",
        "sleep_time": "23:58",
        "sleep_score": 76,
        "score_10": 7.6,
        "better_than_pct": 44,
        "deep_sleep_str": "1h30min",
        "deep_sleep_min": 90,
        "total_sleep_score_text": "76分 清醒次数 (05/03-05/09)"
    },
    "20260510": {
        "wake_time": "06:25",
        "sleep_time": "22:44",
        "sleep_score": 86,
        "score_10": 8.6,
        "better_than_pct": 96,
        "deep_sleep_str": "1h45min",
        "deep_sleep_min": 105,
        "total_sleep_score_text": "86分 睡眠时长 (05/04-05/10)"
    }
}

# 保存
base = r'D:\AISleepGen_Optimized\sleep-skin image database'
out_path = f'{base}\\band_sleep_data_verified.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(BAND_DATA, f, ensure_ascii=False, indent=2, default=str)
print(f'已保存: {out_path}')

# 手环评分 vs 主观评分对比
subjective = {
    "20260505": 6, "20260506": 4, "20260507": 5, 
    "20260508": 4, "20260509": 4, "20260510": 7
}
print('\n=== 手环评分 vs 主观评分 ===')
print(f'{"日期":>8s} {"手环(10分制)":>12s} {"主观评分":>8s} {"差值":>6s}')
for d in sorted(BAND_DATA.keys()):
    b = BAND_DATA[d]['score_10']
    s = subjective.get(d, 0)
    print(f'{d:>8s} {b:>10.1f}分 {s:>6d}分 {b-s:>+6.1f}')
