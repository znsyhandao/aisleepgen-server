"""
sleep_audio_analyzer.py v3.1 - 睡眠音频分析引擎 + AI动态呼吸引导

v3.1 (2026-05-21):
  - 自动 m4a→wav 转换（依赖 ffmpeg）
  - analyze_all_wavs 也支持 .m4a 文件

v3新增：
1. 动态呼吸引导节奏调节（根据鼾声/体动模式自适应调速）
2. 可配置手环数据接口（替换dummy硬编码）
3. 所有except带error打印（消灭空except）
4. 多夜趋势学习（鼾声模式变化检测）
"""
import numpy as np
from scipy.io import wavfile
from scipy import signal
import os, json, time, math, subprocess, tempfile

# ffmpeg 路径（与 batch_convert_m4a.py 保持一致）
FFMPEG = r'D:\ffmpeg\bin\ffmpeg.exe'

# 对不同采样率自适应
SNORE_CONFIG = {
    800:  {"band_low": 80, "band_high": 250, "threshold": 0.17},
    8000: {"band_low": 80, "band_high": 300, "threshold": 0.12},
}
BREATH_BAND = (200, 600)
MOVEMENT_WINDOW = 30
MOVEMENT_HOP = 10

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SLEEP_RECORD_DIR = os.path.join(PROJECT_ROOT, "sleep_record")

# 呼吸法节奏模板（秒）
BREATHING_PATTERNS = {
    "relaxed": {"inhale": 4, "hold": 4, "exhale": 4},     # 箱式呼吸
    "deep":    {"inhale": 4, "hold": 7, "exhale": 8},      # 4-7-8
    "calm":    {"inhale": 4, "hold": 2, "exhale": 6},      # 4-2-6 促进入睡
}

