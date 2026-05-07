"""
sleep_audio_analyzer.py v2 — 睡眠音频分析引擎升级版

改进：
1. 支持800Hz和8kHz两种采样率
2. 更准确的鼾声检测（800Hz下用能量比，8kHz下用频域分析）
3. 多夜对比分析
4. 手环数据融合接口
5. 输出可直接注入POMDP上下文
"""
import numpy as np
from scipy.io import wavfile
from scipy import signal
import os, json, time, math

# 对不同采样率自适应
SNORE_CONFIG = {
    800:  {"band_low": 80, "band_high": 250, "threshold": 0.17},   # 800Hz下频带窄
    8000: {"band_low": 80, "band_high": 300, "threshold": 0.12},  # 8kHz下频带宽
}
BREATH_BAND = (200, 600)
MOVEMENT_WINDOW = 30  # 秒
MOVEMENT_HOP = 10

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SLEEP_RECORD_DIR = os.path.join(PROJECT_ROOT, "sleep_record")

_dummy_ring_measurement = {
    "20260504": {  # from woman_measurement_from_ring_20260505night.jpg
        "bedtime": "23:24", "waketime": "06:35",
        "total_sleep_min": 431,  # 7h11m
        "awake_min": 59,
        "deep_sleep_min": 175,   # 2h55m
        "light_sleep_min": 186,  # 3h6m
        "rem_min": 51,
        "heart_rate_avg": 60, "heart_rate_range": "55-65",
        "hrv": None,  # from image
        "respiratory_rate": None,
        "spo2": None,
        "movement_index": None,
        "sleep_score": 91,
        "source": "ring_screenshot"
    }
}

