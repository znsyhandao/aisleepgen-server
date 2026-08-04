# VoiceProsody 韵律特征模块

## 位置
`D:\AISleepGen_Optimized\voice_prosody.py`

## 依赖
- numpy (运算)
- scipy (信号处理, scipy.io.wavfile, scipy.signal)
- wave (标准库)

零音频专用库依赖（no librosa/pydub/soundfile）。

## API

### 一键调用
```python
from voice_prosody import extract_and_map
result = extract_and_map(wav_bytes)
# result.prosody = {speech_rate, pause_ratio, energy_mean, f0_mean, ...}
# result.bump = {arousal_bump, intensity_bump, valence_bump, confidence, cues}
```

### 分步调用
```python
from voice_prosody import extract_prosody, prosody_to_arousal_bump
prosody = extract_prosody(wav_bytes)  # 15个特征
bump = prosody_to_arousal_bump(prosody)  # 映射到情绪调节值
```

### 集成到 EmotionEngineV4
```python
from voice_prosody import extract_and_map
pm = extract_and_map(wav_bytes)
result = engine.detect(text, openid, prosody=pm)
# 自动叠加 arousal_bump / intensity_bump / valence_bump 到 VAD
```

## 提取的特征（15个）
- speech_rate: 语速指数(0~1), 基于能量变化率峰值密度
- pause_ratio: 停顿比例(0~1), 沉默帧占比
- energy_mean: 平均音量
- energy_std: 音量标准差
- energy_delta: 音量帧间变化率
- energy_peak_freq: 能量高峰频率(次/秒)
- f0_mean: 平均基频(Hz)
- f0_std: 基频标准差
- f0_range: 基频范围(Hz)
- spectral_mean: 谱质心(Hz)
- spectral_flux_mean: 谱通量均值
- voiced_ratio: 有声段占比
- duration_sec: 音频时长
- num_frames: 总帧数
- valid: 是否有足够语音信号

## 韵律→情绪映射规则（8条）
| 线索 | 条件 | arousal影响 | intensity影响 |
|------|------|-------------|--------------|
| 快速 | speech_rate>0.7 | +0.25 | +2 |
| 缓慢 | speech_rate<0.25 | -0.12 | -1 |
| 多停顿 | pause_ratio>0.6 | -0.15 | -1 |
| 少停顿 | pause_ratio<0.15 | +0.08 | +1 |
| 能量波动大 | energy_delta>0.08 | +0.15 | +1 |
| 能量平稳 | energy_delta<0.02 | -0.08 | 0 |
| 能量急促 | peak_freq>5 | +0.20 | +2 |
| 音调高 | f0_mean>250 | +0.18 | +1 |
| 音调低 | f0_mean<120 | -0.10 | 0 |
| 音调变化大 | f0_std>60 | +0.12 | 0 |
| 频谱活跃 | flux>0.005 | +0.10 | +1 |
| 声音明亮 | spectral_mean>3000 | +0.08 | 0 |
| 声音沉闷 | spectral_mean<800 | -0.05 | 0 |

## 测试
```python
python voice_prosody.py  # 自测（纯音合成信号验证）
```
生成5种测试信号：紧张快速、缓慢低沉、短音频无效、高唤醒、静默

## 已集成到 deepseek_proxy.py
- `_handle_voice_relax` 中检测 `voice_file` 参数
- 自动调用 `extract_and_map()` 
- 结果注入 `EmotionEngineV4.detect(prosody=...)`
