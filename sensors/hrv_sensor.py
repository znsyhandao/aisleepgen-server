# hrv_sensor.py
from sensors.sensor_base import SensorBase
import numpy as np
import time

class HRVSensor(SensorBase):
    """HRV 传感器模拟器"""
    
    def initialize(self) -> bool:
        """初始化 HRV 传感器"""
        if not self.validate_config():
            return False
            
        try:
            time.sleep(0.3)
            self.is_initialized = True
            print("HRV 传感器初始化成功")
            return True
        except Exception as e:
            print(f"HRV 传感器初始化失败: {e}")
            return False
            
    def start(self) -> bool:
        """启动 HRV 传感器"""
        if not self.is_initialized:
            if not self.initialize():
                return False
                
        try:
            time.sleep(0.1)
            self.is_running = True
            print("HRV 传感器启动成功")
            return True
        except Exception as e:
            print(f"HRV 传感器启动失败: {e}")
            return False
            
    def stop(self) -> bool:
        """停止 HRV 传感器"""
        try:
            time.sleep(0.1)
            self.is_running = False
            print("HRV 传感器停止成功")
            return True
        except Exception as e:
            print(f"HRV 传感器停止失败: {e}")
            return False
            
    def read_data(self) -> dict:
        """读取 HRV 数据"""
        if not self.is_running:
            return None
            
        try:
            timestamp = time.time()
            data = {
                'timestamp': timestamp,
                'rr_intervals': self._generate_rr_intervals(),
                'features': {
                    'parasympathetic_activity': np.random.uniform(0, 1),
                    'sdnn': np.random.uniform(20, 100),  # 标准差
                    'rmssd': np.random.uniform(10, 80),  # 均方根差
                    'lf_hf_ratio': np.random.uniform(0.5, 3.0)  # 低频/高频比
                }
            }
            
            self.last_data = data
            self.last_timestamp = timestamp
            return data
        except Exception as e:
            print(f"读取 HRV 数据失败: {e}")
            return None
            
    def _generate_rr_intervals(self, count=100):
        """生成模拟 R-R 间期数据"""
        # 生成符合心率变异性的 R-R 间期序列
        base_interval = 800  # 基础 R-R 间期 (ms)
        variability = 50    # 变异性范围
        
        intervals = []
        for i in range(count):
            # 模拟呼吸性窦性心律不齐
            respiratory_modulation = 20 * np.sin(2 * np.pi * 0.25 * i / count)
            random_variation = np.random.normal(0, 10)
            
            interval = base_interval + respiratory_modulation + random_variation
            intervals.append(max(600, min(1200, interval)))  # 限制在合理范围内
            
        return intervals
        
    def _validate_config(self):
        """验证 HRV 传感器配置"""
        required_configs = ['sample_rate']
        for config in required_configs:
            if config not in self.config:
                raise ValueError(f"缺少配置项: {config}")