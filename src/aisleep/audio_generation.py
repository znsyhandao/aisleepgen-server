import torch
import torchaudio
import numpy as np
from pathlib import Path
import soundfile as sf  # 新增导入

def generate_workout_music(duration=180, sample_rate=44100, bpm=128, output_path=None):
    """生成健身激励音乐"""
    # 确保输出目录存在
    output_dir = Path(__file__).parent.parent / 'data'
    output_dir.mkdir(exist_ok=True)
    
    # 设置输出路径
    if output_path is None:
        output_path = output_dir / 'workout_motivation.wav'
    else:
        output_path = Path(output_path)
    
import torch
import numpy as np
from pathlib import Path
import soundfile as sf

def generate_workout_music(duration=300, sample_rate=44100, bpm=128, output_path=None):
    """生成健身激励音乐"""
    # 确保输出目录存在
    output_dir = Path(__file__).parent.parent / 'data'
    output_dir.mkdir(exist_ok=True)
    
    # 设置输出路径
    if output_path is None:
        output_path = output_dir / 'workout_motivation.wav'
    else:
        output_path = Path(output_path)
        # 确保自定义路径的目录存在
        output_path.parent.mkdir(exist_ok=True, parents=True)
    
    
    
    # 1. 节奏部分 - 强劲的低音鼓

    
    t = torch.linspace(0, duration, int(duration * sample_rate))
    
    # 1. 增强鼓点部分 (更动态的节奏)
    beat_interval = 60.0 / bpm
    kick = torch.zeros_like(t)
    for i in range(int(duration / beat_interval)):
        start = int(i * beat_interval * sample_rate)
        end = start + int(0.15 * sample_rate)  # 延长低频持续时间
        # 更强的低频包络 (50Hz)
        env = torch.exp(-20 * t[:end-start]) * (1 + 0.3*torch.sin(2*np.pi*2*t[:end-start]))
        kick[start:end] = 2.0 * (0.7 * torch.sin(2 * np.pi * 50 * t[:end-start]) + 
                                0.3 * torch.sin(2 * np.pi * 25 * t[:end-start])) * env
    
    # ... rest of drum code ...


    # 2. 调整打击乐 (保持不变)
    hihat = torch.zeros_like(t)
    for i in range(int(duration / (beat_interval/2))):
        pos = int(i * beat_interval/2 * sample_rate)
        hihat[pos:pos+150] = 0.5 * torch.randn(150) * torch.exp(-t[:150]*0.1)

    # 3. 大幅增强旋律部分
    melody_env = torch.linspace(0.8, 1.5, len(t))  # 进一步提高旋律音量范围
    #main_melody = 1.2 * (  # 大幅提高主旋律音量
    #    torch.sin(2 * np.pi * 440 * t) + 
    #    0.8 * torch.sin(2 * np.pi * 660 * t) + 
    #    0.6 * torch.sin(2 * np.pi * 880 * t)
    #)
    
    # 添加更丰富的和声层次
   # melody_variation = 0.6 * (
   #     torch.sin(2 * np.pi * (220 + 8*t) * t) +
   #     0.7 * torch.sin(2 * np.pi * (330 + 5*t) * t) +
   #     0.4 * torch.sin(2 * np.pi * (550 + 3*t) * t)
    #)
    #melody = melody_env * (main_melody + melody_variation)
    # 3. 大幅增强旋律部分
    melody = generate_pro_melody(duration, sample_rate, bpm)
    
    #  完全移除背景噪音
    noise = torch.zeros(len(t))  # 使用零张量替代噪音

    
    # 4. 添加环境音效层 (可选)
    ambient = 0.05 * torch.randn(len(t)) * torch.exp(-0.001*t)  # 轻微的环境噪音
    
    # 3. 调整音轨混合比例
    audio = 1.5*kick + 0.1*hihat + 1.0*melody + noise  # 突出低频鼓点
    audio = 0.9 * audio / torch.max(torch.abs(audio))  # 更好的动态控制

# ... 后面的保存代码保持不变 ...

    
    # 保存为立体声WAV文件
    print(f"正在保存音频到: {output_path}")
    try:
        stereo_audio = np.stack([audio.numpy(), audio.numpy()])
        sf.write(str(output_path), stereo_audio.T, sample_rate, subtype='PCM_16')
        print("保存成功")
        return str(output_path)
    except Exception as e:
        print(f"保存失败: {e}")
        raise


