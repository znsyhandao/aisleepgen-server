"""
voice_prosody.py — AISleepGen 语音韵律特征提取
纯 numpy+scipy+wave 实现，零外部音频库依赖。

特征:
  - speech_rate: 语速(音节/秒), 通过短时能量过零率估计
  - pause_ratio: 停顿比例(沉默时长/总时长)
  - energy: 短时能量统计(mean, std, delta, peak_freq)
  - f0: 基频估计(autocorrelation法)
  - spectral: 谱质心(明亮度), 谱通量(变化率)

输出: prosody_feature dict → 可注入 EmotionEngineV4.arousal_bump
"""

import io, math, struct
import numpy as np
from typing import Dict, Optional, Tuple, List


# ============================================================
# 常量
# ============================================================

SAMPLE_RATE = 16000          # 微信语音采样率
FRAME_LEN = 400              # 25ms 帧长 = 400 samples
FRAME_SHIFT = 160            # 10ms 帧移 = 160 samples
F0_MIN = 80                  # 基频下限 Hz
F0_MAX = 400                 # 基频上限 Hz
SILENCE_THRESHOLD_VOL = 0.02 # 静音能量阈值(归一化后)
MIN_VOICED_FRAMES = 3        # 最少有声帧数


def _read_wav(wav_bytes: bytes) -> Tuple[np.ndarray, int]:
    """从 bytes 读 WAV，返回 (samples, sample_rate)"""
    import wave as _wav
    with _wav.open(io.BytesIO(wav_bytes), 'rb') as wf:
        sr = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
        # 判断位深
        sw = wf.getsampwidth()
        if sw == 2:
            dtype = np.int16
            fmt = '<h'
        elif sw == 4:
            dtype = np.int32
            fmt = '<i'
        elif sw == 1:
            dtype = np.uint8
            fmt = 'B'
        else:
            raise ValueError(f'unsupported sample width: {sw}')
        channels = wf.getnchannels()
        samples = np.frombuffer(raw, dtype=dtype).astype(np.float64)
        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1)
        # 归一化到 [-1, 1]
        if dtype == np.int16:
            samples /= 32768.0
        elif dtype == np.int32:
            samples /= 2147483648.0
        elif dtype == np.uint8:
            samples = (samples - 128.0) / 128.0
        return samples, sr


