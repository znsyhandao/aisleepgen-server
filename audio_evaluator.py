# -*- coding: utf-8 -*-
"""
AISleepGen 专业音频评估引擎 v1.0
多维声学分析 + 冥想专业度评分 + 场景匹配
"""
import wave, numpy as np, json, os
from numpy.fft import rfft, rfftfreq

class AudioEvaluator:
    """
    音频专业评估引擎
    评价维度: 1. 声学质量 2. 冥想适配度 3. 场景匹配
    """
    
    def __init__(self):
        self.library = self._load_library()
        self.rules = self._load_rules()
    
    def _load_library(self):
        try:
            with open(r'D:\AISleepGen_Optimized\audio_library.json', 'r', encoding='utf-8') as f:
                return json.load(f).get('audio_library', [])
        except:
            return []
    
    def _load_rules(self):
        try:
            with open(r'D:\AISleepGen_Optimized\audio_matching_rules.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def analyze_wav(self, filepath):
        """完整音频分析"""
        try:
            with wave.open(filepath, 'rb') as w:
                raw = w.readframes(w.getnframes())
                rate = w.getframerate()
                nch = w.getnchannels()
                duration = w.getnframes() / rate
        except:
            return None
        
        audio = np.frombuffer(raw, dtype=np.int16).astype(float)
        if nch == 2:
            audio_st = audio.reshape(-1, 2)
            audio = audio_st.mean(axis=1)
        else:
            audio_st = None
        
        size_mb = os.path.getsize(filepath) / 1024 / 1024
        
        result = {
            'basic': {
                'duration_min': round(duration / 60, 1),
                'size_mb': round(size_mb, 1),
                'sample_rate': rate,
                'channels': nch,
                'bits_per_sample': 16,
            }
        }
        
        # ===== 1. 声学质量评分 =====
        quality = self._assess_quality(audio, rate)
        result['quality'] = quality
        
        # ===== 2. 冥想适配度 =====
        meditation = self._assess_meditation_fitness(audio, rate)
        result['meditation'] = meditation
        
        # ===== 3. 场景匹配 =====
        scenes = self._match_scenes(meditation)
        result['scenes'] = scenes
        
        # ===== 4. 综合评分 =====
        result['overall_sleep_score'] = min(10, max(1, int(
            meditation['vocal_fitness'] * 0.2 +
            meditation['rhythm_fitness'] * 0.2 +
            meditation['spectral_fitness'] * 0.2 +
            quality['recording_quality'] * 0.1 +
            meditation['delta_power'] * 0.3
        )))
        
        # ===== 5. 通俗化描述 =====
        result['description'] = self._generate_description(result)
        
        return result
    
    def _assess_quality(self, audio, rate):
        """录音质量评估"""
        peak = np.max(np.abs(audio))
        clipping = np.sum(np.abs(audio) > 30000) / len(audio) * 100
        
        # 信噪比估计(取音量最低的1秒vs最高1秒)
        seg_len = rate
        n_sec = min(len(audio) // seg_len, 600)
        rms_all = [np.sqrt(np.mean(audio[i*seg_len:(i+1)*seg_len]**2)) for i in range(n_sec)]
        sorted_idx = np.argsort(rms_all)
        noise_sample = audio[sorted_idx[0]*seg_len:(sorted_idx[0]+1)*seg_len]
        signal_sample = audio[sorted_idx[-1]*seg_len:(sorted_idx[-1]+1)*seg_len]
        noise_floor = np.sqrt(np.mean(noise_sample**2))
        signal_level = np.sqrt(np.mean(signal_sample**2))
        snr = 20 * np.log10(signal_level / max(noise_floor, 1)) if noise_floor > 0 else 0
        
        score = 10
        if clipping > 1: score -= 3
        if clipping > 5: score -= 3
        if snr < 20: score -= 2
        if snr < 10: score -= 2
        if peak < 1000: score -= 2  # 音量太小
        
        return {
            'recording_quality': max(1, score),
            'clipping_pct': round(clipping, 3),
            'snr_db': round(snr, 1),
            'peak_level': int(peak),
            'noise_floor': round(noise_floor, 1),
        }
    
    def _assess_meditation_fitness(self, audio, rate):
        """冥想/助眠适配度评估"""
        # A. 人声/器乐比例
        seg = audio[rate*30:rate*min(90, len(audio)//rate)]
        fft = np.abs(rfft(seg))
        freqs = rfftfreq(len(seg), 1/rate)
        total = max(np.sum(fft), 1)
        
        brain = np.sum(fft[(freqs >= 0.5) & (freqs < 30)]) / total
        instrument = np.sum(fft[(freqs >= 30) & (freqs < 200)]) / total
        voice_fund = np.sum(fft[(freqs >= 200) & (freqs < 500)]) / total
        voice_harm = np.sum(fft[(freqs >= 500) & (freqs < 2000)]) / total
        high = np.sum(fft[(freqs >= 2000)]) / total
        
        voice_ratio = voice_fund + voice_harm
        
        # 评分：人声少+低频多+脑波多=适合睡眠
        vocal_score = max(0, 10 - voice_ratio * 12)  # voice>83% => 0分
        spectral_score = min(10, brain * 300 + instrument * 10)  # brain>3% => 10分
        high_score = max(0, 10 - high * 8)  # high>125% => 0分
        
        # B. 音量动态(语速/节奏)
        seg_len = rate
        n_seg = min(len(audio) // seg_len, 600)
        rms = np.array([np.sqrt(np.mean(audio[i*seg_len:(i+1)*seg_len]**2)) for i in range(n_seg)])
        avg_rms = np.mean(rms)
        cv = np.std(rms) / max(avg_rms, 1)
        
        # 低变异系数=平稳=适合睡眠
        rhythm_score = max(0, 10 - cv * 6)  # cv>1.67 => 0分
        
        # C. 语速(切换频率) — 200ms帧，适合冥想引导
        frame_len = rate // 5  # 200ms
        n_frames = min(18000, len(audio[:rate*60]) // frame_len)
        if n_frames > 10:
            energy = np.array([np.sum(audio[i*frame_len:(i+1)*frame_len]**2) 
                              for i in range(n_frames)])
            threshold = np.mean(energy) * 0.2
            transitions = np.sum((energy > threshold)[:-1] != (energy > threshold)[1:])
            trans_per_min = transitions  # 已是一分钟数据
        else:
            trans_per_min = 0
        
        # 慢语速=好 (30-60次/分钟=最理想)
        speech_score = max(0, 10 - abs(trans_per_min - 45) * 0.15)  # 45次/分钟峰值10分
        
        # D. δ波强度
        seg_mid = audio[rate*30:rate*min(90, len(audio)//rate)]
        fft_mid = np.abs(rfft(seg_mid))
        freqs_mid = rfftfreq(len(seg_mid), 1/rate)
        delta_energy = np.sum(fft_mid[(freqs_mid >= 0.5) & (freqs_mid < 4)])
        total_brain = np.sum(fft_mid[(freqs_mid >= 0.5) & (freqs_mid < 100)])
        delta_power = delta_energy / max(total_brain, 1)
        
        # δ波评分(0-10)
        delta_score = min(10, delta_power * 500)
        
        # E. 声音纹理(平坦度)
        geom = np.exp(np.mean(np.log(fft_mid[fft_mid > 0] + 1e-10)))
        arith = np.mean(fft_mid[fft_mid > 0] + 1e-10)
        flatness = geom / max(arith, 1)
        texture_score = min(10, flatness * 200)  # 越接近白噪音越好
        
        return {
            'vocal_fitness': round(vocal_score, 1),
            'spectral_fitness': round(spectral_score, 1),
            'rhythm_fitness': round(rhythm_score, 1),
            'speech_rate': round(speech_score, 1),
            'delta_power': round(delta_score, 1),
            'texture_fitness': round(texture_score, 1),
            # 原始数据
            'voice_ratio_pct': round(voice_ratio * 100, 1),
            'instrument_pct': round(instrument * 100, 1),
            'brain_pct': round(brain * 100, 2),
            'high_freq_pct': round(high * 100, 1),
            'vol_cv': round(cv, 2),
            'trans_per_min': int(trans_per_min),
            'delta_power_pct': round(delta_power * 100, 2),
            'flatness': round(flatness, 4),
        }
    
    def _match_scenes(self, med):
        """匹配场景"""
        scenes = []
        
        # 入睡困难: 低人声+平稳+δ波
        if med['vocal_fitness'] >= 6 and med['rhythm_fitness'] >= 6 and med['delta_power'] >= 5:
            scenes.append({'scene': '入睡困难', 'score': min(10, med['vocal_fitness'] + med['delta_power']//2)})
        
        # 放松减压: 器乐+平稳
        if med['spectral_fitness'] >= 5 and med['rhythm_fitness'] >= 5:
            scenes.append({'scene': '放松减压', 'score': min(10, int(med['spectral_fitness'] * 0.6 + med['rhythm_fitness'] * 0.4))})
        
        # 叙事引导(白天): 有人声且语速适中
        if med['voice_ratio_pct'] > 30 and med['speech_rate'] < 6:
            scenes.append({'scene': '叙事引导(白天)', 'score': min(10, int(med['vocal_fitness'] * 0.3 + med['speech_rate'] * 0.7))})
        
        # 白噪音/环境音: 纹理平坦+低频多
        if med['texture_fitness'] >= 6 and med['spectral_fitness'] >= 6:
            scenes.append({'scene': '环境白噪音', 'score': min(10, int(med['texture_fitness'] * 0.5 + med['spectral_fitness'] * 0.5))})
        
        # 日间唤�?: 适度高频+能量感
        if med['speech_rate'] >= 4 and med['high_freq_pct'] > 40:
            scenes.append({'scene': '日间唤醒', 'score': min(10, int(med['vocal_fitness'] * 0.5 + med['high_freq_pct'] * 0.1))})
        
        # 深睡(无解说): 低人声+高δ波
        if med['voice_ratio_pct'] < 25 and med['delta_power'] >= 6:
            scenes.append({'scene': '深睡辅助', 'score': min(10, int(med['delta_power'] * 2))})
        
        # 默认场景
        if not scenes:
            scenes.append({'scene': '通用背景', 'score': 5})
        
        scenes.sort(key=lambda x: x['score'], reverse=True)
        return scenes
    
    def _generate_description(self, result):
        """生成通俗化描述"""
        m = result['meditation']
        
        parts = []
        # 描述人声
        if m['voice_ratio_pct'] > 40:
            parts.append('人声引导为主')
        elif m['voice_ratio_pct'] > 25:
            parts.append('人声+器乐混合')
        else:
            parts.append('纯器乐/环境音')
        
        # 描述语速节奏
        if m['vol_cv'] > 0.8:
            parts.append('节奏起伏明显')
        elif m['vol_cv'] > 0.4:
            parts.append('中等节奏')
        else:
            parts.append('节奏平稳')
        
        # 描述频段
        if m['delta_power_pct'] > 1:
            parts.append('含低频引导')
        if m['high_freq_pct'] > 50:
            parts.append('高频偏亮')
        elif m['high_freq_pct'] < 30:
            parts.append('高频柔和')
        
        # 睡眠建议
        sleep = result['overall_sleep_score']
        if sleep >= 8:
            advice = '非常适合睡前使用'
        elif sleep >= 6:
            advice = '适合睡前酝酿期'
        elif sleep >= 4:
            advice = '适合白天放松/通勤'
        else:
            advice = '适合白天精力唤醒'
        
        return advice + ' | ' + '，'.join(parts)


# ===== 测试: 评估创造意象.WAV =====
if __name__ == '__main__':
    evaluator = AudioEvaluator()
    result = evaluator.analyze_wav(r'E:\笔记本D盘备份\发烧友快乐音乐湖\输出给柔灵\创造意象.WAV')
    
    print('=== 创造意象.WAV 专业评估 ===')
    print()
    print(f'基础信息: {result["basic"]["duration_min"]}分钟, {result["basic"]["size_mb"]}MB, {result["basic"]["sample_rate"]}Hz')
    print()
    print(f'综合睡眠评分: {result["overall_sleep_score"]}/10')
    print()
    print('-- 声学质量 --')
    q = result['quality']
    print(f'  录音质量: {q["recording_quality"]}/10')
    print(f'  信噪比: {q["snr_db"]}dB')
    print(f'  削波: {q["clipping_pct"]}%')
    print()
    print('-- 冥想适配度 --')
    m = result['meditation']
    print(f'  人声适配: {m["vocal_fitness"]}/10 (人声占比{m["voice_ratio_pct"]}%)')
    print(f'  频谱适配: {m["spectral_fitness"]}/10 (脑波{m["brain_pct"]}%, 高频{m["high_freq_pct"]}%)')
    print(f'  节奏适配: {m["rhythm_fitness"]}/10 (音量变异{m["vol_cv"]})')
    print(f'  语速适配: {m["speech_rate"]}/10 ({m["trans_per_min"]}次/分钟)')
    print(f'  δ波强度: {m["delta_power"]}/10 ({m["delta_power_pct"]}%)')
    print(f'  纹理适配: {m["texture_fitness"]}/10')
    print()
    print('-- 场景匹配 --')
    for s in result['scenes']:
        print(f'  {s["scene"]}: {s["score"]}/10')
    print()
    print('-- 描述 --')
    print(f'  {result["description"]}')
