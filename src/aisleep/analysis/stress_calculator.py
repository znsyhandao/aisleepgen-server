from typing import Dict

class StressCalculator:
    @staticmethod
    def calculate_stress_index(data: Dict) -> float:
        """基于多设备数据计算压力指数(0-1范围)"""
        # 获取基础生理数据
        heart_rate = data.get('wearables', {}).get('heart_rate', 72)
        hrv = data.get('wearables', {}).get('hrv', 0)
        eeg_attention = data.get('bci', {}).get('attention', 0.5)
        gsr = data.get('wearables', {}).get('galvanic_skin', 0)

        # 标准化各项指标
        hr_norm = min(max((heart_rate - 60) / 40, 0), 1)  # 假设60-100为正常范围
        hrv_norm = 1 - min(max(hrv / 200, 0), 1)  # HRV越高压力越小
        attention_norm = 1 - eeg_attention  # 注意力越低压力越大
        gsr_norm = min(max(gsr / 20, 0), 1)  # 皮电反应

        # 加权计算压力指数
        weights = {
            'hr': 0.3,
            'hrv': 0.25,
            'attention': 0.25,
            'gsr': 0.2
        }
        stress_index = (
            hr_norm * weights['hr'] +
            hrv_norm * weights['hrv'] +
            attention_norm * weights['attention'] +
            gsr_norm * weights['gsr']
        )

        return round(stress_index, 2)