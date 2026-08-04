#!/usr/bin/env python3
"""Generate white noise audio files for AISleepGen - rain, ocean, forest"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
os.chdir('D:\\AISleepGen_Optimized')

output_dir = os.path.join('miniprogram', 'assets', 'sounds')
os.makedirs(output_dir, exist_ok=True)

# 用 numpy+scipy 合成白噪音
try:
    import numpy as np
    from scipy.io import wavfile
except ImportError:
    print("pip3 install numpy scipy")
    sys.exit(1)

SAMPLE_RATE = 44100
DURATION = 30  # 30秒循环

# 1. 雨声（粉红噪音 + 随机脉冲模拟雨滴）
def generate_rain():
    """粉红噪音 + 雨滴脉冲"""
    t = np.linspace(0, DURATION, int(SAMPLE_RATE * DURATION), False)
    
    # 粉红噪音基底
    white = np.random.normal(0, 1, len(t))
    # 简易粉红噪音：积分白噪音（布朗噪声）
    pink = np.cumsum(white)
    pink = pink / np.max(np.abs(pink)) * 0.3
    
    # 雨滴脉冲（随机位置的小振幅短脉冲）
    drops = np.zeros_like(t)
    num_drops = int(DURATION * 8)  # 每秒8滴
    for _ in range(num_drops):
        pos = np.random.randint(0, len(t))
        amp = np.random.uniform(0.1, 0.5)
        for j in range(pos, min(pos + 80, len(t))):
            drops[j] += amp * (1 - (j - pos) / 80) * np.random.uniform(0.5, 1.0)
    
    signal = pink + drops * 0.5
    # 归一化到16-bit范围
    signal = np.int16(signal / np.max(np.abs(signal)) * 16384)
    return signal

# 2. 海浪声（低频布朗噪声 + 周期性起伏）
def generate_ocean():
    """低频布朗噪声 + 周期性振幅调制模拟海浪"""
    t = np.linspace(0, DURATION, int(SAMPLE_RATE * DURATION), False)
    
    # 布朗噪声（低频为主）
    white = np.random.normal(0, 1, len(t))
    brown = np.cumsum(white)
    brown = brown / np.max(np.abs(brown)) * 0.4
    
    # 低通滤波（保留低频）
    kernel = np.ones(200) / 200
    brown_filtered = np.convolve(brown, kernel, mode='same')
    
    # 周期性振幅（模拟潮汐，周期~12秒）
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * t / 12)
    
    signal = brown_filtered * envelope * 0.8
    signal = np.int16(signal / np.max(np.abs(signal)) * 16384)
    return signal

# 3. 森林/溪流（高频白噪音 + 低频背景）
def generate_forest():
    """混合白噪音 + 柔和鸟鸣模拟"""
    t = np.linspace(0, DURATION, int(SAMPLE_RATE * DURATION), False)
    
    # 白噪音基底
    white = np.random.normal(0, 1, len(t))
    white = white / np.max(np.abs(white)) * 0.2
    
    # 低频流水声
    brown = np.cumsum(np.random.normal(0, 1, len(t)))
    brown = brown / np.max(np.abs(brown)) * 0.4
    
    # 风噪（缓慢调制）
    wind = np.sin(2 * np.pi * t / 20) * 0.15
    
    signal = white + brown + wind
    signal = np.int16(signal / np.max(np.abs(signal)) * 16384)
    return signal

# 4. 棕噪音（纯低频放松）
def generate_brown():
    """纯布朗噪声"""
    t = np.linspace(0, DURATION, int(SAMPLE_RATE * DURATION), False)
    white = np.random.normal(0, 1, len(t))
    brown = np.cumsum(white)
    brown = brown / np.max(np.abs(brown)) * 0.5
    signal = np.int16(brown / np.max(np.abs(brown)) * 16384)
    return signal

sounds = {
    'rain': ('雨声', generate_rain),
    'ocean': ('海浪', generate_ocean),
    'forest': ('森林', generate_forest),
    'brown': ('棕噪音', generate_brown),
}

for key, (name, gen_func) in sounds.items():
    filepath = os.path.join(output_dir, f'{key}.wav')
    if os.path.exists(filepath):
        os.remove(filepath)
    signal = gen_func()
    wavfile.write(filepath, SAMPLE_RATE, signal)
    size_kb = os.path.getsize(filepath) / 1024
    print(f'[OK] {filepath} ({name}, {size_kb:.0f}KB)')

print(f'\nDone! All files in: {output_dir}')
print('Now updating chat.js with play_audio action...')
