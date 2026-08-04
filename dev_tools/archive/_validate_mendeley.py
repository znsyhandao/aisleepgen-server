# -*- coding: utf-8 -*-
"""
验证 Mendeley 失眠数据集 — EDF 分析 vs Excel 金标准
先跑已有的3个EDF + 全部22个受试者的Excel评分数据对比
"""
import os, json, openpyxl
import numpy as np
from mne.io import read_raw_edf
from scipy.signal import find_peaks, welch
from numpy import trapezoid

DATA_DIR = r'D:\AISleepGen_Optimized\sleep_edf_dataset'
XLSX = os.path.join(DATA_DIR, 'PSG_Psycho_Normal.xlsx')

# ===== 1. 解析Excel金标准 =====
print('='*60)
print('第1步：解析Excel金标准')
print('='*60)

wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb['Subjects']
headers = [str(c.value) for c in next(ws.iter_rows(min_row=1, max_row=1))]

# 构建受试者查找表
subjects_meta = {}
for row in ws.iter_rows(min_row=3, values_only=True):
    name = str(row[0]) if row[0] else ''
    if not name or name == 'None':
        continue
    subjects_meta[name] = {
        'TST': row[headers.index('TST')],
        'SE': row[headers.index('SE')],
        'AHI': row[headers.index('AHI')],
        'AvgHR': row[headers.index('AverageHR')],
        'SpO2_avg': row[headers.index('AverageSpO2')],
        'SpO2_min': row[headers.index('MinimalSpO2')],
        'PLMs': row[headers.index('PLMs')],
        'SnoreIdx': row[headers.index('SnoreIndex')],
        'Diagnosis_Insomnia': row[headers.index('Diagnosis.Insomnia')],
        'ESS_T': row[headers.index('ESS.T')],
        'Age': row[headers.index('Age')],
        'Gender': row[headers.index('Gender')],
        'BMI': row[headers.index('BMI')],
        'Wake_I': row[headers.index('Wake.I')],
        'REM_ST': row[headers.index('REM.ST')],
    }

print('Excel中共 %d 个受试者' % len(subjects_meta))
for name, meta in sorted(subjects_meta.items()):
    ins = meta['Diagnosis_Insomnia']
    label = '失眠' if ins == '1' else ('正常' if ins == '2' else '?')
    print('  %s: TST=%.1f SE=%.1f%% AHI=%.1f HR=%s %s' % (
        name, meta['TST'] or 0, meta['SE'] or 0, meta['AHI'] or 0,
        meta['AvgHR'], label))

# ===== 2. 分析已有EDF =====
print()
print('='*60)
print('第2步：分析已有EDF文件')
print('='*60)

edf_files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith('.edf')])
results = {}

