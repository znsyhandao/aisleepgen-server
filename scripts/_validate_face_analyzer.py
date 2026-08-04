# -*- coding: utf-8 -*-
"""端到端验证：对多张照片跑 face_analyzer，看结果是否不一样"""
import sys, os, json, base64
sys.path.insert(0, r'D:\AISleepGen_Optimized')

# 直接调 face_analyzer（不经过 HTTP）
from face_analyzer import analyze_from_path

# 挑 5 张不同日期的照片
test_cases = [
    ('20260419 评分8', r'D:\AISleepGen_Optimized\sleep-skin image database\20260419\IMG_20260419_071146.jpg'),
    ('20260425 评分4', r'D:\AISleepGen_Optimized\sleep-skin image database\20260425\IMG_20260425_074516.jpg'),
    ('20260505 评分6', r'D:\AISleepGen_Optimized\sleep-skin image database\20260505\IMG_20260505_073139.jpg'),
    ('20260508 评分4 睡前', r'D:\AISleepGen_Optimized\sleep-skin image database\20260508\IMG_20260508_214346.jpg'),
    ('20260509 评分4 醒后', r'D:\AISleepGen_Optimized\sleep-skin image database\20260509\IMG_20260509_073454_1.jpg'),
]

print('=' * 60)
print('  face_analyzer 端到端验证')
print('  测试 5 张不同照片是否输出不同评分')
print('=' * 60)

results = []
for label, fpath in test_cases:
    if not os.path.exists(fpath):
        print(f'\n  [SKIP] {label}: 文件不存在')
        continue
    r = analyze_from_path(fpath)
    score = r.get('predicted_score', 'N/A')
    face = r.get('face_detected', False)
    features = r.get('features', {})
    print(f'\n  {label}')
    print(f'    预测评分: {score}')
    print(f'    人脸检测: {face}')
    if features:
        print(f'    亮度(lab_L): {features.get("lab_L_mean", "N/A"):.1f}')
        print(f'    眉间纹理(fatigue): {features.get("fatigue_brow_texture", "N/A"):.1f}')
        print(f'    额头亮度(forehead): {features.get("roi_forehead_L", "N/A"):.1f}')
    results.append({'label': label, 'score': score, 'face_detected': face})

print('\n' + '=' * 60)
print('  汇总')
print('=' * 60)
scores = [r['score'] for r in results if r['score'] != 'N/A']
for r in results:
    print(f'  {r["label"]:20s}: {r["score"]}')
if len(scores) >= 2:
    print(f'\n  评分范围: {min(scores):.1f} ~ {max(scores):.1f} (差异 {max(scores)-min(scores):.1f} 分)')
    print(f'  如果所有评分一样 → 有问题')
    print(f'  如果不一样 → 模型有效')
