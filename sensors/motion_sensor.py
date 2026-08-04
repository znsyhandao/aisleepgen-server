# motion_sensor.py
from sensors.sensor_base import SensorBase
import numpy as np
import time

class MotionSensor(SensorBase):
    """体动传感器模拟器"""
    
    def __init__(self, config: dict = None):
        super().__init__(config)
        self.position_history = []
        self.turnover_count = 0
        self.last_position = None
        
    def initialize(self) -> bool:
        """初始化体动传感器"""
        if not self.validate_config():
            return False
            
        try:
            time.sleep(0.2)
            self.is_initialized = True
            print("体动传感器初始化成功")
            return True
        except Exception as e:
            print(f"体动传感器初始化失败: {e}")
            return False
            
    def start(self) -> bool:
        """启动体动传感器"""
        if not self.is_initialized:
            if not self.initialize():
                return False
                
        try:
            time.sleep(0.1)
            self.is_running = True
            print("体动传感器启动成功")
            return True
        except Exception as e:
            print(f"体动传感器启动失败: {e}")
            return False
            
    def stop(self) -> bool:
        """停止体动传感器"""
        try:
            time.sleep(0.1)
            self.is_running = False
            print("体动传感器停止成功")
            return True
        except Exception as e:
            print(f"体动传感器停止失败: {e}")
            return False
            
    def read_data(self) -> dict:
        """读取体动数据"""
        if not self.is_running:
            return None
            
        try:
            timestamp = time.time()
            
            # 生成当前体位和加速度数据
            current_position = self._detect_position()
            acceleration = self._generate_acceleration_data()
            
            # 检测翻身
            if self._detect_turnover(current_position):
                self.turnover_count += 1
            
            data = {
                'timestamp': timestamp,
                'acceleration': acceleration,
                'features': {
                    'turnover_count': self.turnover_count,
                    'current_position': current_position,
                    'movement_intensity': np.random.uniform(0, 1),
                    'position_stability': np.random.uniform(0, 1)
                }
            }
            
            self.last_data = data
            self.last_timestamp = timestamp
            self.last_position = current_position
            
            # 保持历史记录长度
            self.position_history.append(current_position)
            if len(self.position_history) > 100:
                self.position_history = self.position_history[-100:]
                
            return data
        except Exception as e:
            print(f"读取体动数据失败: {e}")
            return None
            
    def _detect_position(self):
        """检测当前体位"""
        positions = ['supine', 'prone', 'left_lateral', 'right_lateral']
        
        # 模拟体位变化，但保持一定的稳定性
        if self.last_position and np.random.random() > 0.8:  # 20%概率改变体位
            return np.random.choice(positions)
        elif self.last_position:
            return self.last_position
        else:
            return np.random.choice(positions)
            
    def _generate_acceleration_data(self):
        """生成三轴加速度数据"""
        # 模拟三轴加速度计数据
        base_movement = 0.1  # 基础运动水平
        
        # 根据体位调整基础加速度
        if self.last_position == 'supine':
            base_accel = [0, 0, 9.8]  # 仰卧
        elif self.last_position == 'prone':
            base_accel = [0, 0, -9.8]  # 俯卧
        elif self.last_position == 'left_lateral':
            base_accel = [9.8, 0, 0]  # 左侧卧
        else:  # right_lateral
            base_accel = [-9.8, 0, 0]  # 右侧卧
            
        # 添加随机运动
        movement_noise = np.random.normal(0, 0.5, 3)
        
        return (np.array(base_accel) + movement_noise).tolist()
        
    def _detect_turnover(self, current_position):
        """检测翻身动作"""
        if not self.last_position:
            return False
            
        # 如果体位发生变化，认为是翻身
        if current_position != self.last_position:
            return True
            
        return False
        
    def _validate_config(self):
        """验证体动传感器配置"""
        required_configs = ['sample_rate']
        for config in required_configs:
            if config not in self.config:
                raise ValueError(f"缺少配置项: {config}")