import numpy as np
from typing import Dict

class EnvironmentAdjuster:
    def __init__(self, baseline: Dict):
        """初始化环境调节器"""
        self.ideal = baseline

    def calculate_adjustment(self, current: Dict) -> Dict:
        """计算需要补偿的环境参数"""
        return {
            'temperature': self._temp_compensation(current.get('temperature', 21.0)),  # 默认值 21.0
            'light': self._light_compensation(current.get('light_level', 50)),         # 默认值 50
            'sound': self._sound_compensation(current.get('noise_level', 30))         # 默认值 30
        }

    def _temp_compensation(self, current_temp: float) -> float:
        """温度补偿算法"""
        delta = self.ideal['temperature'] - current_temp
        return np.clip(delta, -3.0, 3.0)  # 限制补偿幅度

    def _light_compensation(self, current_lux: float) -> float:
        """光照补偿曲线"""
        ideal = self.ideal['light_level']
        ratio = current_lux / ideal
        if ratio > 2: return -0.5
        if ratio > 1: return -0.2
        if ratio < 0.5: return 0.5
        return 0

    def _sound_compensation(self, current_db: float) -> float:
        """噪音补偿算法"""
        if current_db > 50: return - (current_db - 50) * 0.02
        return 0