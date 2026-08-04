# -*- coding: utf-8 -*-
"""彻底重训分类器：真实背景样本 + 22维特征"""
import pickle, numpy as np
import soundfile as sf
from scipy import signal
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
import os, sys, clr, random

sys.stdout.reconfigure(encoding='utf-8')

# ===== NAudio for mp3 =====
pkg2 = r'C:\Users\cqs10\AppData\Local\Temp\packages2'
for dll, sub in [('NAudio.Core','lib\\netstandard2.0'),('NAudio.Wasapi','lib\\netstandard2.0'),
                  ('NAudio.WinMM','lib\\netstandard2.0'),('NAudio','lib\\net472')]:
    clr.AddReference(os.path.join(pkg2, dll, sub, dll+'.dll'))
from NAudio.Wave import AudioFileReader, WaveFileWriter

def decode_mp3(path):
    wav = os.path.join(os.environ['TEMP'], '_tmp_r.wav')
    reader = AudioFileReader(path)
    WaveFileWriter.CreateWaveFile16(wav, reader)
    reader.Dispose()
    return wav

def extract_22(data, sr, max_sec=120):
    """22维特征提取 (最长120秒)"""
    if len(data.shape) > 1: data = data.mean(axis=1)
    samples = min(len(data), sr * max_sec)
    data = data[:samples]
    
    f, t, Zxx = signal.stft(data, fs=sr, nperseg=2048, noverlap=1536)
    mag = np.abs(Zxx); total = max(np.sum(mag), 1)
    
    mfcc = [float(np.log1p(np.sum(mag[(f>=lo)&(f<hi)]))) for lo,hi in 
            [(0,100),(100,200),(200,300),(300,400),(400,600),(600,800),
             (800,1000),(1000,1300),(1300,1700),(1700,2200),(2200,3000),
             (3000,4000),(4000,8000)]]
    
    frame_len=sr//10; n=min(len(data)//frame_len,6000)
    energy=np.array([np.sum(data[i*frame_len:(i+1)*frame_len]**2) for i in range(n)])
    cv=float(np.std(energy)/max(np.mean(energy),1))
    zcr_list=[]
    for i in range(min(n,6000)):
        frame=data[i*frame_len:(i+1)*frame_len]
        zcr_list.append(np.sum(np.abs(np.diff(np.sign(frame))))/(2*len(frame)+1))
    zcr=float(np.mean(zcr_list))
    centroid=float(np.sum(f[:,None]*mag)/total)
    mag_p=mag[mag>0]
    flatness=float(np.exp(np.mean(np.log(mag_p+1e-10)))/max(np.mean(mag_p),1e-10)) if len(mag_p)>0 else 0
    def bp(lo,hi):return float(np.sum(mag[(f>=lo)&(f<hi)])/total*100)
    low=bp(20,250);mid=bp(250,2000);high=bp(2000,20000)
    thr=np.mean(energy)*0.15; active_ratio=float(np.sum(energy>thr))/len(energy)
    f_len=sr//5; nf=min(len(data[:sr*60])//f_len,18000)
    ef=np.array([np.sum(data[i*f_len:(i+1)*f_len]**2) for i in range(nf)])
    ethr=np.mean(ef)*0.2
    tpm=int(np.sum((ef>ethr)[:-1]!=(ef>ethr)[1:])) if len(ef)>1 else 0
    
    return np.array(mfcc+[cv,zcr,centroid,flatness,low,mid,high,active_ratio,tpm])

BASE = r'D:\AISleepGen_Optimized'

# === 人声样本: 柔灵10WAV (全部有解说) ===
voice_features = []
d1 = r'E:\笔记本D盘备份\发烧友快乐音乐湖\输出给柔灵'
for f in sorted(os.listdir(d1)):
    if not f.endswith('.WAV'): continue
    data, sr = sf.read(os.path.join(d1, f))
    feat = extract_22(data, sr)
    voice_features.append(feat)
    print(f'VOICE: {f[:20]} ar={feat[20]:.2f} tpm={feat[21]}')

# 额外人声样本：呼吸引导
guided_path = os.path.join(BASE, r'src\data\guided_meditation1.mp3')
if os.path.exists(guided_path):
    wav = decode_mp3(guided_path)
    data, sr = sf.read(wav)
    feat = extract_22(data, sr)
    voice_features.append(feat)
    print(f'VOICE: guided_meditation1  ar={feat[20]:.2f} tpm={feat[21]}')
    os.remove(wav)