def _frame_energy(samples: np.ndarray, frame_len: int, shift: int) -> np.ndarray:
    """分帧求短时能量(均方根)"""
    n = len(samples)
    n_frames = int(max(1, (n - frame_len) // shift + 1))
    energies = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * shift
        end = start + frame_len
        frame = samples[start:end]
        if len(frame) > 0:
            energies[i] = np.sqrt(np.mean(frame ** 2))
    return energies


def _frame_zcr(samples: np.ndarray, frame_len: int, shift: int) -> np.ndarray:
    """短时过零率"""
    n = len(samples)
    n_frames = int(max(1, (n - frame_len) // shift + 1))
    zcrs = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * shift
        end = start + frame_len
        frame = samples[start:end]
        if len(frame) > 1:
            signs = frame[1:] * frame[:-1]
            zcrs[i] = np.sum(signs < 0) / len(frame)
    return zcrs


def _estimate_f0(samples: np.ndarray, frame_len: int, shift: int, sr: int) -> np.ndarray:
    """自相关法基频估计"""
    n = len(samples)
    n_frames = int(max(1, (n - frame_len) // shift + 1))
    f0s = np.zeros(n_frames)
    min_lag = int(sr / F0_MAX)
    max_lag = int(sr / F0_MIN)
    for i in range(n_frames):
        start = i * shift
        end = start + frame_len
        frame = samples[start:end]
        if len(frame) < min_lag + 2:
            continue
        # 中心削波预处理
        clip_thr = 0.3 * np.max(np.abs(frame))
        clipped = np.where(np.abs(frame) > clip_thr, frame - np.sign(frame) * clip_thr, 0)
        # 自相关
        corr = np.correlate(clipped, clipped, mode='full')
        corr = corr[len(corr)//2:]
        if len(corr) <= max_lag + 1:
            continue
        seg = corr[min_lag:max_lag+1]
        peak_idx = np.argmax(seg)
        peak_val = seg[peak_idx]
        # 阈值检查
        if peak_val > 0.3 * corr[0]:  # 对比第 0 帧（自相关在 lag=0 时最高）
            f0s[i] = sr / (min_lag + peak_idx)
    return f0s


def _spectral_centroid(samples: np.ndarray, frame_len: int, shift: int, sr: int) -> np.ndarray:
    """谱质心（亮度估计）"""
    n = len(samples)
    n_frames = int(max(1, (n - frame_len) // shift + 1))
    cents = np.zeros(n_frames)
    # FFT bins
    freqs = np.fft.rfftfreq(frame_len, 1/sr)
    for i in range(n_frames):
        start = i * shift
        end = start + frame_len
        frame = samples[start:end]
        if len(frame) < frame_len:
            pad = np.zeros(max(0, frame_len - len(frame)))
            frame = np.concatenate([frame, pad])
        spec = np.abs(np.fft.rfft(frame))
        total = np.sum(spec)
        if total > 1e-6:
            cents[i] = np.sum(freqs * spec) / total
    return cents


def _spectral_flux(samples: np.ndarray, frame_len: int, shift: int) -> np.ndarray:
    """谱通量（频谱变化率）"""
    n = len(samples)
    n_frames = int(max(1, (n - frame_len) // shift + 1))
    flux = np.zeros(n_frames)
    prev = None
    for i in range(n_frames):
        start = i * shift
        end = start + frame_len
        frame = samples[start:end]
        if len(frame) < frame_len:
            pad = np.zeros(max(0, frame_len - len(frame)))
            frame = np.concatenate([frame, pad])
        spec = np.abs(np.fft.rfft(frame))
        spec = spec / (np.sum(spec) + 1e-10)  # 归一化
        if prev is not None:
            diff = spec - prev
            flux[i] = np.sqrt(np.sum(diff[diff > 0] ** 2))
        prev = spec
    return flux


def extract_prosody(wav_bytes: bytes,
                    sr: int = None) -> Dict:
    """
    从 WAV bytes 提取韵律特征。
    
    返回:
      speech_rate:    语速指数 (0~1), 基于能量变化的节奏密度
      pause_ratio:    停顿比例 (0~1), 沉默帧占比
      energy_mean:    平均音量 (0~1)
      energy_std:     音量标准差
      energy_delta:   音量变化率（帧间差分均值），高=情绪波动大
      energy_peak_freq: 能量高峰出现频率(次/秒)，高=急促
      f0_mean:        平均基频 (Hz) — 高=紧张/激动
      f0_std:         基频标准差 — 高=情绪丰富/不稳定
      f0_range:       基频范围(Hz) — 高=戏剧化/情绪化
      spectral_mean:  平均谱质心(Hz) — 高=明亮/紧张
      spectral_flux_mean: 谱通量均值 — 高=快速交替/不稳定
      voiced_ratio:   有声段占比
      duration_sec:   音频时长(秒)
      num_frames:     总帧数
      valid:          bool 是否有足够的语音信号
    """
    try:
        samples, fs = _read_wav(wav_bytes)
    except Exception:
        return _empty_result()
    
    if sr is not None and sr != fs:
        # 重采样到目标采样率(简单线性)
        ratio = sr / fs
        new_len = int(len(samples) * ratio)
        samples = np.interp(np.linspace(0, len(samples)-1, new_len),
                           np.arange(len(samples)), samples)
        fs = sr
    
    if len(samples) < FRAME_LEN:
        return _empty_result()
    
    nframes = max(1, (len(samples) - FRAME_LEN) // FRAME_SHIFT + 1)
    duration = len(samples) / fs
    if duration < 0.3:
        return _empty_result()
    
    # === 特征计算 ===
    energies = _frame_energy(samples, FRAME_LEN, FRAME_SHIFT)
    zcrs = _frame_zcr(samples, FRAME_LEN, FRAME_SHIFT)
    
    # 静音/有声判别
    voice_mask = energies > SILENCE_THRESHOLD_VOL
    voiced_ratio = np.mean(voice_mask) if len(voice_mask) > 0 else 0
    
    # 停顿：连续无声帧
    if len(voice_mask) > 0:
        pauses = []
        p_len = 0
        for v in voice_mask:
            if not v:
                p_len += 1
            else:
                if p_len > 0:
                    pauses.append(p_len)
                    p_len = 0
        if p_len > 0:
            pauses.append(p_len)
        pause_frames = sum(pauses)
        pause_ratio = pause_frames / len(voice_mask) if len(voice_mask) > 0 else 0.5
    else:
        pause_ratio = 0.5
    
    # 语速估计：基于能量变化率的峰值密度
    if len(energies) > 3:
        energy_diff = np.abs(np.diff(energies))
        # 找局部高峰（能量突升指示音节边界）
        peaks = np.zeros_like(energy_diff)
        if len(energy_diff) > 2:
            peaks[1:-1] = (energy_diff[1:-1] > energy_diff[:-2]) & (energy_diff[1:-1] > energy_diff[2:])
        peak_rate = np.sum(peaks) / duration if duration > 0 else 0
        # 归一化到 0~1（峰值率 > 10 = 非常快）
        speech_rate = min(1.0, peak_rate / 10)
    else:
        speech_rate = 0.3
    
    # 能量统计
    voiced_energies = energies[voice_mask]
    if len(voiced_energies) > 0:
        energy_mean = float(np.mean(voiced_energies))
        energy_std = float(np.std(voiced_energies))
    else:
        energy_mean = 0.0
        energy_std = 0.0
    
    # 能量变化率
    if len(energies) > 2:
        energy_delta = float(np.mean(np.abs(np.diff(energies))))
        # 能量高峰频率
        if len(energies) > 4:
            e_peaks = (energies[:-2] < energies[1:-1]) & (energies[1:-1] > energies[2:])
            energy_peak_freq = np.sum(e_peaks) / duration if duration > 0 else 0
        else:
            energy_peak_freq = 0
    else:
        energy_delta = 0
        energy_peak_freq = 0
    
    # F0 基频（只在有声段计算）
    f0s = _estimate_f0(samples, FRAME_LEN, FRAME_SHIFT, fs)
    voiced_f0 = f0s[f0s > 0]
    if len(voiced_f0) > MIN_VOICED_FRAMES:
        f0_mean = float(np.mean(voiced_f0))
        f0_std = float(np.std(voiced_f0))
        f0_range = float(np.ptp(voiced_f0))
    else:
        f0_mean = 0.0
        f0_std = 0.0
        f0_range = 0.0
    
    # 谱特征
    cents = _spectral_centroid(samples, FRAME_LEN, FRAME_SHIFT, fs)
    cents_voiced = cents[voice_mask]
    spectral_mean = float(np.mean(cents_voiced)) if len(cents_voiced) > 0 else 0
    
    flux = _spectral_flux(samples, FRAME_LEN, FRAME_SHIFT)
    flux_voiced = flux[voice_mask]
    flux_mean = float(np.mean(flux_voiced)) if len(flux_voiced) > 0 else 0
    
    valid = voiced_ratio > 0.05 and duration > 0.5
    
    return {
        'speech_rate': round(speech_rate, 4),
        'pause_ratio': round(pause_ratio, 4),
        'energy_mean': round(energy_mean, 4),
        'energy_std': round(energy_std, 4),
        'energy_delta': round(energy_delta, 4),
        'energy_peak_freq': round(energy_peak_freq, 4),
        'f0_mean': round(f0_mean, 1),
        'f0_std': round(f0_std, 1),
        'f0_range': round(f0_range, 1),
        'spectral_mean': round(spectral_mean, 1),
        'spectral_flux_mean': round(flux_mean, 6),
        'voiced_ratio': round(voiced_ratio, 4),
        'duration_sec': round(duration, 2),
        'num_frames': nframes,
        'valid': valid,
    }


def _empty_result() -> Dict:
    return {
        'speech_rate': 0, 'pause_ratio': 0.5,
        'energy_mean': 0, 'energy_std': 0, 'energy_delta': 0, 'energy_peak_freq': 0,
        'f0_mean': 0, 'f0_std': 0, 'f0_range': 0,
        'spectral_mean': 0, 'spectral_flux_mean': 0,
        'voiced_ratio': 0, 'duration_sec': 0, 'num_frames': 0,
        'valid': False,
    }


# ============================================================
# 韵律→情绪映射
# ============================================================

def prosody_to_arousal_bump(prosody: Dict) -> Dict:
    """
    将韵律特征映射到情绪调节值，供 EmotionEngineV4 使用。
    
    返回:
      arousal_bump:  [-0.3, 0.3] — 唤醒度增量调整
      intensity_bump: [-3, 3] — 强度增量
      valence_bump:  [-0.3, 0.3] — 效价增量（语音中微弱）
      confidence:    [0,1] — 韵律分析置信度
      cues:          str — 检测到的韵律线索描述
    """
    if not prosody.get('valid'):
        return {'arousal_bump': 0, 'intensity_bump': 0, 'valence_bump': 0,
                'confidence': 0, 'cues': 'invalid audio'}
    
    cues = []
    ab = 0.0  # arousal bump
    ib = 0   # intensity bump
    vb = 0.0  # valence bump
    
    # 1. 语速 → arousal
    sr = prosody['speech_rate']
    if sr > 0.7:
        ab += 0.25
        ib += 2
        cues.append('快速')
    elif sr < 0.25:
        ab -= 0.12
        ib -= 1
        cues.append('缓慢')
    
    # 2. 停顿比 → fatigue / hesitation
    pr = prosody['pause_ratio']
    if pr > 0.6:
        ab -= 0.15
        ib -= 1
        cues.append('多停顿')
    elif pr < 0.15:
        ab += 0.08
        ib += 1
        cues.append('少停顿')
    
    # 3. 能量变化率 → arousal / instability
    ed = prosody['energy_delta']
    if ed > 0.08:
        ab += 0.15
        ib += 1
        cues.append('能量波动大')
    elif ed < 0.02:
        ab -= 0.08
        cues.append('能量平稳')
    
    # 4. 能量高峰频率 → 急促/焦躁
    epf = prosody['energy_peak_freq']
    if epf > 5:
        ab += 0.20
        ib += 2
        cues.append('能量急促')
    elif epf < 1:
        ab -= 0.05
        cues.append('能量平缓')
    
    # 5. F0 均值 → arousal (高=紧张)
    f0m = prosody['f0_mean']
    if f0m > 250:
        ab += 0.18
        ib += 1
        cues.append('音调高')
    elif f0m > 200 and f0m <= 250:
        ab += 0.08
        ib += 1
        cues.append('音调偏高')
    elif f0m < 120 and f0m > 0:
        ab -= 0.10
        cues.append('音调低')
    
    # 6. F0 标准差 → 情绪丰富度/不稳定
    f0s = prosody['f0_std']
    if f0s > 60:
        ab += 0.12
        cues.append('音调变化大')
    elif f0s < 15 and f0s > 0:
        ab -= 0.05
        cues.append('音调单一')
    
    # 7. 谱通量 → 不稳定/快速转换
    flx = prosody['spectral_flux_mean']
    if flx > 0.005:
        ab += 0.10
        ib += 1
        cues.append('频谱活跃')
    
    # 8. 谱质心 → 品质/明亮度
    sp = prosody['spectral_mean']
    if sp > 3000:
        ab += 0.08
        cues.append('声音明亮')
    elif sp < 800 and sp > 0:
        ab -= 0.05
        cues.append('声音沉闷')
    
    # 置信度
    conf = min(1.0, prosody['duration_sec'] / 10 * 0.8 + 0.2)
    if not prosody.get('f0_mean', 0) > 0:
        conf *= 0.6  # F0 不可用降置信
    
    # 裁剪
    ab = max(-0.3, min(0.3, ab))
    ib = max(-3, min(3, ib))
    vb = max(-0.3, min(0.3, vb))
    
    return {
        'arousal_bump': round(ab, 3),
        'intensity_bump': ib,
        'valence_bump': round(vb, 3),
        'confidence': round(conf, 3),
        'cues': '+'.join(cues) if cues else 'neutral',
    }


def extract_and_map(wav_bytes: bytes) -> Dict:
    """一键提取+映射"""
    prosody = extract_prosody(wav_bytes)
    bump = prosody_to_arousal_bump(prosody)
    return {
        'prosody': prosody,
        'bump': bump,
    }


# ============================================================
# 测试
# ============================================================

def _generate_test_wav(duration_sec: float = 2.0, pitch: float = 200,
                       vol: float = 0.5, f0_vary: float = 0,
                       sr: int = 16000) -> bytes:
    """生成测试 WAV（纯音+噪声模拟语音）"""
    import struct
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    # 正弦波基音
    signal = np.sin(2 * np.pi * pitch * t)
    if f0_vary > 0:
        # 调频
        signal = np.sin(2 * np.pi * (pitch + f0_vary * np.sin(2 * np.pi * 3 * t)) * t)
    # 噪声调制（模拟语音的随机性）
    noise = np.random.randn(len(t)) * 0.1
    signal = signal * vol * 0.8 + noise * vol * 0.2
    # 加包络(起落)
    env = np.ones(len(t))
    attack = int(sr * 0.1)
    env[:attack] = np.linspace(0, 1, attack)
    decay = int(sr * 0.15)
    env[-decay:] = np.linspace(1, 0, decay)
    signal *= env
    # 16bit WAV
    signal = np.int16(signal * 32767 * 0.8)
    buf = io.BytesIO()
    import wave
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(signal.tobytes())
    return buf.getvalue()


if __name__ == '__main__':
    print('=== VoiceProsody 单元测试 ===\n')
    
    # 测试1: 快速紧张 (high f0, fast energy)
    wav1 = _generate_test_wav(2.0, pitch=280, vol=0.7, f0_vary=40)
    p1 = extract_prosody(wav1)
    b1 = prosody_to_arousal_bump(p1)
    print(f'  紧张快速: f0={p1["f0_mean"]:.0f}Hz sr={p1["speech_rate"]:.2f} '
          f'ab={b1["arousal_bump"]:+.2f} cues={b1["cues"]}')
    
    # 测试2: 缓慢低沉 (low f0, low vol)
    wav2 = _generate_test_wav(3.0, pitch=100, vol=0.25, f0_vary=5)
    p2 = extract_prosody(wav2)
    b2 = prosody_to_arousal_bump(p2)
    print(f'  缓慢低沉: f0={p2["f0_mean"]:.0f}Hz sr={p2["speech_rate"]:.2f} '
          f'ab={b2["arousal_bump"]:+.2f} cues={b2["cues"]}')
    
    # 测试3: 短音频（无效）
    wav3 = _generate_test_wav(0.2, pitch=200, vol=0.5)
    p3 = extract_prosody(wav3)
    print(f'  短音频无效: valid={p3["valid"]}')
    
    # 测试4: 高能量变化（激动）
    wav4 = _generate_test_wav(2.5, pitch=240, vol=0.9, f0_vary=60)
    p4 = extract_prosody(wav4)
    b4 = prosody_to_arousal_bump(p4)
    print(f'  高唤醒: f0={p4["f0_mean"]:.0f}Hz f0s={p4["f0_std"]:.0f} '
          f'ab={b4["arousal_bump"]:+.2f} ib={b4["intensity_bump"]:+d} '
          f'cues={b4["cues"]}')
    
    # 测试5: 静默（无效）
    wav5 = _generate_test_wav(1.0, pitch=200, vol=0.005)
    p5 = extract_prosody(wav5)
    print(f'  静默: valid={p5["valid"]}')
    
    print(f'\n  特征完备: {sorted(p1.keys())}')
    print(f'  全部通过 ✅')
