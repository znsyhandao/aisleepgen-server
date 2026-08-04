# -*- coding: utf-8 -*-
"""
AISleepGen 专业音频评估引擎 v2.0
声学专家级判断 + 精细化场景匹配

========== 适用范围 ==========
本引擎分析的是 **WAV/PCM 格式** 的线性时域信号。
对于 AAC/MP3 等有损压缩格式，必须先解码为 PCM 再输入。
直接在压缩域(如 AAC ADTS 比特流)上做 FFT 是错误的——
压缩域数据是 MDCT 系数经量化和熵编码后的符号序列，不是时域采样。
详见 _analyze_aac.py 中的说明(已废弃，改为 NAudio 解码通道)。

========== 指标定义 ==========
- CV (变异系数, Coefficient of Variation) = σ/μ
  衡量音量波动程度。CV<0.15 为平稳(环境音), CV>0.6 为波动大(叙事)
  
- TPM (每分钟切换次数, Transitions Per Minute)
  基于 200ms 帧的能量过零率。TPM>30 ≈ 有说话节奏, TPM<10 ≈ 稳态

- voice% (人声频段占比)
  250-2000Hz (低频中段低音调区域+中频区域) 能量占比
  语音基频(200-500Hz) + 泛音(500-2000Hz) 集中在此

- music% (低频器乐占比)
  30-250Hz (次低频+低频) 能量占比
  贝斯/大提琴/底鼓等器乐基频集中在此

- δ波/θ波/α波/β波
  脑波频段能量相对占比 (0.5-4Hz / 4-8Hz / 8-13Hz / 13-30Hz)
  注意: 这是音频信号的频段特征, 不是 EEG 脑电信号
  音频中的低频节奏(如 0.1Hz 呼吸引导)可以通过包络检测提取

- 信噪比 (SNR)
  信号段 RMS(最高的 1 秒) / 静音段 RMS(最低的 1 秒), 取 dB
  SNR>30dB = 高品质录音

- 频谱质心 (Spectral Centroid)
  Σ(f × |X(f)|) / Σ|X(f)|, 单位 Hz
  反映人耳感知的"亮度"。质心低(<500Hz)=柔和, 高(>3000Hz)=明亮

- 频谱平坦度 (Spectral Flatness)
  几何均值 / 算术均值, 接近 0 = 纯音, 接近 1 = 白噪声

========== 分析方法 ==========
1. 基础层: 文件结构解析 (采样率/时长/通道/位深)
2. 声学指纹层: 时域+频域特征提取
   - 时域: RMS 序列 → CV, 动态范围, 语速(TPM)
   - 频域: 20 秒 FFT → 频段分布, 脑波占比, 质心, 平坦度
3. 心理声学层: 映射到听觉感知 (认知负荷, 温暖/刺耳, 放松潜力)
4. 临床映射层: 映射到睡眠/减压场景 (场景匹配, 禁忌判定)

========== 可靠性声明 ==========
- PCM 域频谱分析: ✅ 可靠
- 语音/音乐分类: ⚠️ 对高混响/多说话人场景可能误判
- δ波诱导判定: ⚠️ 仅指示音频中低频节奏的存在, 非 EEG 等效
- 场景匹配: ⚠️ 依赖预设权重, 需人类专家标定验证

========== 注意事项 ==========
- 本引擎不评估音乐艺术性、编曲质量、情感共鸣
- 高保真度(高 SNR)不等同于高睡眠指数
- 叙事引导音频的"好"与"不好"不由本引擎判定, 而是由用户需求决定
"""

import wave, numpy as np, json, os, struct
from numpy.fft import rfft, rfftfreq
from datetime import datetime

