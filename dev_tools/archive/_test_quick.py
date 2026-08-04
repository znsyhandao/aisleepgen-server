# -*- coding: utf-8 -*-
"""快速测试引擎v2 - 前90秒，验证分类器"""
import pickle, numpy as np
import soundfile as sf
from scipy import signal

def extract_fast(data, sr, max_sec=90):
    """取前max_sec秒做特征提取"""
    if len(data.shape) > 1: data = data.mean(axis=1)
    samples = min(len(data), sr * max_sec)
    data = data[:samples]
    
    f, t, Zxx = signal.stft(data, fs=sr, nperseg=2048, noverlap=1536)
    mag = np.abs(Zxx); total = max(np.sum(mag), 1)
    
    mel_bins = [(0,100),(100,200),(200,300),(300,400),(400,600),
                (600,800),(800,1000),(1000,1300),(1300,1700),
                (1700,2200),(2200,3000),(3000,4000),(4000,8000)]
    mfcc = [float(np.log1p(np.sum(mag[(f>=lo)&(f<hi)]))) for lo,hi in mel_bins]
    
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

with open(r'D:\AISleepGen_Optimized\audio_classifier.pkl', 'rb') as f:
    d = pickle.load(f)
clf, scaler = d['model'], d['scaler']
print(f'Classifier: {scaler.n_features_in_} dims, {len(clf.support_)} SVs\n')

import os, clr
pkg2 = r'C:\Users\cqs10\AppData\Local\Temp\packages2'
for dll, sub in [('NAudio.Core','lib\\netstandard2.0'),('NAudio.Wasapi','lib\\netstandard2.0'),
                  ('NAudio.WinMM','lib\\netstandard2.0'),('NAudio','lib\\net472')]:
    clr.AddReference(os.path.join(pkg2, dll, sub, dll+'.dll'))
from NAudio.Wave import AudioFileReader, WaveFileWriter

BASE = r'D:\AISleepGen_Optimized'
tests = [
    ('创造意象(解说)', r'E:\笔记本D盘备份\发烧友快乐音乐湖\输出给柔灵\创造意象.WAV'),
    ('雷阵雨', os.path.join(BASE, r'aisleepgen-netlify\audio\fixed_rain.mp3')),
    ('海风', os.path.join(BASE, r'aisleepgen-netlify\audio\fixed_seawind.mp3')),
    ('小溪流水', os.path.join(BASE, r'assets\纯音乐冥想-Alpha冥想.mp3')),
    ('氛围音乐', os.path.join(BASE, r'aisleepgen-netlify\audio\mixkit-smooth-meditation-324.mp3')),
    ('呼吸引导(女声)', os.path.join(BASE, r'src\data\guided_meditation1.mp3')),
    ('白噪音', os.path.join(BASE, r'aisleepgen-netlify\audio\white-noise.mp3')),
    ('睡眠风铃', os.path.join(BASE, r'assets\睡眠纯音乐-风铃.mp3')),
]

for label, path in tests:
    if not os.path.exists(path): continue
    
    if path.endswith('.WAV'):
        data, sr = sf.read(path)
    else:
        wav = os.path.join(os.environ['TEMP'], '_tmp_q.wav')
        reader = AudioFileReader(path)
        WaveFileWriter.CreateWaveFile16(wav, reader)
        reader.Dispose()
        data, sr = sf.read(wav)
        os.remove(wav)
    
    feat = extract_fast(data, sr)
    pred = clf.predict(scaler.transform(feat.reshape(1,-1)))[0]
    prob = clf.predict_proba(scaler.transform(feat.reshape(1,-1)))[0]
    
    voice_lab = 'VOICE' if pred==1 else 'ambient'
    exp_lab = 'VOICE' if label.find('解说')>=0 or label.find('引导')>=0 else 'ambient'
    ok = 'OK' if voice_lab==exp_lab else 'XX'
    
    print(f'{ok} {label:<20s} {voice_lab} (p_v={prob[1]:.2f}) '
          f'ar={feat[20]:.2f} tpm={feat[21]:.0f} cv={feat[13]:.2f} '
          f'cent={feat[15]:.0f} flat={feat[16]:.4f}')