class SleepAudioAnalyzer:
    def __init__(self):
        self._cache = {}
    
    def analyze_file(self, wav_path: str) -> dict:
        """分析单段WAV音频"""
        t0 = time.time()
        sr, data = wavfile.read(wav_path)
        if data.ndim > 1:
            data = data.mean(axis=1)
        data = data.astype(np.float32)
        if np.max(np.abs(data)) > 0:
            data = data / np.max(np.abs(data))
        
        duration_sec = len(data) / sr
        cfg = SNORE_CONFIG.get(sr, SNORE_CONFIG[8000])
        
        result = {
            "file": os.path.basename(wav_path),
            "sr": sr,
            "duration_hours": round(duration_sec / 3600, 2),
            "snore": self._detect_snore(data, sr, cfg),
            "breath": self._estimate_breath_rate(data, sr),
            "movement": self._detect_movement(data, sr, duration_sec),
            "silence": self._analyze_silence(data, sr),
            "stability": self._sleep_stability(data, sr),
            "sleep_efficiency": self._estimate_sleep_efficiency(data, sr, duration_sec),
            "analysis_ms": round((time.time() - t0) * 1000, 1),
        }
        return result
    
    def analyze_all_wavs(self) -> list:
        """分析所有WAV文件，返回含日期的列表"""
        results = []
        for f in sorted(os.listdir(SLEEP_RECORD_DIR)):
            if f.endswith('.wav'):
                date = f[:8]
                print(f"  Analyzing {date} ({f})...")
                r = self.analyze_file(os.path.join(SLEEP_RECORD_DIR, f))
                r["date"] = date
                results.append(r)
        return results
    
    def build_sleep_context(self, wav_results: list, ring_data: dict = None) -> str:
        """生成可注入LLM/POMDP的睡眠上下文文本"""
        if not wav_results:
            return ""
        
        latest = wav_results[-1] if wav_results else None
        if not latest:
            return ""
        
        parts = []
        
        # 最新一晚摘要
        s = latest["snore"]
        m = latest["movement"]
        st = latest["stability"]
        eff = latest["sleep_efficiency"]
        parts.append(f"昨晚睡眠时长{latest['duration_hours']:.1f}小时")
        parts.append(f"鼾声占比{s['snore_pct']:.0f}%")
        parts.append(f"体动{m['total_movement_min']:.0f}分钟")
        parts.append(f"稳定性{st['score']}/100")
        parts.append(f"睡眠效率{eff:.0f}%")
        
        # 趋势
        if len(wav_results) >= 2:
            prev = wav_results[-2]
            delta = st["score"] - prev["stability"]["score"]
            if delta > 5:
                parts.append(f"稳定性比上晚改善+{delta:.0f}分")
            elif delta < -5:
                parts.append(f"稳定性比上晚下降{abs(delta):.0f}分")
        
        # 手环数据
        if ring_data:
            for date, rd in ring_data.items():
                if date in [r.get("date","") for r in wav_results[-3:]]:
                    parts.append(f"手环: 总睡{rd['total_sleep_min']}分,深睡{rd['deep_sleep_min']}分,浅睡{rd['light_sleep_min']}分,REM{rd['rem_min']}分,心率{rd['heart_rate_avg']},评分{rd['sleep_score']}")
        
        return "; ".join(parts)
    
    def _detect_snore(self, data, sr, cfg):
        """检测鼾声"""
        nperseg = min(int(sr * 2), len(data))
        if nperseg < 32:
            return {"total_snore_min": 0, "snore_pct": 0}
        
        f, t, Sxx = signal.spectrogram(data, sr, nperseg=nperseg, noverlap=nperseg//2)
        
        snore_band = (f >= cfg["band_low"]) & (f <= cfg["band_high"])
        full_band = f <= sr//2
        
        snore_energy = np.sum(Sxx[snore_band, :], axis=0)
        total_energy = np.sum(Sxx[full_band, :], axis=0) + 1e-10
        snore_ratio = snore_energy / total_energy
        
        # 滑动平均平滑
        kernel = np.ones(5) / 5
        snore_smoothed = np.convolve(snore_ratio, kernel, mode='same')
        
        snore_mask = snore_smoothed > cfg["threshold"]
        snore_pct = float(np.mean(snore_mask)) * 100 if len(snore_mask) > 0 else 0
        total_snore_sec = snore_pct / 100 * t[-1] if len(t) > 0 else 0
        
        return {
            "total_snore_min": round(total_snore_sec / 60, 1),
            "snore_pct": round(snore_pct, 1),
            "threshold_used": cfg["threshold"]
        }
    
    def _estimate_breath_rate(self, data, sr):
        """估算呼吸率"""
        hop = int(sr * 0.1)
        window = int(sr * 0.5)
        if len(data) < window + hop:
            return {"estimated_bpm": 0}
        
        energy = np.array([
            np.sum(data[i:i+window]**2)
            for i in range(0, len(data)-window, hop)
        ], dtype=np.float64)
        
        if len(energy) < 50:
            return {"estimated_bpm": 0}
        
        from scipy import signal as sg
        sos = sg.butter(4, [0.1, 0.5], btype='band', fs=1/(hop/sr), output='sos')
        filtered = sg.sosfilt(sos, energy - np.mean(energy))
        
        peaks, _ = sg.find_peaks(filtered, distance=int(sr/hop*2))
        if len(peaks) < 3:
            return {"estimated_bpm": 0}
        
        total_min = (peaks[-1] - peaks[0]) * hop / sr / 60
        if total_min < 0.5:
            return {"estimated_bpm": 0}
        
        return {"estimated_bpm": round(len(peaks) / total_min, 1)}
    
    def _detect_movement(self, data, sr, duration_sec):
        """检测体动"""
        win = int(sr * MOVEMENT_WINDOW)
        hop = int(sr * MOVEMENT_HOP)
        if win >= len(data):
            return {"total_movement_min": 0, "num_events": 0}
        
        energies = np.array([
            np.sqrt(np.mean(data[i:i+win]**2))
            for i in range(0, len(data)-win, hop)
        ])
        
        if len(energies) < 2:
            return {"total_movement_min": 0, "num_events": 0}
        
        mean_e = np.mean(energies)
        threshold = mean_e + 0.15 * (np.std(energies) + mean_e)
        
        mov_idx = np.where(energies > threshold)[0]
        events = 0
        if len(mov_idx) > 0:
            groups = np.split(mov_idx, np.where(np.diff(mov_idx) > 1)[0] + 1)
            events = len(groups)
        
        total_mov_sec = len(mov_idx) * MOVEMENT_HOP
        
        return {
            "total_movement_min": round(total_mov_sec / 60, 1),
            "num_events": events,
            "threshold": round(float(threshold), 4)
        }
    
    def _analyze_silence(self, data, sr):
        """安静时段分析"""
        hop = int(sr)
        if hop >= len(data):
            return {"silent_min": 0, "silent_ratio": 0}
        
        silent = 0
        total = 0
        for i in range(0, len(data) - hop, hop):
            rms = np.sqrt(np.mean(data[i:i+hop]**2))
            if rms < 0.008:
                silent += 1
            total += 1
        
        return {
            "silent_min": round(silent / 60, 1),
            "silent_ratio": round(silent / max(total, 1), 3)
        }
    
    def _sleep_stability(self, data, sr):
        """睡眠稳定性"""
        hop = int(sr * 60)
        if hop >= len(data):
            return {"score": 0, "interpretation": "unknown"}
        
        energies = []
        for i in range(0, len(data) - hop, hop):
            energies.append(np.sqrt(np.mean(data[i:i+hop]**2)))
        
        if len(energies) < 2:
            return {"score": 0, "interpretation": "unknown"}
        
        energies = np.array(energies)
        cv = np.std(energies) / (np.mean(energies) + 1e-10)
        score = max(0, min(100, 100 - cv * 40))
        
        interp = "stable" if score > 70 else "moderate" if score > 40 else "unstable"
        return {"score": round(float(score), 1), "cv": round(float(cv), 3), "interpretation": interp}
    
    def _estimate_sleep_efficiency(self, data, sr, duration_sec):
        """估算睡眠效率（安静时间占比）"""
        hop = int(sr * 30)
        if hop >= len(data):
            return 0
        
        quiet = 0
        total = 0
        for i in range(0, len(data) - hop, hop):
            rms = np.sqrt(np.mean(data[i:i+hop]**2))
            if rms < 0.015:
                quiet += 1
            total += 1
        
        return round(quiet / max(total, 1) * 100, 1)
    
    def audio_to_pomdp_observation(self, wav_results: list, ring_data: dict = None) -> dict:
        """将音频分析结果转换为POMDP可消费的观测"""
        if not wav_results:
            return {}
        
        latest = wav_results[-1]
        
        obs = {
            "sleep_efficiency": latest.get("sleep_efficiency", 0),
            "stability": latest["stability"]["score"],
            "snore_pct": latest["snore"]["snore_pct"],
            "movement_min": latest["movement"]["total_movement_min"],
            "breath_rate": latest["breath"]["estimated_bpm"],
            "duration_hours": latest["duration_hours"],
        }
        
        if ring_data:
            for date, rd in ring_data.items():
                if date in [r.get("date","") for r in wav_results[-3:]]:
                    obs.update({
                        "ring_deep_sleep_min": rd["deep_sleep_min"],
                        "ring_light_sleep_min": rd["light_sleep_min"],
                        "ring_rem_min": rd["rem_min"],
                        "ring_heart_rate": rd["heart_rate_avg"],
                        "ring_sleep_score": rd["sleep_score"],
                        "ring_total_sleep_min": rd["total_sleep_min"],
                    })
                    break
        
        return obs

def get_analyzer():
    return SleepAudioAnalyzer()

if __name__ == "__main__":
    ana = SleepAudioAnalyzer()
    wavs = ana.analyze_all_wavs()
    
    print(f"\n=== All {len(wavs)} nights analyzed ===")
    for r in wavs:
        d = r["date"]
        s = r["snore"]
        m = r["movement"]
        st = r["stability"]
        e = r["sleep_efficiency"]
        print(f"  {d}: {r['duration_hours']:.1f}h, snore={s['snore_pct']:.0f}%, mov={m['total_movement_min']:.0f}m, stable={st['score']}/100, eff={e:.0f}%")
    
    print(f"\nSleep context: {ana.build_sleep_context(wavs, _dummy_ring_measurement)}")
    print(f"\nPOMDP obs: {ana.audio_to_pomdp_observation(wavs, _dummy_ring_measurement)}")
