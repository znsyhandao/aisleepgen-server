# -*- coding: utf-8 -*-
"""
干扰动音频评估引擎 v3.0
至尊宝要求：不是会说的模型，是能直接给出干预动作的工具

架构：
soundfile/scipy读音频 → 22维特征提取 → SVM分类(voice/ambient) → 场景匹配评分(睡眠/减压双维度) → 输出干预动作
"""
import soundfile as sf
import numpy as np
from scipy import signal
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
import os, pickle, json, sys

sys.stdout.reconfigure(encoding='utf-8')

# ===================== 特征提取 =====================
def extract_features(data, sr):
    """从PCM数据提取22维特征向量"""
    if len(data.shape) > 1:
        data = data.mean(axis=1)
    
    # STFT频谱
    f, t, Zxx = signal.stft(data, fs=sr, nperseg=2048, noverlap=1536)
    mag = np.abs(Zxx)
    total = max(np.sum(mag), 1)
    
    # 1-13. Mel频段能量 (13个)
    mel_bins = [
        (0,100),(100,200),(200,300),(300,400),(400,600),
        (600,800),(800,1000),(1000,1300),(1300,1700),
        (1700,2200),(2200,3000),(3000,4000),(4000,8000)
    ]
    mfcc_like = [float(np.log1p(np.sum(mag[(f>=lo)&(f<hi)]))) for lo,hi in mel_bins]
    
    # 14. 能量CV
    frame_len = sr // 10
    n = min(len(data)//frame_len, 6000)
    energy = np.array([np.sum(data[i*frame_len:(i+1)*frame_len]**2) for i in range(n)])
    cv = float(np.std(energy)/max(np.mean(energy),1))
    
    # 15. 零交叉率
    zcr_frames = [np.sum(np.abs(np.diff(np.sign(data[i*frame_len:(i+1)*frame_len]))))/(2*frame_len+1) for i in range(min(n,6000))]
    zcr = float(np.mean(zcr_frames))
    
    # 16. 谱质心
    centroid = float(np.sum(f[:,None]*mag)/total)
    
    # 17. 谱平坦度
    mag_p = mag[mag>0]
    flatness = float(np.exp(np.mean(np.log(mag_p+1e-10)))/max(np.mean(mag_p),1e-10)) if len(mag_p)>0 else 0
    
    # 18-20. 频段占比
    def band_pct(lo, hi):
        mask = (f >= lo) & (f < hi)
        return float(np.sum(mag[mask])/total*100)
    low_pct = band_pct(20,250)
    mid_pct = band_pct(250,2000)
    high_pct = band_pct(2000,20000)
    
    # 21. 活跃率
    thr = np.mean(energy)*0.15
    active_ratio = float(np.sum(energy>thr))/len(energy)
    
    # 22. TPM
    f_len = sr//5
    nf = min(len(data[:sr*60])//f_len, 18000)
    ef = np.array([np.sum(data[i*f_len:(i+1)*f_len]**2) for i in range(nf)])
    ethr = np.mean(ef)*0.2
    tpm = int(np.sum((ef>ethr)[:-1]!=(ef>ethr)[1:])) if len(ef)>1 else 0
    
    return np.array(mfcc_like+[cv,zcr,centroid,flatness,low_pct,mid_pct,high_pct,active_ratio,tpm])

def extract_features_from_file(filepath):
    """从文件直接提取特征"""
    data, sr = sf.read(filepath)
    return extract_features(data, sr), sr, data

# ===================== 分类器 =====================
def train_classifier(voice_features, ambient_features):
    """训练SVM分类器"""
    X = np.vstack([np.array(voice_features), np.array(ambient_features)])
    y = np.array([1]*len(voice_features) + [0]*len(ambient_features))
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X)
    clf = SVC(kernel='rbf', probability=True)
    clf.fit(X_s, y)
    return clf, scaler

def classify_voice(features, clf, scaler):
    """返回 (is_voice:bool, voice_probability:float)"""
    prob = clf.predict_proba(scaler.transform(features.reshape(1,-1)))[0]
    return clf.predict(scaler.transform(features.reshape(1,-1)))[0] == 1, float(prob[1])

# ===================== 场景评分 =====================

# --- 至尊宝盲测校正标准（2026-05-17）---
CALIBRATION = {
    '海风海浪':      {'type':'natural_ambient','sleep':8,'relax':8},
    '雷阵雨':        {'type':'natural_ambient','sleep':7,'relax':7},
    '小溪流水':      {'type':'natural_ambient','sleep':8,'relax':8},
    '呼吸引导':      {'type':'narration',     'sleep':6,'relax':7},
    '氛围音乐':      {'type':'music',         'sleep':6,'relax':7},
    '白噪音':        {'type':'white_noise',   'sleep':8,'relax':5},
}

def score_audio(features, is_voice, voice_prob):
    """基于声学特征+分类器输出映射睡眠指数和减压指数
    使用决策树分类（不依赖SVM类型输出，而是结合声学指标）"""
    cv = features[13]      # 能量CV
    zcr = features[14]     # 零交叉率
    centroid = features[15] # 谱质心
    flatness = features[16] # 谱平坦度
    low_pct = features[17]  # 低频占比
    mid_pct = features[18]  # 中频占比
    high_pct = features[19] # 高频占比
    active_ratio = features[20] # 活跃率
    tpm = features[21]     # 过零切换率
    
    result = {}
    
    # ===== 决策树分类 =====
    # 1. 白噪音: 极稳+持续+平坦
    if active_ratio > 0.95 and cv < 0.3 and flatness > 0.02:
        result['type'] = 'white_noise'
        result['sleep'] = 8
        result['relax'] = 5
        result['cog_load'] = 0
        result['best_scene'] = '入睡辅助'
        result['scenes'] = [{'scene':'入睡辅助','score':8},{'scene':'专注','score':5}]
        result['contraindications'] = ['睡前使用(低频恒定,可能干扰深度睡眠)']
        result['time_of_day'] = '全天'
    
    # 2. 呼吸引导: 低活跃率+高CV+间歇说话
    elif active_ratio < 0.5 and cv > 2.0 and tpm > 15:
        result['type'] = 'breathing_guide'
        result['sleep'] = 6
        result['relax'] = 7
        result['cog_load'] = 3
        result['best_scene'] = '减压放松'
        result['scenes'] = [{'scene':'减压放松','score':7},{'scene':'睡前放松','score':6}]
        result['contraindications'] = []
        result['time_of_day'] = '睡前/午间'
    
    # 3. 解说叙事: is_voice+部分SVM置信 或 声学指标符合人声模式
    elif (is_voice and voice_prob > 0.5) or (not is_voice and active_ratio < 0.85 and tpm > 10 and cv > 0.5):
        speech_density = min((active_ratio + tpm/50) / 2, 1.0)
        music_quality = min(low_pct / 20, 1.0) if low_pct > 10 else 0.2
        sleep_score = int(10 * (1 - speech_density * 0.7) + music_quality * 2)
        relax_score = int(10 * (1 - speech_density * 0.5) + music_quality * 3)
        result['type'] = 'narration'
        result['sleep'] = max(1, min(10, sleep_score))
        result['relax'] = max(1, min(10, relax_score))
        result['cog_load'] = int(3 + speech_density * 7)
        result['best_scene'] = '专注白天' if speech_density > 0.6 else '放松引导'
        scenes = [{'scene':'白天引导','score':result['relax']}]
        if result['sleep'] >= 4: scenes.append({'scene':'轻度助眠','score':result['sleep']})
        result['scenes'] = scenes
        result['contraindications'] = ['高认知负荷(有解说)'] if result['cog_load'] > 6 else []
        result['time_of_day'] = '白天' if speech_density > 0.6 else '午后/傍晚'
    
    # 4. 自然声(海浪/流水): 持续高能+中低CV+适中平坦度
    elif active_ratio > 0.85 and cv < 0.8 and flatness > 0.02:
        result['type'] = 'natural_ambient'
        result['sleep'] = 8
        result['relax'] = 8
        result['cog_load'] = 0
        result['best_scene'] = '入睡辅助/减压放松'
        result['scenes'] = [{'scene':'入睡辅助','score':8},{'scene':'减压放松','score':8}]
        result['contraindications'] = []
        result['time_of_day'] = '全天'
    
    # 5. 纯音乐/氛围: 低频主导+低质心+低平坦度
    elif low_pct > 15 and centroid < 3000 and flatness < 0.05:
        result['type'] = 'music'
        result['sleep'] = 6
        result['relax'] = 7
        result['cog_load'] = 2
        result['best_scene'] = '减压放松'
        result['scenes'] = [{'scene':'减压放松','score':7},{'scene':'轻度助眠','score':6}]
        result['contraindications'] = ['注意力需求(音乐结构丰富的片段)']
        result['time_of_day'] = '全天'
    
    # 6. 环境音(fallback)
    else:
        result['type'] = 'ambient'
        result['sleep'] = 7
        result['relax'] = 6
        result['cog_load'] = 1
        result['best_scene'] = '背景环境'
        result['scenes'] = [{'scene':'背景环境','score':7},{'scene':'轻度减压','score':6}]
        result['contraindications'] = []
        result['time_of_day'] = '全天'
    
    result['voice_prob'] = round(voice_prob, 2)
    result['features'] = {
        'active_ratio': round(active_ratio, 2),
        'tpm': tpm,
        'cv': round(cv, 2),
        'centroid': round(centroid, 0),
        'flatness': round(flatness, 4),
        'low_pct': round(low_pct, 1),
        'mid_pct': round(mid_pct, 1),
        'zcr': round(zcr, 4)
    }
    
    return result

def generate_intervention(result):
    """生成可直接执行的干预动作"""
    sleep = result['sleep']
    relax = result['relax']
    audio_type = result['type']
    
    # 主要用途判定
    if sleep >= relax and sleep >= 6:
        primary = 'sleep'
    elif relax > sleep and relax >= 6:
        primary = 'relax'
    else:
        primary = 'ambient'
    
    scene = result.get('best_scene', '背景环境')
    time_of_day = result.get('time_of_day', '全天')
    
    action = {
        'recommend': primary,
        'scene': scene,
        'time': time_of_day,
        'sleep_index': sleep,
        'relax_index': relax,
        'cog_load': result.get('cog_load', 0),
        'type': audio_type,
        'duration_min': estimate_duration(audio_type, sleep),
        'contraindications': result.get('contraindications', []),
        'scenes': result.get('scenes', [])
    }
    
    # 自然语言可读建议
    if primary == 'sleep':
        if audio_type in ('natural_ambient', 'white_noise'):
            action['advice'] = '适合作为入睡背景音持续播放'
        elif audio_type == 'breathing_guide':
            action['advice'] = '适合睡前呼吸练习，结束后自动停止'
        else:
            action['advice'] = '适合轻度助眠场景'
    elif primary == 'relax':
        if audio_type == 'breathing_guide':
            action['advice'] = '适合减压呼吸训练，建议跟随引导'
        elif audio_type == 'music':
            action['advice'] = '适合作为阅读/工作背景减压'
        else:
            action['advice'] = '适合减压放松场景'
    else:
        action['advice'] = '适合作为背景环境音'
    
    return action

def estimate_duration(audio_type, sleep_score):
    """基于音频类型推荐持续时间(分钟)"""
    durations = {
        'white_noise': [30, 60, 120],
        'natural_ambient': [20, 45, 90],
        'music': [15, 30, 60],
        'narration': [10, 20, 30],
        'breathing_guide': [5, 10, 20],
        'ambient': [20, 60, 120],
        'mixed': [10, 20, 30],
    }
    return durations.get(audio_type, [15, 30, 60])

# ===================== 主函数 =====================

def analyze_and_act(filepath, clf=None, scaler=None):
    """输入音频文件 → 输出干预动作"""
    # 特征提取
    features, sr, data = extract_features_from_file(filepath)
    
    # 分类
    if clf is not None and scaler is not None:
        is_voice, voice_prob = classify_voice(features, clf, scaler)
    else:
        # fallback: 用active_ratio
        is_voice = features[20] < 0.7
        voice_prob = 1.0 - features[20] if is_voice else features[20]
    
    # 评分
    result = score_audio(features, is_voice, voice_prob)
    
    # 干预输出
    action = generate_intervention(result)
    
    return result, action

def load_or_train_classifier(voice_dir=None, retrain=False):
    """加载或训练分类器"""
    model_path = os.path.join(os.path.dirname(__file__), 'audio_classifier.pkl')
    
    if os.path.exists(model_path) and not retrain:
        with open(model_path, 'rb') as f:
            data = pickle.load(f)
            clf = data['model']
            scaler = data['scaler']
            # 检查维度是否匹配
            if hasattr(scaler, 'n_features_in_') and scaler.n_features_in_ == 22:
                return clf, scaler
            print(f'  Classifier has {scaler.n_features_in_} dims, need 22. Retraining...')
    
    # 训练(22维)
    print('Training classifier (22-dims)...')
    d1 = r'E:\笔记本D盘备份\发烧友快乐音乐湖\输出给柔灵'
    voice_feats = []
    for f in sorted(os.listdir(d1)):
        if not f.endswith('.WAV'): continue
        p = os.path.join(d1, f)
        if os.path.getsize(p) < 1024*1024: continue
        feat, _, _ = extract_features_from_file(p)
        voice_feats.append(feat)
        print(f'  voice: {f[:20]}')
    
    import random
    ambient_feats = []
    for _ in range(15):
        syn = np.random.randn(22)
        syn[20] = 0.85 + random.random()*0.15  # active_ratio > 0.85
        syn[21] = random.randint(0, 15)         # tpm < 15
        syn[16] = 0.05 + random.random()*0.1     # flatness
        ambient_feats.append(syn)
    
    clf, scaler = train_classifier(voice_feats, ambient_feats)
    with open(model_path, 'wb') as f:
        pickle.dump({'model': clf, 'scaler': scaler}, f)
    print(f'Saved: {model_path} (22-dim)')
    return clf, scaler

# ===================== 演示/测试 =====================
if __name__ == '__main__':
    import clr
    pkg2 = r'C:\Users\cqs10\AppData\Local\Temp\packages2'
    for dll, sub in [('NAudio.Core','lib\\netstandard2.0'),('NAudio.Wasapi','lib\\netstandard2.0'),
                      ('NAudio.WinMM','lib\\netstandard2.0'),('NAudio','lib\\net472')]:
        clr.AddReference(os.path.join(pkg2, dll, sub, dll+'.dll'))
    from NAudio.Wave import AudioFileReader, WaveFileWriter
    
    def decode_mp3(path):
        wav = os.path.join(os.environ['TEMP'], '_tmp_eng.wav')
        reader = AudioFileReader(path)
        WaveFileWriter.CreateWaveFile16(wav, reader)
        reader.Dispose()
        return wav
    
    # 训练或加载分类器
    clf, scaler = load_or_train_classifier()
    
    # 测试全部关键音频
    BASE = r'D:\AISleepGen_Optimized'
    test_files = [
        ('创造意象(叙事解说)', r'E:\笔记本D盘备份\发烧友快乐音乐湖\输出给柔灵\创造意象.WAV', None),
        ('雷阵雨(自然白噪)', os.path.join(BASE, r'aisleepgen-netlify\audio\fixed_rain.mp3'), None),
        ('海风海浪(自然)', os.path.join(BASE, r'aisleepgen-netlify\audio\fixed_seawind.mp3'), None),
        ('小溪流水(自然)', os.path.join(BASE, r'assets\纯音乐冥想-Alpha冥想.mp3'), None),
        ('氛围音乐', os.path.join(BASE, r'aisleepgen-netlify\audio\mixkit-smooth-meditation-324.mp3'), None),
        ('呼吸引导(女声)', os.path.join(BASE, r'src\data\guided_meditation1.mp3'), None),
        ('白噪音', os.path.join(BASE, r'aisleepgen-netlify\audio\white-noise.mp3'), None),
        ('睡眠风铃', os.path.join(BASE, r'assets\睡眠纯音乐-风铃.mp3'), None),
    ]
    
    print('='*70)
    print('AISleepGen 音频评估引擎 v3.0 — 完整管线测试')
    print('='*70)
    
    for label, path, _ in test_files:
        if not os.path.exists(path): continue
        
        # 解码mp3
        wav_path = decode_mp3(path) if path.endswith('.mp3') else path
        
        result, action = analyze_and_act(wav_path, clf, scaler)
        
        print(f'\n{"─"*60}')
        print(f'🎧 {label}')
        print(f'{"─"*60}')
        print(f'  类型: {result["type"]}  |  人声概率: {result["voice_prob"]:.0%}')
        print(f'  睡眠指数: {result["sleep"]}/10  |  减压指数: {result["relax"]}/10  |  认知负荷: {result["cog_load"]}/10')
        print(f'  最佳场景: {result["best_scene"]}')
        print(f'  建议时段: {result["time_of_day"]}')
        print(f'  干预建议: {action["advice"]}')
        print(f'  推荐时长: {action["duration_min"][0]}-{action["duration_min"][-1]}分钟')
        if result['contraindications']:
            print(f'  ⚠️ 禁忌: {", ".join(result["contraindications"])}')
        
        # 核心特征
        ftr = result['features']
        print(f'  特征: ar={ftr["active_ratio"]} tpm={ftr["tpm"]} cv={ftr["cv"]} '
              f'cent={ftr["centroid"]:.0f} flat={ftr["flatness"]:.4f}')
        
        if path.endswith('.mp3'):
            os.remove(wav_path)
    
    print('\n'+'='*70)
    print('引擎就绪，可对接世界模型决策内参')
    print('='*70)


# ===================== CONCEPT PROOF: SAE 幻觉检测 =====================
# 论文: Whisper Hallucination Detection via Sparse AutoEncoders
# 概念验证: 用 PCA 近似 SAE 的稀疏编码，在特征空间检测异常激活
# 2026-06-09 集成

class SparseAEHallucinationDetector:
    """
    简易 SAE 幻觉检测器（概念验证）
    原理论文：用稀疏自编码器从 Whisper 隐藏状态中提取可解释特征
    本实现：用 PCA 白化 + 稀疏阈值近似 SAE，检测特征空间的异常/幻觉模式
    
    原理：
    - 正常语音的特征向量在 PCA 空间的激活模式应当是稀疏的（少数维度激活）
    - 幻觉/噪声的特征向量激活模式是弥散的（多数维度都有激活）
    - 通过对比稀疏度差异来判定是否为幻觉
    """
    
    def __init__(self, n_components=8, sparsity_threshold=0.15):
        self.n_components = n_components
        self.sparsity_threshold = sparsity_threshold  # 低于此比例视为"稀疏"
        self.pca = None
        self.normal_activation_profile = None  # 正常语音的稀疏度基准
        self._fitted = False
    
    def fit(self, feature_vectors):
        """用一批正常音频特征拟合 PCA 变换"""
        X = np.array(feature_vectors)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        if X.shape[0] < self.n_components:
            # 数据太少时用简化版
            self._fitted = False
            return
        
        # PCA 白化（模拟 SAE 的稀疏编码过程）
        from sklearn.decomposition import PCA
        self.pca = PCA(n_components=min(self.n_components, X.shape[1], X.shape[0]))
        Z = self.pca.fit_transform(X)
        
        # 计算正常语音的稀疏度分布
        # 稀疏度 = (|z_i| < 阈值 的维度数) / 总维度
        z_std = np.std(Z, axis=0)
        self.normal_activation_profile = z_std
        self._fitted = True

    def detect(self, feature_vector, return_score=True):
        """
        检测特征向量是否为"幻觉"
        返回: (is_hallucination: bool, confidence: float)
        """
        x = np.array(feature_vector).reshape(1, -1)
        
        if self._fitted and self.pca is not None:
            # PCA 投影
            z = self.pca.transform(x)[0]
            
            # 计算激活稀疏度: 激活显著的维度占比
            n_active = np.sum(np.abs(z) > np.std(z) * 0.5)
            sparsity = 1.0 - (n_active / len(z))
            
            # 与正常分布对比: 计算马氏距离
            z_diff = z / (self.normal_activation_profile + 1e-8)
            anomaly_score = float(np.sqrt(np.sum(z_diff ** 2)))
            
            # 判定: 要么离群太远，要么激活太弥散
            is_hallucination = (anomaly_score > 4.2) or (sparsity < self.sparsity_threshold)
            hallucination_conf = min(1.0, anomaly_score / 5.0)
            
            return is_hallucination, hallucination_conf
        else:
            # 简化版: 基于特征本身的能量分布
            x_norm = np.abs(x[0]) / (np.linalg.norm(x[0]) + 1e-8)
            entropy = -np.sum(x_norm * np.log(x_norm + 1e-10)) / np.log(len(x_norm))
            # 熵越高 → 能量越分散 → 越可能是幻觉（正常音频能量集中在少数频段）
            is_hallucination = entropy > 0.7
            return is_hallucination, min(1.0, entropy)

    def correct_transcription(self, transcript, is_hallucination, confidence):
        """修正幻觉转录结果"""
        if is_hallucination and confidence > 0.5:
            return "[音频置信度过低，已跳过幻觉转录]"
        return transcript


# ===================== 概念验证：集成到分析管线 =====================

# 全局单例（在 analyze_and_act 中首次调用时 lazy init）
_HALLUCINATION_DETECTOR = None

def get_hallucination_detector():
    """获取/初始化全局幻觉检测器"""
    global _HALLUCINATION_DETECTOR
    if _HALLUCINATION_DETECTOR is None:
        _HALLUCINATION_DETECTOR = SparseAEHallucinationDetector()
    return _HALLUCINATION_DETECTOR


def analyze_with_hallucination_check(filepath, features=None):
    """
    在 analyze_and_act 之前调用，对音频特征做幻觉检测
    如果检测为幻觉，标记 transcript 为不可信
    
    用法:
        features = extract_features_from_file(filepath)
        is_hall, conf = analyze_with_hallucination_check(filepath, features)
    """
    detector = get_hallucination_detector()
    
    if features is None:
        try:
            data, sr = sf.read(filepath)
            features = extract_features(data, sr)
        except:
            return False, 0.0
    
    # 特征向量化
    if isinstance(features, np.ndarray):
        # sleep_audio_engine.extract_features 返回 numpy 数组
        if len(features) >= 8:
            feat_vec = features[:8]
        else:
            feat_vec = np.pad(features, (0, 8 - len(features)), 'constant')
    elif isinstance(features, dict):
        feat_vec = np.array([
            features.get('active_ratio', 0),
            features.get('tpm', 0),
            features.get('cv', 0),
            features.get('centroid', 0) / 1000,
            features.get('flatness', 0) * 10,
            features.get('rms_mean', 0) * 100,
            features.get('band_energy_ratio', 0),
            features.get('chroma_std', 0),
        ])
    else:
        feat_vec = np.zeros(8)
    
    is_hall, conf = detector.detect(feat_vec)
    
    if is_hall:
        print(f'  [SAE幻觉检测] ⚠️ 检测到可疑输入: conf={conf:.2f}')
    else:
        print(f'  [SAE幻觉检测] ✅ 正常: conf={1-conf:.2f}')
    
    return is_hall, conf


# 2. 集成到 analyze_and_act（可选）
# 在 WorldModel 调用 analyze_and_act 前先过幻觉检测
# 修改位置: world_model_coordinator.py or deepseek_proxy.py 中的音频处理逻辑
# 使用方式:
#   from sleep_audio_engine import analyze_with_hallucination_check
#   is_hall, conf = analyze_with_hallucination_check(filepath)
#   if is_hall:
#       # 跳过转录，标记为"可能的环境音/噪声"
#       transcript = "[SAE过滤: 非语音输入]"


if __name__ == '__main__':
    main()
