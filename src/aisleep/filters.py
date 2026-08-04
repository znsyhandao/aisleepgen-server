import numpy as np
from scipy.signal import butter, lfilter, iirnotch

class ButterworthFilter:
    def __init__(self, lowcut, highcut, order=5):
        self.lowcut = lowcut
        self.highcut = highcut
        self.order = order

    def apply(self, signal, fs=250):
        # 计算归一化的截止频率
        nyq = 0.5 * fs
        low = self.lowcut / nyq
        high = self.highcut / nyq

        # 设计巴特沃斯滤波器
        b, a = butter(self.order, [low, high], btype='band')
        
        # 应用滤波器
        filtered_signal = lfilter(b, a, signal)
        return filtered_signal

class NotchFilter:
    def __init__(self, freq, order=2):
        self.freq = freq
        self.order = order

    def apply(self, signal, fs=250):
        # 计算归一化的频率
        nyq = 0.5 * fs
        notch_freq = self.freq / nyq

        # 设计陷波滤波器
        b, a = iirnotch(notch_freq, 0.7)
        
        # 应用滤波器
        filtered_signal = lfilter(b, a, signal)
        return filtered_signal
class BioSignalProcessor:
    def __init__(self, sample_rate, filters):
        self.sample_rate = sample_rate
        self.filters = filters

    def process_signal(self, signal_type, signal):
        if signal_type in self.filters:
            return self.filters[signal_type].apply(signal)
        return signal
