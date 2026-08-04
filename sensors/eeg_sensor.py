# eeg_sensor.py
from sensor_base import SensorBase
import numpy as np
import time

class EEGSensor(SensorBase):
    """EEG 传感器模拟器"""
    
    def initialize(self) -> bool:
        """初始化 EEG 传感器"""
        if not self.validate_config():
            return False
            
        try:
            # 模拟初始化过程
            time.sleep(0.5)
            self.is_initialized = True
            print("EEG 传感器初始化成功")
            return True
        except Exception as e:
            print(f"EEG 传感器初始化失败: {e}")
            return False
            
    def start(self) -> bool:
        """启动 EEG 传感器"""
        if not self.is_initialized:
            if not self.initialize():
                return False
                
        try:
            # 模拟启动过程
            time.sleep(0.2)
            self.is_running = True
            print("EEG 传感器启动成功")
            return True
        except Exception as e:
            print(f"EEG 传感器启动失败: {e}")
            return False
            
    def stop(self) -> bool:
        """停止 EEG 传感器"""
        try:
            # 模拟停止过程
            time.sleep(0.2)
            self.is_running = False
            print("EEG 传感器停止成功")
            return True
        except Exception as e:
            print(f"EEG 传感器停止失败: {e}")
            return False
            
    def read_data(self) -> dict:
        """读取 EEG 数据"""
        if not self.is_running:
            return None
            
        try:
            # 生成模拟 EEG 数据
            timestamp = time.time()
            data = {
                'timestamp': timestamp,
                'channels': {
                    'C3': self._generate_eeg_signal(),
                    'C4': self._generate_eeg_signal(),
                    'O1': self._generate_eeg_signal(),
                    'O2': self._generate_eeg_signal()
                },
                'features': {
                    'slow_wave_depth': np.random.uniform(0, 1),
                    'delta_power': np.random.uniform(0, 1),
                    'alpha_power': np.random.uniform(0, 1),
                    'beta_power': np.random.uniform(0, 1)
                }
            }
            
            self.last_data = data
            self.last_timestamp = timestamp
            return data
        except Exception as e:
            print(f"读取 EEG 数据失败: {e}")
            return None
            
    def _generate_eeg_signal(self, length=250):
        """生成模拟 EEG 信号"""
        # 生成包含多种频段的信号
        t = np.arange(length) / 250.0  # 1秒数据，250Hz采样率
        delta = 0.5 * np.sin(2 * np.pi * 2 * t)  # δ 波 (0.5-4Hz)
        theta = 0.3 * np.sin(2 * np.pi * 6 * t)  # θ 波 (4-8Hz)
        alpha = 0.2 * np.sin(2 * np.pi * 10 * t)  # α 波 (8-12Hz)
        beta = 0.1 * np.sin(2 * np.pi * 20 * t)  # β 波 (12-30Hz)
        noise = 0.05 * np.random.randn(length)  # 噪声
        
        return (delta + theta + alpha + beta + noise).tolist()
        
    def _validate_config(self):
        """验证 EEG 传感器配置"""
        # 检查必要的配置项
        required_configs = ['sample_rate', 'channels']
        for config in required_configs:
            if config not in self.config:
                raise ValueError(f"缺少配置项: {config}")