for fname in edf_files:
    # 提取受试者名
    base = fname.replace('.edf', '')
    # 尝试匹配 Excel 中的名字
    meta = subjects_meta.get(base, None)
    if not meta:
        # 模糊匹配
        for k in subjects_meta:
            if k in fname or fname.replace('.edf','') in k:
                meta = subjects_meta[k]
                break
    
    print()
    print('--- %s ---' % fname)
    if meta:
        print('  金标准匹配: TST=%.1f SE=%.1f AHI=%.1f' % (
            meta['TST'] or 0, meta['SE'] or 0, meta['AHI'] or 0))
    else:
        print('  未匹配到Excel金标准')
    
    fpath = os.path.join(DATA_DIR, fname)
    raw = read_raw_edf(fpath, preload=True, verbose='ERROR')
    sfreq = raw.info['sfreq']
    ch_names = raw.ch_names
    
    # 通道选择
    eeg_chan = [c for c in ['C3A2', 'C4A1', 'F3', 'F4', 'C3', 'C4', 'O1', 'O2'] if c in ch_names]
    ecg_chan = [c for c in ['ECGII'] if c in ch_names]
    spo2_chan = [c for c in ['SpO2'] if c in ch_names]
    
    # --- HRV ---
    hrv = None
    if ecg_chan:
        ecg_data, _ = raw[ecg_chan[0], :]
        ecg_data = ecg_data.flatten()
        # 单位: 伏特 -> uV. ECG通常 1mV = 0.001V, 放缩到mV
        if np.std(ecg_data) < 0.01:
            ecg_data = ecg_data * 1e6  # V -> uV
        peaks, props = find_peaks(ecg_data, distance=sfreq*0.25, 
                                   height=np.median(ecg_data) + np.std(ecg_data)*1.5)
        rri = np.diff(peaks) / sfreq * 1000
        rri = rri[(rri > 300) & (rri < 1500)]  # 过滤异常RRI
        
        if len(rri) > 30:
            sdnn = float(np.std(rri))
            rmssd = float(np.sqrt(np.mean(np.diff(rri)**2)))
            mean_hr = float(60000 / np.mean(rri)) if np.mean(rri) > 0 else 0
            hrv = {'SDNN_ms': round(sdnn, 1), 'RMSSD_ms': round(rmssd, 1),
                   'MeanHR_bpm': round(mean_hr, 1), 'R_peaks': len(peaks),
                   'valid_RRI': len(rri)}
            print('  HRV: HR=%s SDNN=%sms RMSSD=%sms (RRI=%d)' % (
                hrv['MeanHR_bpm'], hrv['SDNN_ms'], hrv['RMSSD_ms'], hrv['valid_RRI']))
        else:
            print('  HRV: 不足(' + str(len(rri)) + '个RRI)')
    else:
        print('  HRV: 无ECG通道')
    
    # --- EEG频带功率 ---
    bands_result = {}
    if eeg_chan:
        # 取中间1小时数据做分析（避免睡前/醒后边缘区）
        mid_start = int(sfreq * 3600 * 3.5)  # 3.5h处
        mid_end = int(sfreq * 3600 * 4.5)    # 4.5h处
        data, _ = raw[eeg_chan[0], mid_start:mid_end]
        data = data.flatten()
        # 转uV如果原数据是V
        if np.std(data) < 0.001:
            data = data * 1e6
        
        freqs, psd = welch(data, sfreq, nperseg=sfreq*4, noverlap=sfreq*2)
        
        bands = {'delta': (0.5,4), 'theta': (4,8), 'alpha': (8,13),
                 'sigma': (12,16), 'beta': (13,30)}
        for bname, (lo, hi) in bands.items():
            mask = (freqs >= lo) & (freqs < hi)
            bands_result[bname] = round(float(trapezoid(psd[mask], freqs[mask])), 2)
        
        print('  EEG频带(uV2): Delta=%.2f Theta=%.2f Alpha=%.2f Sigma=%.2f Beta=%.2f' % (
            bands_result.get('delta',0), bands_result.get('theta',0),
            bands_result.get('alpha',0), bands_result.get('sigma',0),
            bands_result.get('beta',0)))
    else:
        print('  EEG: 无EEG通道')
    
    # --- SpO2 ---
    spo2_avg = None
    if spo2_chan:
        spo2_data, _ = raw[spo2_chan[0], :]
        spo2_data = spo2_data.flatten()
        spo2_data = spo2_data[spo2_data > 50]  # 过滤无效
        if len(spo2_data) > 0:
            spo2_avg = round(float(np.mean(spo2_data)), 1)
            print('  SpO2: 平均=%s%%' % spo2_avg)
    
    results[fname] = {
        'base_name': base,
        'meta': meta,
        'hrv': hrv,
        'bands': bands_result,
        'spo2_avg': spo2_avg,
        'channels': len(ch_names),
        'duration_h': round(raw.n_times/sfreq/3600, 2),
    }

# ===== 3. 金标准对比 =====
print()
print('='*60)
print('第3步：EDF分析 vs Excel金标准 对比')
print('='*60)

for fname, r in sorted(results.items()):
    meta = r['meta']
    if not meta:
        print('  %s: 无金标准' % fname)
        continue
    
    print()
    print('  [%s]' % fname)
    
    # HR vs 金标准
    if r['hrv'] and meta['AvgHR']:
        hr_diff = abs(r['hrv']['MeanHR_bpm'] - float(meta['AvgHR']))
        print('    HR分析: %s vs 金标准%s | 偏差=%.1f' % (
            r['hrv']['MeanHR_bpm'], meta['AvgHR'], hr_diff))
    
    # 备注
    print('    时长: %sh' % r['duration_h'])
    if r['bands']:
        alpha_rel = r['bands']['alpha'] / (r['bands']['delta'] + 0.001)
        print('    Alpha/Delta比: %.3f' % alpha_rel)

# ===== 4. 生成下载清单 =====
print()
print('='*60)
print('第4步：待下载EDF清单')
print('='*60)

# 已有文件
existing = [f.replace('.edf', '') for f in edf_files]
print('已有 EDF (%d个):' % len(existing))
for f in edf_files:
    print('  ✅', f)

# 需要下的
need_to_download = []
for name in sorted(subjects_meta.keys()):
    edf_found = False
    for ext in ['']:  # 文件名可能不完全一致
        if name in existing or any(name in e for e in existing):
            edf_found = True
            break
    if not edf_found:
        need_to_download.append(name)
        meta = subjects_meta[name]
        ins = '失眠' if meta['Diagnosis_Insomnia'] == '1' else '正常'
        print('  ⬇ [%s] %s (TST=%.1f, SE=%.1f)' % (
            ins, name, meta['TST'] or 0, meta['SE'] or 0))

print()
print('待下载: %d 个' % len(need_to_download))
print('完成度: %d/22 = %.0f%%' % (len(existing), len(existing)/22*100))

# 保存分析结果
out = {
    'analysis_time': '2026-05-17 09:37',
    'total_subjects': len(subjects_meta),
    'existing_edf': len(existing),
    'need_to_download': len(need_to_download),
    'results': {k: {kk: vv for kk, vv in v.items() if kk != 'meta'} 
                for k, v in results.items()}
}
# 可序列化
with open(os.path.join(DATA_DIR, 'mendeley_validation.json'), 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2, default=str)
print('\n结果已保存到 mendeley_validation.json')
