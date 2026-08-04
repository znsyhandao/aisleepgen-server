import pandas as pd
import numpy as np
from datetime import datetime, time
from typing import Dict, List
from scipy import stats

class HabitAnalyzer:
    def __init__(self, db_path: str):
        self.data = self._load_data(db_path)
        
    def _load_data(self, path: str) -> pd.DataFrame:
        """加载并预处理用户历史数据"""
        df = pd.read_parquet(path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df

    def analyze_sleep_patterns(self, user_id: str) -> Dict:
        """分析用户30天内的睡眠习惯"""
        user_data = self.data[self.data['user_id'] == user_id].last('30D')
        
        return {
            'sleep_regularity': self._calc_regularity(user_data),
            'optimal_sleep_window': self._find_optimal_window(user_data),
            'stress_correlations': self._find_stress_factors(user_data)
        }

    def _calc_regularity(self, data: pd.DataFrame) -> float:
        """计算睡眠规律性得分(0-1)"""
        bedtimes = data['bedtime'].apply(
            lambda x: (datetime.min + x).time()
        )
        return 1 - (bedtimes.std().total_seconds() / 3600 / 3)  # 3小时为最大偏差

    def _find_optimal_window(self, data: pd.DataFrame) -> Dict:
        """计算最佳入睡时间窗口"""
        fall_asleep = data['sleep_latency'].mean()
        wake_times = data['wake_time'].apply(
            lambda x: (datetime.min + x).time()
        )
        peak_hour = stats.mode(wake_times.apply(lambda x: x.hour)).mode[0]
        return {
            'start': time(hour=(peak_hour - 8) % 24), 
            'end': time(hour=(peak_hour - 6) % 24),
            'confidence': 0.9
        }

    def _find_stress_factors(self, data: pd.DataFrame) -> List[Dict]:
        """识别压力相关因素"""
        factors = []
        for col in ['screen_time', 'caffeine_intake']:
            corr = data['stress_level'].corr(data[col])
            factors.append({'factor': col, 'correlation': corr})
        return sorted(factors, key=lambda x: -abs(x['correlation']))