def generate_pro_melody(duration, sample_rate, bpm):
    """基于音乐理论生成专业旋律"""
    t = torch.linspace(0, duration, int(duration * sample_rate))
    
    # 更丰富的和弦进行 (扩展为16小节循环)
    chord_progression = [
        [261.63, 329.63, 392.00, 440.00],  # Cmaj7
        [246.94, 329.63, 392.00, 466.16],   # G/B (add9)
        [220.00, 261.63, 329.63, 369.99],   # Am7
        [349.23, 440.00, 523.25, 587.33],   # Fmaj7
        [329.63, 392.00, 493.88, 554.37],   # C/E (add9)
        [349.23, 440.00, 523.25, 587.33],   # Fmaj7
        [392.00, 493.88, 587.33, 659.25],   # Gmaj7
        [261.63, 329.63, 392.00, 440.00],   # Cmaj7
        [261.63, 329.63, 392.00, 493.88],   # Cmaj9
        [246.94, 329.63, 392.00, 523.25],   # G/B (add11)
        [220.00, 261.63, 329.63, 415.30],   # Am9
        [349.23, 440.00, 523.25, 659.25],   # Fmaj7#11
        [329.63, 392.00, 493.88, 587.33],   # C/E (add9)
        [349.23, 440.00, 523.25, 698.46],   # Fmaj7 with higher extensions
        [392.00, 493.88, 587.33, 783.99],   # Gmaj9
        [261.63, 329.63, 392.00, 523.25]    # Cmaj9
    ]
    
    # 扩展旋律音高变化 (增加更多音程变化)
    melody_scales = {
        'major': [0, 2, 4, 5, 7, 9, 11, 12, 14, 16],  # 大调音阶
        'minor': [0, 2, 3, 5, 7, 8, 10, 12, 14, 15],   # 小调音阶
        'blues': [0, 3, 5, 6, 7, 10, 12, 15, 17]       # 布鲁斯音阶
    }
    
    melody = torch.zeros_like(t)
    beats_per_chord = 4  # 改为每4拍换一个和弦，让和声变化更自然
    beat_length = int(60/bpm * sample_rate)
    
    # 主旋律生成
    for i in range(int(duration * bpm / 60 / beats_per_chord)):
        chord = chord_progression[i % len(chord_progression)]
        scale_type = 'major' if i % 16 < 8 else ('minor' if i % 2 else 'blues')
        current_scale = melody_scales[scale_type]
        
        # 更智能的旋律音选择
        prev_note = current_scale[(i//4 - 1) % len(current_scale)]
        current_options = [
            n for n in current_scale 
            if abs(n - prev_note) <= 7  # 允许更大的音程跳跃
        ]
        note_variation = current_options[(i//2) % len(current_options)]
        start = i * beats_per_chord * beat_length
        
        # 主旋律音 (使用更丰富的波形)
        main_note = chord[note_variation % len(chord)]
        wave = (0.6 * torch.sin(2*np.pi*main_note*t[:beats_per_chord*beat_length]) +
                0.3 * torch.sin(2*np.pi*main_note*2*t[:beats_per_chord*beat_length]) +
                0.1 * torch.sin(2*np.pi*main_note*3*t[:beats_per_chord*beat_length]))
        
        # 更复杂的包络
        env = (torch.linspace(0.9, 0.3, beats_per_chord*beat_length) * 
               (0.8 + 0.2*torch.sin(2*np.pi*1.5*t[:beats_per_chord*beat_length])) *
               torch.exp(-0.5*t[:beats_per_chord*beat_length]/(beats_per_chord*beat_length/sample_rate)))
        
        melody[start:start+beats_per_chord*beat_length] += 0.5 * wave * env
        
        # 和弦背景音 (更丰富的和声)
        for j, f in enumerate(chord):
            volume = 0.25 if j == note_variation % len(chord) else 0.15
            harmonic = (0.6 * torch.sin(2*np.pi*f*t[:beats_per_chord*beat_length]) +
                        0.3 * torch.sin(2*np.pi*f*2*t[:beats_per_chord*beat_length]) +
                        0.1 * torch.sin(2*np.pi*f*3*t[:beats_per_chord*beat_length]))
            melody[start:start+beats_per_chord*beat_length] += volume * harmonic
    
    # ... rest of the function remains the same ...

    
    return melody

