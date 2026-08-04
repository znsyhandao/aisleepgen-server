
import random
from .base import StressInterventionBase  # 确保正确导入
import numpy as np
from typing import List, Dict
from scipy.signal import welch
import json


class MusicTherapy:
    def __init__(self, device_manager):
        self.device_manager = device_manager

        # 初始化音乐库
        self.music_library = {
            'sleep': ['deep_sleep_track1', 'deep_sleep_track2'],
            'relax': ['relaxation_track1', 'relaxation_track2'],
            'focus': ['focus_track1', 'focus_track2'],
            'meditation': ['meditation_track1', 'meditation_track2'],
            'energy_boost': ['energy_boost_track1', 'energy_boost_track2']
        }

    def adjust_music_preferences(self, feedback: Dict):
        """
        根据用户反馈调整音乐选择逻辑。

        参数:
            feedback (Dict): 用户反馈数据，例如用户对不同音乐类型的偏好评分。
        """
        # 示例：根据反馈动态调整音乐库的优先级
        if 'preferred_music' in feedback:
            preferred_music = feedback['preferred_music']
            if preferred_music in self.music_library:
                # 动态调整优先级（示例逻辑，可根据需求扩展）
                self.music_library[preferred_music].append('user_favorite_track')

  
    
    def load_music_library(self, filepath: str):
        """
        从 JSON 文件加载音乐库。
    
        参数:
            filepath (str): JSON 文件路径。
        """
        try:
            with open(filepath, 'r') as file:
                self.music_library = json.load(file)
        except FileNotFoundError:
            print(f"Music library file not found: {filepath}")
            self.music_library = {}
    

    
    def _analyze_eeg(self, eeg_data: List[float]) -> Dict:
        """
        使用 Welch 方法分析 EEG 数据并提取特征。
    
        参数:
            eeg_data (List[float]): EEG 数据的时间序列。
    
        返回:
            Dict: 包含 α 波、θ 波和 β 波的频谱特征。
        """
        if not eeg_data:  # 如果 EEG 数据为空
            return {'alpha': 0, 'theta': 0, 'beta': 0}
    
        # 动态调整 nperseg，确保不超过数据长度
        nperseg = min(len(eeg_data), 256)
    
        # 使用 Welch 方法计算功率谱密度
        freqs, psd = welch(eeg_data, fs=256, nperseg=nperseg)
    
    # 提取 α 波、θ 波和 β 波的频谱特征
        def safe_mean(condition):
            return psd[condition].mean() if psd[condition].size > 0 else 0

        return {
            'alpha': safe_mean((freqs >= 8) & (freqs <= 12)),  # α波(8-12Hz)
            'theta': safe_mean((freqs >= 4) & (freqs <= 7)),   # θ波(4-7Hz)
            'beta': safe_mean((freqs >= 13) & (freqs <= 30)),  # β波(13-30Hz)
        }

    def get_effectiveness(self, user_profile: Dict) -> float:
        """根据用户配置文件计算音乐疗法的效果"""
        # 示例实现：根据用户敏感度调整效果
        sensitivity = user_profile.get('sensitivity', 0.5)
        return 0.8 * sensitivity  # 假设基础效果为 0.8，乘以敏感度

    async def apply(self, biometrics):
        """应用音乐疗法"""
        eeg = self._analyze_eeg(biometrics['eeg'])
        if eeg['alpha'] > eeg['theta']:
            music_type = 'calm'
        else:
            music_type = 'focus'

        return {
            'type': 'music',
            'music_type': music_type,
            'duration': 300,
            'intensity': 0.5
        }
    

    
    def _select_music(self, eeg_analysis: Dict, user_preferences: Dict = None) -> str:
        """
        根据 EEG 分析结果和用户偏好选择音乐。
        """
        # 默认音乐库
        self.music_library = {
            'sleep': ['deep_sleep_track1', 'deep_sleep_track2'],
            'relax': ['relaxation_track1', 'relaxation_track2'],
            'focus': ['focus_track1', 'focus_track2'],
            'meditation': ['meditation_track1', 'meditation_track2'],
            'energy_boost': ['energy_boost_track1', 'energy_boost_track2']
        }

        # 如果用户有音乐偏好，优先选择用户偏好
        if user_preferences and 'preferred_music' in user_preferences:
            preferred_music = user_preferences['preferred_music']
            if preferred_music in self.music_library:
                return random.choice(self.music_library[preferred_music])

        # 根据 EEG 分析结果选择音乐
        if eeg_analysis['theta'] > 0.7:
            return random.choice(self.music_library['sleep'])
        elif eeg_analysis['alpha'] > 0.6:
            return random.choice(self.music_library['relax'])
        elif eeg_analysis['beta'] > 0.5:
            return random.choice(self.music_library['focus'])
        elif eeg_analysis['alpha'] > 0.4 and eeg_analysis['theta'] > 0.4:
            return random.choice(self.music_library['meditation'])
        elif eeg_analysis['beta'] > 0.7:
            return random.choice(self.music_library['energy_boost'])

        # 默认返回专注音乐
        return random.choice(self.music_library['focus'])

    def adjust_music_preferences(self, feedback: Dict):
        """
        根据用户反馈调整音乐选择逻辑。

        参数:
            feedback (Dict): 用户反馈数据，例如用户对不同音乐类型的偏好评分。
        """
        # 示例：根据反馈动态调整音乐库的优先级
        if 'preferred_music' in feedback:
            preferred_music = feedback['preferred_music']
            if preferred_music in self.music_library:
                # 动态调整优先级（示例逻辑，可根据需求扩展）
                self.music_library[preferred_music].append('user_favorite_track')

    def update_music_during_playback(self, eeg_analysis: Dict):
        """
        根据实时 EEG 数据动态调整音乐类型。

        参数:
            eeg_analysis (Dict): 实时 EEG 分析结果。
        """
        # 示例：根据实时 EEG 数据切换音乐类型
        new_music_type = self._select_music(eeg_analysis)
        print(f"Switching to new music type: {new_music_type}")
        # 实际实现中，可以调用播放器接口切换音乐 