import numpy as np
import librosa
from scipy import signal
import logging

class TherapeuticAudioGenerator:
    def __init__(self, sample_rate=44100):
        """
        初始化治疗音频生成器
        :param sample_rate: 采样率，默认44100Hz
        """
        self.sample_rate = sample_rate
        self.audio = None
        self.logger = logging.getLogger(__name__)
        
    def generate_white_noise(self, duration=60, amplitude=0.1):
        """
        生成白噪声
        :param duration: 时长(秒)
        :param amplitude: 振幅(0-1)
        """
        samples = int(duration * self.sample_rate)
        self.audio = np.random.uniform(-amplitude, amplitude, samples)
        return self
        
    def generate_pink_noise(self, duration=60, amplitude=0.1):
        """
        生成粉红噪声
        :param duration: 时长(秒)
        :param amplitude: 振幅(0-1)
        """
        samples = int(duration * self.sample_rate)
        white = np.random.randn(samples)
        # 使用滤波器生成粉红噪声
        b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
        a = [1, -2.494956002, 2.017265875, -0.522189400]
        self.audio = amplitude * signal.lfilter(b, a, white)
        return self
        
    def add_binaural_beats(self, base_freq=200, delta_freq=10):
        """
        添加双耳节拍
        :param base_freq: 基础频率(Hz)
        :param delta_freq: 频率差(Hz)
        """
        if self.audio is None:
            self.logger.warning("未生成基础音频，先调用生成方法")
            return self
            
        t = np.arange(len(self.audio)) / float(self.sample_rate)
        left = 0.1 * np.sin(2 * np.pi * (base_freq - delta_freq/2) * t)
        right = 0.1 * np.sin(2 * np.pi * (base_freq + delta_freq/2) * t)
        
        # 如果是立体声则合并，单声道则转为立体声
        if len(self.audio.shape) == 1:
            self.audio = np.column_stack((self.audio + left, self.audio + right))
        else:
            self.audio[:, 0] += left
            self.audio[:, 1] += right
            
        return self
        
    def save_to_file(self, filename):
        """
        保存音频到文件
        :param filename: 输出文件名
        """
        if self.audio is None:
            raise ValueError("未生成音频数据")
            
        # 这里应该使用音频库保存文件，例如soundfile或scipy.io.wavfile
        # 示例代码需要安装相应库
        try:
            import soundfile as sf
            sf.write(filename, self.audio, self.sample_rate)
            self.logger.info(f"音频已保存到 {filename}")
        except ImportError:
            from scipy.io import wavfile
            wavfile.write(filename, self.sample_rate, self.audio)
            
        return self

    def normalize(self):
        """归一化音频到-1到1之间"""
        if self.audio is not None:
            max_val = np.max(np.abs(self.audio))
            if max_val > 0:
                self.audio = self.audio / max_val
        return self
