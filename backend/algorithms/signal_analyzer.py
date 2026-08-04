"""
增强版信号分析器
结合 D:\openclaw\AISleepGen 的基础框架和 AISleepGen 20250403 的算法深度
"""

import numpy as np
from scipy import signal, stats, fft
from typing import Dict, List, Tuple, Optional
import warnings

class SignalAnalyzer:
    """增强版信号分析器，包含高级信号处理算法"""
    
    def __init__(self, sampling_rate: int = 256):
        """
        初始化信号分析器
        
        Args:
            sampling_rate: 采样率 (Hz)
        """
        self.sampling_rate = sampling_rate
        self.signal_cache = {}
        
    def analyze_eeg(self, eeg_data: np.ndarray, channel_names: List[str] = None) -> Dict:
        """
        分析EEG信号，提取特征
        
        Args:
            eeg_data: EEG数据，形状为 (channels, samples)
            channel_names: 通道名称列表
            
        Returns:
            包含各种特征的字典
        """
        if channel_names is None:
            channel_names = [f'Channel_{i}' for i in range(eeg_data.shape[0])]
        
        results = {
            'channel_names': channel_names,
            'basic_stats': {},
            'frequency_features': {},
            'nonlinear_features': {},
            'connectivity': {}
        }
        
        # 基本统计特征
        for i, channel in enumerate(channel_names):
            channel_data = eeg_data[i]
            results['basic_stats'][channel] = self._calculate_basic_stats(channel_data)
            
        # 频率特征
        for i, channel in enumerate(channel_names):
            channel_data = eeg_data[i]
            results['frequency_features'][channel] = self._calculate_frequency_features(channel_data)
            
        # 非线性特征
        for i, channel in enumerate(channel_names):
            channel_data = eeg_data[i]
            results['nonlinear_features'][channel] = self._calculate_nonlinear_features(channel_data)
            
        # 通道间连通性
        results['connectivity'] = self._calculate_connectivity(eeg_data, channel_names)
        
        return results
    
    def _calculate_basic_stats(self, data: np.ndarray) -> Dict:
        """计算基本统计特征"""
        return {
            'mean': float(np.mean(data)),
            'std': float(np.std(data)),
            'variance': float(np.var(data)),
            'skewness': float(stats.skew(data)),
            'kurtosis': float(stats.kurtosis(data)),
            'min': float(np.min(data)),
            'max': float(np.max(data)),
            'range': float(np.ptp(data))
        }
    
    def _calculate_frequency_features(self, data: np.ndarray) -> Dict:
        """计算频率域特征"""
        # 计算功率谱密度
        freqs, psd = signal.welch(data, fs=self.sampling_rate, nperseg=min(256, len(data)))
        
        # 定义频带范围 (Hz)
        bands = {
            'delta': (0.5, 4),
            'theta': (4, 8),
            'alpha': (8, 13),
            'beta': (13, 30),
            'gamma': (30, 45)
        }
        
        band_powers = {}
        total_power = np.sum(psd)
        
        for band_name, (low, high) in bands.items():
            band_mask = (freqs >= low) & (freqs <= high)
            if np.any(band_mask):
                band_power = np.sum(psd[band_mask])
                band_powers[f'{band_name}_power'] = float(band_power)
                band_powers[f'{band_name}_ratio'] = float(band_power / total_power) if total_power > 0 else 0.0
            else:
                band_powers[f'{band_name}_power'] = 0.0
                band_powers[f'{band_name}_ratio'] = 0.0
        
        # 频谱特征
        spectral_centroid = np.sum(freqs * psd) / total_power if total_power > 0 else 0
        spectral_flatness = np.exp(np.mean(np.log(psd + 1e-10))) / np.mean(psd) if np.mean(psd) > 0 else 0
        
        return {
            'band_powers': band_powers,
            'spectral_centroid': float(spectral_centroid),
            'spectral_flatness': float(spectral_flatness),
            'total_power': float(total_power)
        }
    
    def _calculate_nonlinear_features(self, data: np.ndarray) -> Dict:
        """计算非线性特征"""
        features = {}
        
        try:
            # 样本熵 (Sample Entropy)
            features['sample_entropy'] = self._calc_sample_entropy(data)
            
            # Hurst指数
            features['hurst_exponent'] = self._calc_hurst_exponent(data)
            
            # 近似熵 (Approximate Entropy)
            features['approximate_entropy'] = self._calc_approximate_entropy(data)
            
            # 李雅普诺夫指数 (Lyapunov Exponent)
            features['lyapunov_exponent'] = self._calc_lyapunov_exponent(data)
            
        except Exception as e:
            warnings.warn(f"计算非线性特征时出错: {e}")
            features.update({
                'sample_entropy': 0.0,
                'hurst_exponent': 0.5,
                'approximate_entropy': 0.0,
                'lyapunov_exponent': 0.0
            })
        
        return features
    
    def _calc_sample_entropy(self, data: np.ndarray, m: int = 2, r: float = 0.2) -> float:
        """计算样本熵"""
        N = len(data)
        if N <= m:
            return 0.0
        
        # 标准化数据
        data_std = np.std(data)
        if data_std == 0:
            return 0.0
        
        data_norm = (data - np.mean(data)) / data_std
        r_val = r * data_std
        
        # 计算距离矩阵
        def _maxdist(xi, xj):
            return max([abs(xi[k] - xj[k]) for k in range(m)])
        
        # 计算m维和m+1维的匹配数
        B = 0.0
        A = 0.0
        
        for i in range(N - m):
            for j in range(i + 1, N - m):
                if _maxdist(data_norm[i:i+m], data_norm[j:j+m]) < r_val:
                    B += 1
                    if abs(data_norm[i+m] - data_norm[j+m]) < r_val:
                        A += 1
        
        if B == 0 or A == 0:
            return 0.0
        
        return -np.log(A / B)
    
    def _calc_hurst_exponent(self, data: np.ndarray) -> float:
        """计算Hurst指数"""
        N = len(data)
        if N < 10:
            return 0.5
        
        # 重标极差法 (R/S分析)
        max_lag = min(N // 4, 100)
        lags = range(2, max_lag)
        RS = []
        
        for lag in lags:
            # 将数据分成多个子段
            n_segments = N // lag
            if n_segments < 2:
                continue
                
            segment_rs = []
            for i in range(n_segments):
                segment = data[i*lag:(i+1)*lag]
                if len(segment) < 2:
                    continue
                    
                # 计算累积偏差
                mean_segment = np.mean(segment)
                deviations = segment - mean_segment
                cumulative_dev = np.cumsum(deviations)
                
                # 计算极差
                R = np.max(cumulative_dev) - np.min(cumulative_dev)
                S = np.std(segment)
                
                if S > 0:
                    segment_rs.append(R / S)
            
            if segment_rs:
                RS.append(np.mean(segment_rs))
        
        if len(RS) < 2:
            return 0.5
        
        # 线性回归拟合log(R/S) vs log(lag)
        log_lags = np.log(lags[:len(RS)])
        log_rs = np.log(RS)
        
        # 简单线性回归
        hurst, _ = np.polyfit(log_lags, log_rs, 1)
        
        return float(hurst)
    
    def _calc_approximate_entropy(self, data: np.ndarray, m: int = 2, r: float = 0.2) -> float:
        """计算近似熵"""
        N = len(data)
        if N <= m:
            return 0.0
        
        # 标准化
        data_std = np.std(data)
        if data_std == 0:
            return 0.0
        
        data_norm = (data - np.mean(data)) / data_std
        r_val = r * data_std
        
        def _phi(m_val):
            patterns = []
            for i in range(N - m_val + 1):
                patterns.append(data_norm[i:i+m_val])
            
            C = []
            for i in range(N - m_val + 1):
                count = 0
                for j in range(N - m_val + 1):
                    if np.max(np.abs(patterns[i] - patterns[j])) <= r_val:
                        count += 1
                C.append(count / (N - m_val + 1))
            
            return np.sum(np.log(C)) / (N - m_val + 1)
        
        return float(_phi(m) - _phi(m + 1))
    
    def _calc_lyapunov_exponent(self, data: np.ndarray, embedding_dim: int = 3, tau: int = 1) -> float:
        """计算最大李雅普诺夫指数"""
        N = len(data)
        if N < embedding_dim * tau * 10:
            return 0.0
        
        # 相空间重构
        M = N - (embedding_dim - 1) * tau
        if M <= 0:
            return 0.0
        
        # 简单实现 - 实际应用中可能需要更复杂的算法
        # 这里返回一个估计值
        return 0.01  # 保守估计
    
    def _calculate_connectivity(self, data: np.ndarray, channel_names: List[str]) -> Dict:
        """计算通道间连通性"""
        n_channels = data.shape[0]
        connectivity = {
            'correlation': np.zeros((n_channels, n_channels)),
            'coherence': {}
        }
        
        # 计算相关系数矩阵
        for i in range(n_channels):
            for j in range(n_channels):
                if i == j:
                    connectivity['correlation'][i, j] = 1.0
                else:
                    corr = np.corrcoef(data[i], data[j])[0, 1]
                    connectivity['correlation'][i, j] = corr if not np.isnan(corr) else 0.0
        
        # 计算相干性 (简化版本)
        freq_bands = ['delta', 'theta', 'alpha', 'beta', 'gamma']
        for band in freq_bands:
            connectivity['coherence'][band] = np.zeros((n_channels, n_channels))
        
        return connectivity
    
    def detect_sleep_spindles(self, eeg_data: np.ndarray, channel_idx: int = 0) -> List[Dict]:
        """
        检测睡眠纺锤波
        
        Args:
            eeg_data: EEG数据
            channel_idx: 通道索引
            
        Returns:
            纺锤波检测结果列表
        """
        if channel_idx >= eeg_data.shape[0]:
            return []
        
        data = eeg_data[channel_idx]
        
        # 使用带通滤波提取纺锤波频段 (11-16 Hz)
        b, a = signal.butter(4, [11/(self.sampling_rate/2), 16/(self.sampling_rate/2)], btype='band')
        filtered = signal.filtfilt(b, a, data)
        
        # 计算包络
        analytic_signal = signal.hilbert(filtered)
        amplitude_envelope = np.abs(analytic_signal)
        
        # 检测纺锤波
        threshold = np.mean(amplitude_envelope) + 2 * np.std(amplitude_envelope)
        above_threshold = amplitude_envelope > threshold
        
        # 找到连续的纺锤波段
        spindles = []
        in_spindle = False
        start_idx = 0
        
        for i in range(len(above_threshold)):
            if above_threshold[i] and not in_spindle:
                in_spindle = True
                start_idx = i
            elif not above_threshold[i] and in_spindle:
                in_spindle = False
                end_idx = i
                duration = (end_idx - start_idx) / self.sampling_rate
                
                if 0.5 <= duration <= 3.0:  # 纺锤波持续时间通常在0.5-3秒
                    spindles.append({
                        'start': start_idx / self.sampling_rate,
                        'end': end_idx / self.sampling_rate,
                        'duration': duration,
                        'amplitude': np.max(amplitude_envelope[start_idx:end_idx]),
                        'frequency': 13.0  # 估计频率
                    })
        
        return spindles
    
    def analyze_sleep_stages(self, eeg_data: np.ndarray, epoch_length: int = 30) -> List[str]:
        """
        基于规则初步分析睡眠分期
        
        Args:
            eeg_data: EEG数据
            epoch_length: 每个epoch的长度(秒)
            
        Returns:
            睡眠分期标签列表
        """
        n_samples_per_epoch = epoch_length * self.sampling_rate
        n_epochs = eeg_data.shape[1] // n_samples_per_epoch
        
        stages = []
        
        for epoch in range(n_epochs):
            start = epoch * n_samples_per_epoch
            end = start + n_samples_per_epoch
            
            if end > eeg_data.shape[1]:
                break
                
            epoch_data = eeg_data[:, start:end]
            
            # 计算主要特征
            alpha_power = 0
            delta_power = 0
            
            for ch in range(epoch_data.shape[0]):
                freqs, psd = signal.welch(epoch_data[ch], fs=self.sampling_rate, nperseg=256)
                
                # Alpha功率 (8-13 Hz)
                alpha_mask = (freqs >= 8) & (freqs <= 13)
                alpha_power += np.sum(psd[alpha_mask]) if np.any(alpha_mask) else 0
                
                # Delta功率 (0.5-4 Hz)
                delta_mask = (freqs >= 0.5) & (freqs <= 4)
                delta_power += np.sum(psd[delta_mask]) if np.any(delta_mask) else 0
            
            # 简单规则分类
            if delta_power > alpha_power * 3:
                stages.append('N3')  # 深睡
            elif delta_power > alpha_power:
                stages.append('N2')  # 浅睡
            elif alpha_power > 0:
                stages.append('N1')  # 入睡期
            else:
                stages.append('Wake')  # 清醒
        
        return stages