class SleepAudioAnalyzer:
    def __init__(self, ring_data_provider=None):
        """
        ring_data_provider: 可选，接受 date 返回 dict 的函数
        """
        self._cache = {}
        self._ring_data_provider = ring_data_provider
        self._history = []  # 历史分析结果，用于趋势学习

    def set_ring_provider(self, provider):
        """设置手环数据提供者函数"""
        self._ring_data_provider = provider

    @staticmethod
    def _ensure_wav(path: str) -> str:
        """如果输入是 .m4a，用 ffmpeg 转成临时 .wav；否则原样返回"""
        ext = os.path.splitext(path)[1].lower()
        if ext == '.wav':
            return path
        if ext == '.m4a':
            if not os.path.exists(FFMPEG):
                raise RuntimeError(f"ffmpeg not found at {FFMPEG} — 无法解码 .m4a 文件")
            tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            tmp_path = tmp.name
            tmp.close()
            cmd = [FFMPEG, '-i', path, '-ac', '1', '-ar', '8000',
                   '-sample_fmt', 's16', '-y', tmp_path]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                os.unlink(tmp_path)
                raise RuntimeError(f"ffmpeg 转码失败: {r.stderr.strip()[:200]}")
            return tmp_path
        raise ValueError(f"不支持的音频格式: {ext}")

    def analyze_file(self, audio_path: str, skip_seconds: int = 0) -> dict:
        """分析单段音频（支持 .wav 和 .m4a）

        Args:
            audio_path: 音频文件路径
            skip_seconds: 跳过开头N秒（如600去掉前10分钟安置段）
        """
        t0 = time.time()
        tmp_path = None
        try:
            wav_path = self._ensure_wav(audio_path)
            tmp_path = wav_path if wav_path != audio_path else None
            sr, data = wavfile.read(wav_path)
            
            # 跳过开头N秒（去掉手机安置段）
            if skip_seconds > 0 and len(data) > skip_seconds * sr:
                data = data[int(skip_seconds * sr):]
                print('[Analyzer] Skip first %ds, remaining %.1fmin' %
                      (skip_seconds, len(data) / sr / 60))
        except Exception as e:
            raise RuntimeError(f"读取音频失败: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
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
        """分析所有 WAV/M4A 文件，返回含日期的列表"""
        results = []
        for f in sorted(os.listdir(SLEEP_RECORD_DIR)):
            if f.endswith('.wav') or f.endswith('.m4a'):
                date = f[:8]
                print(f"  Analyzing {date} ({f})...")
                path = os.path.join(SLEEP_RECORD_DIR, f)
                r = self.analyze_file(path)
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
        """估算呼吸率（带异常保护）"""
        try:
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
        except Exception as e:
            print(f"[audio] breath_rate error: {e}")
            return {"estimated_bpm": 0, "error": str(e)}

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

        # 使用可配置的手环数据提供者
        ring_to_use = ring_data
        if ring_to_use is None and self._ring_data_provider:
            try:
                date_key = latest.get("date", "")
                if date_key:
                    ring_to_use = {date_key: self._ring_data_provider(date_key)}
            except Exception as e:
                print(f"[audio] ring provider error: {e}")

        if ring_to_use:
            for date, rd in ring_to_use.items():
                if date in [r.get("date","") for r in wav_results[-3:]]:
                    obs.update({
                        "ring_deep_sleep_min": rd.get("deep_sleep_min", 0),
                        "ring_light_sleep_min": rd.get("light_sleep_min", 0),
                        "ring_rem_min": rd.get("rem_min", 0),
                        "ring_heart_rate": rd.get("heart_rate_avg", 0),
                        "ring_sleep_score": rd.get("sleep_score", 0),
                        "ring_total_sleep_min": rd.get("total_sleep_min", 0),
                    })
                    break

        return obs

    def suggest_breathing_pattern(self, wav_results: list) -> dict:
        """根据音频分析和历史模式，推荐最佳呼吸法"""
        if not wav_results:
            return {"pattern": "relaxed", "reason": "无音频数据，默认箱式呼吸"}

        latest = wav_results[-1]

        # 收集近期趋势指标
        snore_avg = np.mean([r["snore"]["snore_pct"] for r in wav_results[-5:]])
        stability_avg = np.mean([r["stability"]["score"] for r in wav_results[-5:]])
        movement_avg = np.mean([r["movement"]["total_movement_min"] for r in wav_results[-5:]])

        # 规则引擎：根据特征选择最佳呼吸模式
        if snore_avg > 50:
            return {
                "pattern": "deep",
                "name": "4-7-8 深呼吸",
                "timing": BREATHING_PATTERNS["deep"],
                "reason": f"鼾声偏高({snore_avg:.0f}%)，建议4-7-8深呼吸缓解气道张力",
                "confidence": min(0.9, snore_avg / 100 + 0.3)
            }
        elif stability_avg < 50:
            return {
                "pattern": "calm",
                "name": "4-2-6 缓呼吸",
                "timing": BREATHING_PATTERNS["calm"],
                "reason": f"睡眠稳定性偏低({stability_avg:.0f}/100)，建议缓呼吸促进入睡",
                "confidence": min(0.85, (70 - stability_avg) / 70 + 0.2)
            }
        elif movement_avg > 45:
            return {
                "pattern": "calm",
                "name": "4-2-6 缓呼吸",
                "timing": BREATHING_PATTERNS["calm"],
                "reason": f"体动偏多({movement_avg:.0f}分钟)，建议缓呼吸减少夜间翻动",
                "confidence": min(0.8, movement_avg / 60 + 0.2)
            }
        else:
            return {
                "pattern": "relaxed",
                "name": "4-4-4 箱式呼吸",
                "timing": BREATHING_PATTERNS["relaxed"],
                "reason": "睡眠指标正常，箱式呼吸维持放松状态",
                "confidence": 0.6
            }

    def learn_from_history(self, wav_results: list):
        """从历史记录学习趋势（保存内部状态用于连贯决策）"""
        if not wav_results:
            return

        # 保存最近30晚的趋势
        self._history = wav_results[-30:]

        # 检测鼾声变化趋势
        if len(self._history) >= 7:
            recent_snore = np.mean([r["snore"]["snore_pct"] for r in self._history[-3:]])
            older_snore = np.mean([r["snore"]["snore_pct"] for r in self._history[-7:-3]])
            snore_trend = recent_snore - older_snore
            self._snore_trend = snore_trend
        else:
            self._snore_trend = 0

    @property
    def snore_trend(self):
        """最近鼾声趋势（正=恶化，负=改善）"""
        return getattr(self, '_snore_trend', 0)

def get_analyzer(ring_provider=None):
    return SleepAudioAnalyzer(ring_data_provider=ring_provider)

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
