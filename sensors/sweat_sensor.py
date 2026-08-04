# sweat_sensor.py
from sensors.sensor_base import SensorBase
import numpy as np
import time
from datetime import datetime

class SweatSensor(SensorBase):
    """汗液传感器模拟器"""
    
    def __init__(self, config: dict = None):
        super().__init__(config)
        self.cortisol_history = []
        self.melatonin_history = []
        self.last_reading_time = None
        
    def initialize(self) -> bool:
        """初始化汗液传感器"""
        if not self.validate_config():
            return False
            
        try:
            time.sleep(0.5)
            self.is_initialized = True
            print("汗液传感器初始化成功")
            return True
        except Exception as e:
            print(f"汗液传感器初始化失败: {e}")
            return False
            
    def start(self) -> bool:
        """启动汗液传感器"""
        if not self.is_initialized:
            if not self.initialize():
                return False
                
        try:
            time.sleep(0.2)
            self.is_running = True
            print("汗液传感器启动成功")
            return True
        except Exception as e:
            print(f"汗液传感器启动失败: {e}")
            return False
            
    def stop(self) -> bool:
        """停止汗液传感器"""
        try:
            time.sleep(0.2)
            self.is_running = False
            print("汗液传感器停止成功")
            return True
        except Exception as e:
            print(f"汗液传感器停止失败: {e}")
            return False
            
    def read_data(self) -> dict:
        """读取汗液数据"""
        if not self.is_running:
            return None
            
        # 汗液传感器采样率较低，检查是否需要读取新数据
        current_time = time.time()
        if (self.last_reading_time and 
            current_time - self.last_reading_time < 10.0):  # 每10秒采样一次
            return self.last_data
            
        try:
            timestamp = time.time()
            
            # 根据时间模拟生理节律
            hour = datetime.now().hour
            cortisol_level = self._simulate_cortisol_rhythm(hour)
            melatonin_level = self._simulate_melatonin_rhythm(hour)
            
            data = {
                'timestamp': timestamp,
                'biomarkers': {
                    'cortisol': cortisol_level,
                    'melatonin': melatonin_level,
                    'stress_index': np.random.uniform(0, 1),
                    'relaxation_level': np.random.uniform(0, 1)
                },
                'features': {
                    'cortisol_trend': self._calculate_trend(self.cortisol_history),
                    'melatonin_trend': self._calculate_trend(self.melatonin_history),
                    'circadian_phase': self._detect_circadian_phase(hour)
                }
            }
            
            # 更新历史记录
            self.cortisol_history.append(cortisol_level)
            self.melatonin_history.append(melatonin_level)
            if len(self.cortisol_history) > 100:
                self.cortisol_history = self.cortisol_history[-100:]
                self.melatonin_history = self.melatonin_history[-100:]
            
            self.last_data = data
            self.last_timestamp = timestamp
            self.last_reading_time = current_time
            
            return data
        except Exception as e:
            print(f"读取汗液数据失败: {e}")
            return None
            
    def _simulate_cortisol_rhythm(self, hour):
        """模拟皮质醇昼夜节律"""
        # 皮质醇在早晨最高，晚上最低
        if 6 <= hour < 9:  # 早晨
            base_level = 0.8
        elif 9 <= hour < 18:  # 白天
            base_level = 0.5
        else:  # 晚上和夜间
            base_level = 0.2
            
        # 添加随机波动
        variation = np.random.normal(0, 0.1)
        return max(0, min(1, base_level + variation))
        
    def _simulate_melatonin_rhythm(self, hour):
        """模拟褪黑素昼夜节律"""
        # 褪黑素在夜间最高，白天最低
        if 20 <= hour or hour < 6:  # 夜间
            base_level = 0.8
        elif 6 <= hour < 12:  # 上午
            base_level = 0.2
        else:  # 下午和傍晚
            base_level = 0.5
            
        # 添加随机波动
        variation = np.random.normal(0, 0.1)
        return max(0, min(1, base_level + variation))
        
    def _calculate_trend(self, history):
        """计算趋势"""
        if len(history) < 2:
            return 'stable'
            
        # 简单趋势计算
        recent_avg = np.mean(history[-5:])
        older_avg = np.mean(history[-10:-5]) if len(history) >= 10 else history[0]
        
        if recent_avg > older_avg + 0.1:
            return 'increasing'
        elif recent_avg < older_avg - 0.1:
            return 'decreasing'
        else:
            return 'stable'
            
    def _detect_circadian_phase(self, hour):
        """检测昼夜节律阶段"""
        if 6 <= hour < 12:
            return 'morning'
        elif 12 <= hour < 18:
            return 'afternoon'
        elif 18 <= hour < 22:
            return 'evening'
        else:
            return 'night'
            
    def _validate_config(self):
        """验证汗液传感器配置"""
        required_configs = ['sample_rate']
        for config in required_configs:
            if config not in self.config:
                raise ValueError(f"缺少配置项: {config}")