# -*- coding: utf-8 -*-
"""快速分析3个EDF文件"""
import os, time, numpy as np
from mne.io import read_raw_edf
from scipy import signal as sp_signal
from scipy.signal import find_peaks

DATA_DIR = r'D:\AISleepGen_Optimized\sleep_edf_dataset'

files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith('.edf')])
results = {}

for fname in files:
    fpath = os.path.join(DATA_DIR, fname)
    size = os.path.getsize(fpath)
    t0 = time.time()

    raw = read_raw_edf(fpath, preload=False, verbose='ERROR')
    sfreq = raw.info['sfreq']
    n_times = raw.n_times
    ch_names = raw.ch_names
    duration_h = n_times / sfreq / 3600

    # 选择关键通道
    eeg_channels = ['C3A2', 'C4A1', 'F3', 'F4', 'C3', 'C4', 'O1', 'O2']
    eog_channels = ['EOG1', 'EOG2']
    emg_channels = ['EMG', 'EMG1', 'EMG2']
    ecg_channels = ['ECGII']

    has_eeg = [c for c in eeg_channels if c in ch_names]
    has_eog = [c for c in eog_channels if c in ch_names]
    has_emg = [c for c in emg_channels if c in ch_names]
    has_ecg = [c for c in ecg_channels if c in ch_names]

    # 取5分钟EEG数据做简单PSD
    raw.load_data()
    pick = has_eeg[0] if has_eeg else ch_names[0]
    data_5min, _ = raw[pick, 0:int(sfreq*300)]
    data_5min = data_5min.flatten()

    # Welch PSD
    freqs, psd = sp_signal.welch(data_5min, sfreq, nperseg=sfreq*4, noverlap=sfreq*2)

    # 频带功率
    bands = {
        'delta': (0.5, 4),
        'theta': (4, 8),
        'alpha': (8, 13),
        'sigma': (12, 16),
        'beta': (13, 30),
    }
    band_power = {}
    for name, (lo, hi) in bands.items():
        mask = (freqs >= lo) & (freqs < hi)
        band_power[name] = float(np.trapezoid(psd[mask], freqs[mask]))

    # HRV
    hrv = None
    if has_ecg:
        ecg_data, _ = raw[ecg_channels[0], :]
        ecg_data = ecg_data.flatten()
        peaks, _ = find_peaks(ecg_data, distance=sfreq*0.3, height=np.median(ecg_data)*1.5)
        rri = np.diff(peaks) / sfreq * 1000
        if len(rri) > 10:
            sdnn = float(np.std(rri))
            rmssd = float(np.sqrt(np.mean(np.diff(rri)**2)))
            hrv = {'SDNN': round(sdnn, 1), 'RMSSD': round(rmssd, 1), 'R_peaks': len(peaks)}

    elapsed = time.time() - t0
    results[fname] = {
        'size_mb': round(size/1e6, 1),
        'sfreq': sfreq,
        'channels': len(ch_names),
        'duration_h': round(duration_h, 2),
        'has_eeg': has_eeg[:3],
        'has_eog': has_eog,
        'has_emg': has_emg,
        'has_ecg': has_ecg,
        'band_power': band_power,
        'hrv': hrv,
        'analysis_s': round(elapsed, 1),
    }

    ecg_str = "Y" if has_ecg else "N"
    eeg_str = has_eeg[0] if has_eeg else "N/A"
    print("[%s] %.1fh | %dch | ECG:%s | EEG:%s" % (
        fname, duration_h, len(ch_names), ecg_str, eeg_str))
    print("  频带(uV2): Delta=%.1f Theta=%.1f Alpha=%.1f Sigma=%.1f Beta=%.1f" % (
        band_power['delta'], band_power['theta'], band_power['alpha'],
        band_power['sigma'], band_power['beta']))
    if hrv:
        print("  HRV: SDNN=%sms RMSSD=%sms (%d R峰)" % (
            hrv['SDNN'], hrv['RMSSD'], hrv['R_peaks']))
    print("  分析耗时: %.1fs" % elapsed)

print()
print("="*60)
print("总结:")
for fname, r in results.items():
    status = "OK" if r['hrv'] else "NO_ECG"
    print("  %s [%s] %s (%dMB, %.1fh)" % (
        status, fname, r['size_mb'], r['size_mb'], r['duration_h']))
