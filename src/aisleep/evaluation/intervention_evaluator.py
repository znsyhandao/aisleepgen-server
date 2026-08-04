from typing import Dict, List
import numpy as np
from sklearn.metrics import mean_squared_error

class InterventionEvaluator:
    def __init__(self):
        self.baseline_metrics = {
            'sleep_quality': 0.7,
            'stress_level': 50
        }

    def evaluate(self, before: Dict, after: Dict) -> Dict:
        """评估干预效果"""
        return {
            'metrics': self._calc_improvements(before, after),
            'effectiveness': self._calc_effectiveness_score(before, after),
            'suggestions': self._generate_suggestions(before, after)
        }

    def _calc_improvements(self, before: Dict, after: Dict) -> Dict:
        """计算各项指标改善程度"""
        return {
            key: (before[key] - after[key]) / before[key] * 100 
            for key in ['sleep_quality', 'stress_level']
        }

    def _calc_effectiveness_score(self, before: Dict, after: Dict) -> float:
        """计算综合效果评分(0-1)"""
        improvements = self._calc_improvements(before, after)
        return 0.5 + sum(improvements.values()) / 200

    def _generate_suggestions(self, before: Dict, after: Dict) -> List[str]:
        """生成优化建议"""
        suggestions = []
        if after['stress_level'] > 40:
            suggestions.append("增加冥想干预时长")
        if after['sleep_quality'] < before['sleep_quality']:
            suggestions.append("调整声波频率")
        return suggestions