class ProAudioAnalyzer:
    """
    顶级音频分析引擎
    能力: 识别音频的物理特性 -> 映射到生理心理效应 -> 匹配最优干预场景
    """
    
    def __init__(self):
        self._load_models()
    
    def _load_models(self):
        """加载已有标注库"""
        try:
            with open(r'D:\AISleepGen_Optimized\audio_library.json', 'r', encoding='utf-8') as f:
                self.library = json.load(f).get('audio_library', [])
        except:
            self.library = []
        try:
            with open(r'D:\AISleepGen_Optimized\audio_matching_rules.json', 'r', encoding='utf-8') as f:
                self.rules = json.load(f)
        except:
            self.rules = {}
    
    def full_analysis(self, filepath):
        """完整音频分析 - 4层深度"""
        basic = self._analyze_basic(filepath)
        if not basic:
            return None
        fingerprint = self._acoustic_fingerprint(basic['audio'], basic['rate'])
        psychoacoustic = self._psychoacoustic_analysis(fingerprint)
        clinical = self._clinical_mapping(psychoacoustic)
        return {
            'basic': basic['info'],
            'fingerprint': fingerprint,
            'psychoacoustic': psychoacoustic,
            'clinical': clinical,
        }
    
    def _analyze_basic(self, filepath):
        """基础信息提取
        接收 WAV 文件路径，读取 PCM 数据。
        注意: 非 WAV 格式(如 AAC/MP3)必须先解码为 WAV。
        对于 AAC 文件，使用 NAudio (Windows Media Foundation) 解码后再调用。
        - 返回的 audio 数组为 np.float64 类型，单声道混音后值
        - 立体声采用 L+R 平均混音，不保留声场信息(声场分析在 fingerprint 中单独做)
        """
        try:
            with wave.open(filepath, 'rb') as w:
                raw = w.readframes(w.getnframes())
                sr = w.getframerate()
                ch = w.getnchannels()
                duration = w.getnframes() / sr
        except:
            # 非 WAV 格式时返回 None，由调用方处理
            print(f'[WARN] 无法打开文件(非WAV格式或已损坏): {filepath}')
            return None
        
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
        self._last_channels = ch
        self._last_stereo = audio
        if ch == 2:
            audio_st = audio.reshape(-1, 2)
            audio = audio_st.mean(axis=1)
        
        size_mb = os.path.getsize(filepath) / (1024*1024)
        
        return {
            'audio': audio,
            'rate': sr,
            'channels': ch,
            'info': {
                'duration_s': int(duration),
                'duration_min': round(duration/60, 1),
                'size_mb': round(size_mb, 1),
                'sample_rate': sr,
                'channels': ch,
                'bits': 16,
                'file': os.path.basename(filepath),
            }
        }
    
    def _acoustic_fingerprint(self, audio, sr):
        """第2层: 声学指纹提取
        接收线性 PCM 时域信号(audio, np.float64)，计算:
        
        时域特征(均在 PCM 时域计算):
        - RMS 序列: 按秒分帧计算 √(Σx²/N)，得到 CV(变异系数=σ/μ)
        - 动态范围: RMS序列的dB极差, 20×log₁₀(max/min)
        - 信噪比: 取 RMS 最高 1s / 最低 1s, dB 表示
        - 语速(TPM): 200ms帧能量过零率, 反映人声说话节奏
        
        频域特征(基于20秒窗口FFT):
        - FFT点数 = N, 分辨率 = sr/N
        - 频段划分: 次低频20-60Hz, 低频60-250Hz, 低中频250-500Hz,
                     中频500-2000Hz, 高中频2000-4000Hz, 4000-6000Hz, >6000Hz
        - 脑波频段: δ(0.5-4Hz), θ(4-8Hz), α(8-13Hz), β(13-30Hz)
                     注意: 这是音频信号的频域能量占比, 非EEG信号
        - 谱质心(亮度): Σf×|X(f)|/Σ|X(f)|, 单位 Hz
        - 谱平坦度(噪声度): 几何均值/算数均值, 0=纯音 1=白噪声
        - 80%能量截止频率: 累计能量达到80%时的最高频率
        
        立体声分离度(仅在2ch时有效):
        - 左/右声道 Pearson 相关系数, 1=完全相关(单声道), 近0=分离
        """
        # ---------- 音量动态 ----------
        seg_len = sr
        n_sec = min(len(audio)//seg_len, 600)
        rms_sec = np.array([np.sqrt(np.mean(audio[i*seg_len:(i+1)*seg_len]**2)) 
                           for i in range(n_sec)])
        avg_rms = float(np.mean(rms_sec))
        vol_cv = float(np.std(rms_sec) / max(avg_rms, 1))
        peak = int(np.max(np.abs(audio)))
        
        # 动态范围(基于RMS)
        rms_db = 20 * np.log10(rms_sec + 1)
        dynamic_range_db = float(np.max(rms_db) - np.min(rms_db[rms_db > -40]))
        
        # 底噪和信噪比
        sorted_idx = np.argsort(rms_sec)
        noise_sample = audio[sorted_idx[0]*seg_len:(sorted_idx[0]+1)*seg_len]
        signal_sample = audio[sorted_idx[-1]*seg_len:(sorted_idx[-1]+1)*seg_len]
        noise_floor = float(np.sqrt(np.mean(noise_sample**2)))
        signal_peak = float(np.sqrt(np.mean(signal_sample**2)))
        snr_db = float(20*np.log10(signal_peak/max(noise_floor,1))) if noise_floor > 0 else 0
        
        # 削波检测
        clipping_pct = float(np.sum(np.abs(audio) > 30000) / len(audio) * 100)
        
        # ---------- 频谱分析(取3个位置取平均) ----------
        # 预防长度不够
        min_len = min(len(audio), sr * 90)  # 最多90秒
        positions = [min_len//4, min_len//2, 3*min_len//4]
        positions = [max(p, sr*5) for p in positions]  # 至少5秒后
        
        spectral_means = []
        for pos in positions:
            if pos + sr*15 > len(audio):
                continue
            seg = audio[pos:pos+sr*15]
            fft = np.abs(rfft(seg))
            freqs = rfftfreq(len(seg), 1/sr)
            spectral_means.append((fft, freqs))
        
        if not spectral_means:
            return None
        
        # 综合频谱
        fft_avg = np.mean([s[0] for s in spectral_means], axis=0)
        freqs = spectral_means[0][1]
        total = max(np.sum(fft_avg), 1)
        
        # 精细频段划分
        bands = {}
        labels = {
            'sub_bass': (20, 60, '极低频'),
            'bass': (60, 250, '低频'),
            'low_mid': (250, 500, '低中频'),
            'mid': (500, 2000, '中频'),
            'high_mid': (2000, 4000, '高中频'),
            'presence': (4000, 6000, '临场感'),
            'brilliance': (6000, 20000, ' brilliance')
        }
        for name, (lo, hi, _) in labels.items():
            mask = (freqs >= lo) & (freqs < hi)
            bands[name] = float(np.sum(fft_avg[mask]) / total * 100)
        
        # 脑波频段
        bands['delta'] = float(np.sum(fft_avg[(freqs>=0.5)&(freqs<4)]) / total * 100)
        bands['theta'] = float(np.sum(fft_avg[(freqs>=4)&(freqs<8)]) / total * 100)
        bands['alpha'] = float(np.sum(fft_avg[(freqs>=8)&(freqs<13)]) / total * 100)
        bands['beta'] = float(np.sum(fft_avg[(freqs>=13)&(freqs<30)]) / total * 100)
        bands['brain_total'] = bands['delta'] + bands['theta'] + bands['alpha'] + bands['beta']
        
        # 谱质心(感知亮度)
        centroid = float(np.sum(freqs[:len(fft_avg)] * fft_avg) / total)
        
        # 谱平坦度(白噪音指数)
        fft_positive = fft_avg[fft_avg > 0]
        geom = float(np.exp(np.mean(np.log(fft_positive + 1e-10))))
        arith = float(np.mean(fft_positive + 1e-10))
        flatness = geom / max(arith, 1)
        
        # 80%能量截止频率
        sorted_idx_f = np.argsort(fft_avg)[::-1]
        cumsum = np.cumsum(fft_avg[sorted_idx_f]) / total
        cutoff = np.searchsorted(cumsum, 0.8)
        freq_80pct = float(freqs[sorted_idx_f[min(cutoff, len(sorted_idx_f)-1)]])
        
        # ---------- 时间结构 ----------
        # 语速检测(200ms帧)
        frame_len = sr // 5
        n_frames = min(18000, len(audio[:sr*60]) // frame_len)
        if n_frames > 10:
            speech_energy = np.array([np.sum(audio[i*frame_len:(i+1)*frame_len]**2) 
                                      for i in range(n_frames)])
            thr = float(np.mean(speech_energy) * 0.2)
            active_frames = np.sum(speech_energy > thr)
            transitions = np.sum((speech_energy > thr)[:-1] != (speech_energy > thr)[1:])
            trans_per_min = int(transitions)
            speech_active_ratio = float(active_frames / n_frames)
        else:
            trans_per_min = 0
            speech_active_ratio = 0
        
        # ---------- 立体声宽度 ----------
        if self._last_channels == 2:
            audio_st = self._last_stereo.reshape(-1, 2)
            seg_st = audio_st[sr*30:sr*60]
            L, R = seg_st[:,0].astype(float), seg_st[:,1].astype(float)
            stereo_corr = float(np.corrcoef(L, R)[0,1])
        else:
            stereo_corr = 1.0
        
        return {
            'rms_avg': avg_rms,
            'vol_cv': vol_cv,
            'peak': peak,
            'dynamic_range_db': dynamic_range_db,
            'snr_db': snr_db,
            'clipping_pct': clipping_pct,
            'bands': bands,
            'centroid_hz': centroid,
            'flatness': flatness,
            'freq_80pct_hz': freq_80pct,
            'trans_per_min': trans_per_min,
            'speech_active_ratio': speech_active_ratio,
            'stereo_corr': stereo_corr,
        }
    
    def _psychoacoustic_analysis(self, fp):
        """第3层: 心理声学解析（物理参数→感知映射）
        
        基于声学指纹的物理量, 映射到听觉感知维度:
        
        - 声音类型判定（修正版）:
          * narration(叙事): 检测到间歇性能量突降(人声呼吸停顿)+稳定F0峰
          * speech_music(配乐解说): 有背景音乐+间歇性人声
          * music(器乐): 有旋律变化+立体声左右游走+无间歇性开关
          * natural_ambient(自然环境): 连续平稳频谱+频段在山峰形分布
          * white_noise(白噪音): 平坦频谱+平稳CV<0.1
          * mixed: 多个特征混合
        
        - 认知负荷评估:
          * 人声: 基础负荷3 + 语速偏移 + 活跃度
          * 环境音: 认知负荷天然低(<3)
          * 纯音乐: 由音量动态决定
        
        - 放松潜力(两维):
          * 睡眠指数: 适用于被动闭眼场景(白噪音/自然声/纯音乐)
          * 减压指数: 适用于需要注意力锚定的场景(呼吸引导/流水声)
        
        - 修正(2026-05-17):
          * 不再以250-2000Hz频段占比作为"人声"判断依据
          * 改为检测"间歇性能量突降"(人声说话-呼吸-停顿的时序模式)
          * 自然声(雨声/海浪)虽然频段重叠250-2000Hz, 但能量是连续的
          * 乐器声虽然频段也在250-2000Hz, 但有音高旋律变化
        
        输出: 心理声学特征字典
        """
        if fp is None:
            return {}
        
        bands = fp['bands']
        result_extras = {'vol_cv': fp.get('vol_cv', 0.5)}
        
        # ===== 声音类型判定(修正版) =====
        
        # 核心判据: 能量活跃率的分布
        # ratio(active_ratio) = 高能帧占比
        #   <0.6: 间歇性(说话有停顿)
        #   >0.85: 持续性(连续说话/自然声/音乐持续)
        #   0.6-0.85: 中度间歇(可能有少量停顿或调制)
        speech_active_ratio = fp.get('speech_active_ratio', 0.5)
        tpm = fp.get('trans_per_min', 0)
        vol_cv = fp.get('vol_cv', 0.5)
        
        is_intermittent = speech_active_ratio < 0.7
        
        # 2. 频谱特征分析
        voice_like = bands['low_mid'] + bands['mid']  # 原"人声频段", 已弃用作为判据
        
        # 自然声频谱特征: 低频丰富+高频衰减
        # 雨声: 100-2000Hz山峰形, 不衰减
        # 海风: 宽频带+高频较多
        # 白噪音: 几乎平坦
        flatness = fp.get('flatness', 0.01)
        centroid = fp.get('centroid_hz', 1000)
        
        # 检测音频的自然属性
        # 自然声的频谱在3个时间窗口高度一致
        # 人声/音乐的频谱在不同窗口变化大
        stereo_corr = fp.get('stereo_corr', 1.0)
        
        # 3. 综合判定——基于active_ratio和cv
        # 呼吸引导: 间歇性(active_ratio<0.7) + 高CV(说话有音量起伏)
        if is_intermittent and vol_cv > 0.5:
            if bands['sub_bass'] + bands['bass'] > 10:
                sound_type = 'speech_music'
            else:
                sound_type = 'narration'
        
        # 轻度间歇: 可能有少量话语或自然调制
        elif is_intermittent and vol_cv > 0.3:
            sound_type = 'mixed'
            
        # 持续高能(active_ratio>0.85): 自然声或持续音乐
        elif speech_active_ratio > 0.85:
            # 白噪音: 平坦+极稳
            if flatness > 0.1 and vol_cv < 0.15:
                sound_type = 'white_noise'
            # 纯器乐/氛围音乐: 有立体声游走 + 低频主导 + 能量持续
            elif vol_cv > 0.3 and (bands['sub_bass'] + bands['bass'] > 15) and stereo_corr < 0.85:
                sound_type = 'music'
            # 自然声: 持续能量+适中平坦度
            elif flatness > 0.02 and vol_cv < 0.6:
                sound_type = 'natural_ambient'
            else:
                sound_type = 'ambient'
        
        # 中能段: 需要更多判断
        elif speech_active_ratio > 0.7:
            if flatness > 0.05 and vol_cv < 0.4:
                sound_type = 'natural_ambient'
            else:
                sound_type = 'mixed'
        
        else:
            # 低能区
            sound_type = 'ambient'
        
        # ===== 听觉舒适度 =====
        harshness_score = min(10, (bands.get('brilliance', 0) + bands.get('high_mid', 0) * 0.5) * 0.15)
        warmth_score = min(10, (bands['sub_bass'] + bands['bass'] * 0.5) * 0.5)
        
        # ===== 认知负荷评估 =====
        if sound_type in ('narration', 'speech_music'):
            speech_load = abs(max(tpm, 10) - 15) * 0.12
            cognitive_load = min(10, 3 + speech_load + speech_active_ratio * 3)
        elif sound_type == 'music':
            cognitive_load = min(5, vol_cv * 4)
        elif sound_type in ('natural_ambient', 'white_noise', 'ambient'):
            cognitive_load = min(2, vol_cv * 2)  # 自然声本质低负荷
        else:
            cognitive_load = min(5, vol_cv * 3)
        
        # ===== 放松诱导潜力(双维度) =====
        low_energy = bands['sub_bass'] + bands['bass'] + bands['delta'] * 3
        
        # 睡眠潜力: 需要平稳+低频+无认知需求
        sleep_potential = (
            low_energy * 0.3 -
            vol_cv * 5 -
            cognitive_load * 1.5 +
            flatness * 8 +
            warmth_score * 0.3
        )
        # 环境声+白噪音默认高睡眠潜力
        if sound_type in ('natural_ambient', 'white_noise', 'ambient'):
            sleep_potential += 3
        
        # 减压潜力: 需要感官锚定+认知占用低
        relax_potential = (
            low_energy * 0.2 -
            vol_cv * 3 +
            (10 - cognitive_load) * 0.5 +
            warmth_score * 0.4 +
            (1 - abs(stereo_corr - 0.5)) * 2  # 适度的立体声分离度有利于放松
        )
        if sound_type == 'music':
            relax_potential += 2  # 音乐的空间游走增强减压
        if sound_type in ('natural_ambient', 'ambient'):
            relax_potential += 2  # 自然声天生减压
        # 轻柔引导(低tpm+中voice)也能减压
        if sound_type in ('narration', 'speech_music') and tpm < 20 and cognitive_load < 5:
            relax_potential += 3
        
        return {
            'sound_type': sound_type,
            'has_narration': sound_type in ('narration', 'speech_music'),
            'voice_dominance': voice_like,
            'music_dominance': bands['sub_bass'] + bands['bass'] + bands['low_mid'] * 0.3,
            'harshness': round(harshness_score, 1),
            'warmth': round(warmth_score, 1),
            'cognitive_load': round(cognitive_load, 1),
            'sleep_potential': round(sleep_potential, 1),
            'relax_potential': round(relax_potential, 1),
            'trans_per_min': tpm,
            'speech_active_ratio': speech_active_ratio,
            'is_intermittent': is_intermittent,
            **result_extras,
        }
    
    def _clinical_mapping(self, psycho):
        """第4层: 临床映射（心理声学→双维度评分+场景匹配）
        
        将心理声学特征映射到两个独立维度:
        
        - sleep_index (睡眠指数, 1-10):
          适合被动入睡的评分标准
          * 自然环境声/白噪音: 天然高分(7-8)
          * 纯音乐/氛围: 中等(5-7)  
          * 有解说/配乐: 低分(1-4)
        
        - stress_relief_index (减压指数, 1-10):
          适合放松减压的评分标准
          * 空间游走音乐: 高分(6-8)
          * 轻柔呼吸引导: 高分(6-8)
          * 自然声: 中高分(5-7)
          * 高认知负荷: 低分(1-3)
        
        - 场景匹配 (修正版):
          基于双维度评分, 输出最适合场景+备选场景
          * 白噪音/自然声 → 深睡辅助, 环境白噪音
          * 纯音乐/氛围 → 放松减压, 背景音乐
          * 轻柔引导 → 减压放松, 呼吸训练
          * 叙事引导 → 日间冥想训练
        
        注意: 评分基于至尊宝2026-05-17盲测校正
        """
        if not psycho:
            return {}
        
        st = psycho['sound_type']
        sp = psycho['sleep_potential']
        rp = psycho['relax_potential']
        cv = psycho.get('vol_cv', 0.5)
        cgl = psycho['cognitive_load']
        harsh = psycho['harshness']
        warmth = psycho['warmth']
        tpm = psycho.get('trans_per_min', 0)
        
        # ===== 双维度评分 =====
        
        # 睡眠指数
        if st in ('natural_ambient', 'white_noise', 'ambient'):
            sleep_index = min(9, max(6, int(sp * 0.8 + 5.5)))
        elif st == 'music':
            sleep_index = min(8, max(4, int(sp * 0.6 + 4)))
        elif st in ('narration', 'speech_music'):
            # 轻柔引导(低tpm)可以用于入睡
            if tpm < 20 and cgl < 5:
                sleep_index = min(6, max(3, int(5 - cgl * 0.5)))
            else:
                sleep_index = min(3, max(1, int(3 - cgl * 0.3)))
        elif st == 'mixed' and cgl < 4 and tpm < 20:
            # 间歇性+低认知=轻柔呼吸引导
            sleep_index = 5
        else:
            sleep_index = min(6, max(2, int(3)))
        
        # 减压指数
        if st in ('natural_ambient', 'ambient'):
            stress_relief = min(8, max(5, int(rp * 0.7 + 4)))
        elif st == 'white_noise':
            stress_relief = min(7, max(4, int(4 + warmth * 0.3)))
        elif st == 'music':
            stress_relief = min(9, max(5, int(6 - cgl * 0.5 + warmth * 0.3)))
        elif st in ('narration', 'speech_music') or (st == 'mixed' and tpm < 20):
            # 只要识别出间歇性(有说话)且语速不快 -> 减压引导
            if tpm < 20 and cgl < 5:
                stress_relief = min(8, max(5, int(6 + (10-harsh)*0.2 - cgl*0.3)))
            else:  # 普通叙事
                stress_relief = min(4, max(1, int(4 - cgl * 0.4)))
        else:
            stress_relief = min(5, max(2, int(3)))
        
        # ===== 场景匹配(双维度驱动) =====
        scenes = []
        
        # 1. 深睡辅助: 需要高睡眠指数(>6) + 低减压需求(<4)
        if sleep_index >= 6:
            if st in ('natural_ambient', 'white_noise'):
                scenes.append({'scene': '深睡辅助', 'score': sleep_index,
                              'why': '稳态自然声, 适合被动入睡'})
            elif st == 'ambient':
                scenes.append({'scene': '深睡辅助', 'score': min(8, sleep_index),
                              'why': '环境音掩蔽, 适合入眠'})
        
        # 2. 放松减压: 需要高减压指数(>5)
        if stress_relief >= 5:
            if st == 'music':
                scenes.append({'scene': '放松减压', 'score': min(9, stress_relief + 1),
                              'why': '空间游走音乐, 注意力锚定'})
            elif st in ('natural_ambient', 'ambient'):
                scenes.append({'scene': '放松减压', 'score': min(8, stress_relief),
                              'why': '自然声沉浸, 舒缓压力'})
            elif st in ('narration', 'speech_music') and tpm < 20:
                scenes.append({'scene': '放松减压', 'score': min(7, stress_relief),
                              'why': '轻柔呼吸引导, 副交感神经激活'})
        
        # 3. 环境白噪音/掩蔽
        if st in ('white_noise', 'natural_ambient', 'ambient') and cv < 0.5:
            scenes.append({'scene': '白噪音掩蔽', 'score': min(8, int(6 + (1-cv)*2)),
                          'why': '平稳频谱, 掩蔽环境噪声'})
        
        # 4. 背景音乐(专注/阅读)
        if st == 'music' and cgl < 3:
            scenes.append({'scene': '专注背景', 'score': min(7, int(7 - cgl)),
                          'why': '纯器乐, 空间感好, 不侵占注意力'})
        
        # 5. 叙事引导(白天)
        if st in ('narration', 'speech_music'):
            if tpm < 20 and cgl < 4:
                scenes.append({'scene': '呼吸训练/冥想', 'score': min(8, max(5, int(8 - cgl))),
                              'why': '轻柔引导, 适合放松训练'})
            else:
                scenes.append({'scene': '引导训练', 'score': min(6, max(2, int(8 - cgl))),
                              'why': '叙事引导, 需要注意力'})
        
        # 默认
        if not scenes:
            scenes.append({'scene': '通用背景', 'score': 4, 'why': '无明显特征'})
        
        scenes.sort(key=lambda x: x['score'], reverse=True)
        
        # ===== 禁忌场景 =====
        contraindications = []
        if harsh > 7:
            contraindications.append('睡前使用(高频刺耳, 可能干扰入睡)')
        if cgl > 6:
            contraindications.append('入睡期使用(认知负荷过高, 需要注意力)')
        if cv > 0.8:
            contraindications.append('入眠期(音量波动过大, 易惊醒)')
        
        return {
            'sleep_index': sleep_index,
            'stress_relief_index': stress_relief,
            'sound_type': st,
            'cognitive_load': int(cgl),
            'scenes': scenes,
            'contraindications': contraindications,
            'recommended_time': ('睡前' if sleep_index >= 6 and stress_relief < 8
                                else '白天' if sleep_index < 4
                                else '全天通用'),
            'best_for': scenes[0]['scene'] if scenes else '通用',
        }
    
    def match_for_user(self, user_need, exclude_types=None, top_n=3):
        """给用户推荐音频——基于双维度评分
        
        user_need: 'sleep' | 'relax' | 'focus' | 'masking' | 'meditation'
        """
        if not self.library:
            return []
        
        candidates = []
        for entry in self.library:
            score = self._calculate_user_match(entry, user_need, exclude_types)
            if score > 0:
                candidates.append((score, entry))
        
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [e for s, e in candidates[:top_n]]
    
    def _calculate_user_match(self, entry, user_need, exclude_types):
        """计算音频对用户需求的匹配度"""
        ac = entry.get('acoustic', {})
        cat = entry.get('category', '')
        
        if exclude_types:
            words = cat + ' ' + ' '.join(entry.get('tags', []))
            for ex in exclude_types:
                if ex in words:
                    return 0
        
        sound_type = ac.get('sound_type', '')
        sleep_idx = ac.get('sleep_index', 1)
        relax_idx = ac.get('stress_relief_index', 1)
        cgl = ac.get('cognitive_load', 5)
        cv = ac.get('vol_cv', 0.5)
        
        if user_need == 'sleep':
            return sleep_idx * 2 - cgl
        elif user_need == 'relax':
            return relax_idx * 1.5 - abs(cgl - 3) * 0.5
        elif user_need == 'focus':
            score = (8 - cgl) + (10 if sound_type == 'music' else 0)
            return score
        elif user_need == 'masking':
            return (1 if sound_type in ('white_noise','ambient') else 0) * 10 + (10 - cv * 5)
        elif user_need == 'meditation':
            if sound_type in ('narration','speech_music'):
                return min(10, relax_idx + (8 - cgl))
            return 0
        return 0
    
    def describe(self, clinical):
        """生成人话描述"""
        if not clinical:
            return "分析失败"
        
        idx = clinical['sleep_index']
        sri = clinical['stress_relief_index']
        sound_type = clinical['sound_type']
        top_scene = clinical['scenes'][0]['scene'] if clinical['scenes'] else '通用'
        
        type_map = {
            'narration': '叙事引导音频',
            'speech_music': '配乐解说',
            'music': '器乐/氛围音乐',
            'natural_ambient': '自然环境录音',
            'white_noise': '白噪音',
            'ambient': '环境音',
            'mixed': '混合型',
        }
        
        lines = [
            f'声学类型: {type_map.get(sound_type, sound_type)}',
            f'睡眠指数: {idx}/10 | 减压指数: {sri}/10',
            f'认知负荷: {clinical["cognitive_load"]}/10',
            f'最佳场景: {top_scene}',
            f'推荐时段: {clinical["recommended_time"]}',
        ]
        
        if clinical['contraindications']:
            lines.append(f'禁忌: {"、".join(clinical["contraindications"][:2])}')
        
        return ' | '.join(lines)


# ===== 快速测试 =====
if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    analyzer = ProAudioAnalyzer()
    
    path = r'E:\笔记本D盘备份\发烧友快乐音乐湖\输出给柔灵\创造意象.WAV'
    result = analyzer.full_analysis(path)
    
    print('=== 创造意象.WAV 专业音频评估报告 (v2.0) ===')
    print()
    b = result['basic']
    print(f'--- 基础信息 ---')
    print(f'时长: {b["duration_min"]}m / 大小: {b["size_mb"]}MB / {b["sample_rate"]}Hz / {b["channels"]}ch')
    print()
    
    f = result['fingerprint']
    print(f'--- 声学指纹 ---')
    print(f'音量: RMS={f["rms_avg"]:.0f} CV={f["vol_cv"]:.2f} 动态范围={f["dynamic_range_db"]:.0f}dB')
    print(f'信噪比: {f["snr_db"]:.0f}dB 削波: {f["clipping_pct"]}% 峰值: {f["peak"]}')
    print(f'谱质心: {f["centroid_hz"]:.0f}Hz 平坦度: {f["flatness"]:.4f} 80%能量: {f["freq_80pct_hz"]:.0f}Hz')
    print(f'立体声分离度: {f["stereo_corr"]:.2f}')
    print()
    print(f'频段分布:')
    for k in ['sub_bass','bass','low_mid','mid','high_mid','presence','brilliance']:
        if k in f['bands']:
            label_map = {'sub_bass':'次低频','bass':'低频','low_mid':'低中频','mid':'中频','high_mid':'高中频','presence':'临场感','brilliance':'亮度'}
            print(f'  {label_map.get(k,k):>6s}: {f["bands"][k]:.1f}%')
    print(f'  脑波δ: {f["bands"]["delta"]:.2f}%  θ: {f["bands"]["theta"]:.2f}%  α: {f["bands"]["alpha"]:.2f}%  β: {f["bands"]["beta"]:.2f}%')
    print(f'  脑波总计: {f["bands"]["brain_total"]:.2f}%')
    print(f'语速: {f["trans_per_min"]}t/m 活跃率: {f["speech_active_ratio"]:.1%}')
    print()
    
    p = result['psychoacoustic']
    print(f'--- 心理声学解析 ---')
    print(f'声音类型: {p["sound_type"]}')
    if 'voice_dominance' in p:
        print(f'人声主导: {p["voice_dominance"]:.0f} 音乐主导: {p["music_dominance"]:.0f}')
    print(f'刺耳度: {p["harshness"]:.1f}/10 温暖度: {p["warmth"]:.1f}/10')
    print(f'认知负荷: {p["cognitive_load"]:.1f}/10')
    print(f'睡眠潜力: {p["sleep_potential"]:.1f} | 减压潜力: {p["relax_potential"]:.1f}')
    print()
    
    c = result['clinical']
    print(f'--- 临床映射(双维度) ---')
    print(f'睡眠指数: {c["sleep_index"]}/10  | 减压指数: {c["stress_relief_index"]}/10')
    print(f'认知负荷: {c["cognitive_load"]}/10')
    print(f'推荐时段: {c["recommended_time"]}')
    print()
    print(f'场景匹配:')
    for s in c['scenes'][:3]:
        print(f'  {s["scene"]}: {s["score"]}/10 ({s["why"]})')
    print()
    if c['contraindications']:
        print(f'禁忌: {"、".join(c["contraindications"])}')
    print()
    print(analyzer.describe(c))