# === 背景音样本: 已知的纯自然/白噪音/音乐 ===
bg_files = [
    # 纯自然录音 (海浪/雨声/流水)
    os.path.join(BASE, r'aisleepgen-netlify\audio\fixed_rain.mp3'),
    os.path.join(BASE, r'aisleepgen-netlify\audio\fixed_rainnight.mp3'),
    os.path.join(BASE, r'aisleepgen-netlify\audio\fixed_seawind.mp3'),
    os.path.join(BASE, r'aisleepgen-netlify\audio\fixed_springsong.mp3'),
    os.path.join(BASE, r'aisleepgen-netlify\audio\ocean-waves.mp3'),
    os.path.join(BASE, r'aisleepgen-netlify\audio\rain-sounds.mp3'),
    os.path.join(BASE, r'aisleepgen-netlify\audio\nature-ambience.mp3'),
    os.path.join(BASE, r'aisleepgen-netlify\audio\white-noise.mp3'),
    # 纯氛围音乐
    os.path.join(BASE, r'aisleepgen-netlify\audio\mixkit-smooth-meditation-324.mp3'),
    os.path.join(BASE, r'aisleepgen-netlify\audio\mixkit-relaxation-05-749.mp3'),
    os.path.join(BASE, r'aisleepgen-netlify\audio\mixkit-meditation-441.mp3'),
    os.path.join(BASE, r'aisleepgen-netlify\audio\mixkit-nature-meditation-345.mp3'),
    os.path.join(BASE, r'aisleepgen-netlify\audio\mixkit-yoga-song-444.mp3'),
    os.path.join(BASE, r'aisleepgen-netlify\audio\piano-music.mp3'),
    # 睡眠纯音乐
    os.path.join(BASE, r'assets\睡眠纯音乐-风铃.mp3'),
    os.path.join(BASE, r'assets\bg_music.mp3'),
    os.path.join(BASE, r'assets\meditation_music.mp3'),
]

ambient_features = []
for path in bg_files:
    if not os.path.exists(path): continue
    wav = decode_mp3(path)
    data, sr = sf.read(wav)
    feat = extract_22(data, sr)
    ambient_features.append(feat)
    name = os.path.basename(path)[:25]
    print(f'AMBIENT: {name} ar={feat[20]:.2f} tpm={feat[21]}')
    os.remove(wav)

print(f'\nVOICE: {len(voice_features)}, AMBIENT: {len(ambient_features)}, TOTAL: {len(voice_features)+len(ambient_features)}')

# === 训练 ===
X = np.vstack([np.array(voice_features), np.array(ambient_features)])
y = np.array([1]*len(voice_features) + [0]*len(ambient_features))

scaler = StandardScaler()
X_s = scaler.fit_transform(X)
clf = SVC(kernel='rbf', probability=True)
clf.fit(X_s, y)

# === 验证 ===
errors = 0
total = len(X)
print('\n=== 验证 ===')
for i, (feat, label) in enumerate(zip(X, y)):
    pred = clf.predict(scaler.transform(feat.reshape(1,-1)))[0]
    prob = clf.predict_proba(scaler.transform(feat.reshape(1,-1)))[0]
    if pred != label:
        errors += 1
        print(f'  XX #{i}: actual={"voice" if label==1 else "ambient"} pred={"voice" if pred==1 else "ambient"} (p_v={prob[1]:.2f})')

acc = (total - errors) / total * 100
print(f'\nAccuracy: {acc:.1f}% ({total-errors}/{total})')

# === 盲测 ===
print('\n=== 盲测 ===')
blind_tests = [
    ('小溪流水', os.path.join(BASE, r'assets\纯音乐冥想-Alpha冥想.mp3')),
    ('呼吸引导', os.path.join(BASE, r'src\data\guided_meditation1.mp3')),
    ('焦虑缓解', os.path.join(BASE, r'aisleepgen-netlify\audio\anxiety-relief.mp3')),
    ('深呼吸', os.path.join(BASE, r'aisleepgen-netlify\audio\deep-breathing.mp3')),
    ('风铃(长)', os.path.join(BASE, r'aisleepgen-netlify\audio\fixed_sleep_music_wind_chimes.mp3')),
    ('放松状态冥想', os.path.join(BASE, r'aisleepgen-netlify\audio\fixed_relax_state_meditation.mp3')),
]

for label, path in blind_tests:
    if not os.path.exists(path): continue
    wav = decode_mp3(path)
    data, sr = sf.read(wav)
    feat = extract_22(data, sr)
    pred = clf.predict(scaler.transform(feat.reshape(1,-1)))[0]
    prob = clf.predict_proba(scaler.transform(feat.reshape(1,-1)))[0]
    os.remove(wav)
    vl = 'VOICE' if pred==1 else 'ambient'
    print(f'  {label:<20s} -> {vl} (p_v={prob[1]:.2f}) ar={feat[20]:.2f} tpm={feat[21]} cv={feat[13]:.3f} cent={feat[15]:.0f}')

# === 保存 ===
with open(os.path.join(BASE, 'audio_classifier.pkl'), 'wb') as f:
    pickle.dump({'model':clf,'scaler':scaler}, f)
print(f'\nSaved: audio_classifier.pkl ({total} samples, {scaler.n_features_in_} dims)')
