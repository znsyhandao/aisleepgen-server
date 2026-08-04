"""
增强版睡眠质量评估器
实现完整的PSQI(匹兹堡睡眠质量指数)和其他睡眠质量指标
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import warnings

class SleepQualityAssessor:
    """睡眠质量评估器，包含完整的PSQI计算和其他质量指标"""
    
    def __init__(self):
        # PSQI权重配置
        self.psqi_weights = {
            'subjective_quality': 1,      # 主观睡眠质量
            'sleep_latency': 2,           # 入睡潜伏期
            'sleep_duration': 3,          # 睡眠时长
            'sleep_efficiency': 4,        # 睡眠效率
            'sleep_disturbances': 5,      # 睡眠 disturbances
            'use_of_sleeping_pills': 6,   # 使用安眠药物
            'daytime_dysfunction': 7      # 日间功能障碍
        }
        
        # 睡眠阶段权重
        self.stage_weights = {
            'N3': 0.4,    # 深睡期 - 最重要
            'N2': 0.25,   # 浅睡期
            'REM': 0.25,  # REM睡眠
            'N1': 0.05,   # 入睡期
            'Wake': -0.1  # 清醒期 (负权重)
        }
        
        # 理想睡眠参数
        self.ideal_params = {
            'total_sleep_time': 7.5 * 3600,  # 7.5小时
            'sleep_efficiency': 0.85,        # 85%效率
            'sleep_latency': 15 * 60,        # 15分钟入睡
            'wake_after_sleep_onset': 30 * 60,  # 30分钟夜间醒来
            'rem_latency': 90 * 60,          # 90分钟进入REM
            'n3_percentage': 0.20,           # 20%深睡
            'rem_percentage': 0.25           # 25%REM睡眠
        }
    
    def calculate_psqi(self, sleep_data: Dict) -> Dict:
        """
        计算完整的匹兹堡睡眠质量指数(PSQI)
        
        Args:
            sleep_data: 包含睡眠数据的字典，需要以下字段:
                - bed_time: 上床时间 (datetime)
                - sleep_onset_time: 入睡时间 (datetime)
                - wake_up_time: 起床时间 (datetime)
                - final_awakening_time: 最终醒来时间 (datetime)
                - subjective_quality: 主观睡眠质量 (1-4)
                - sleep_latency_minutes: 入睡潜伏期(分钟)
                - disturbances_count: 夜间 disturbances 次数
                - use_sleeping_pills: 是否使用安眠药物 (bool)
                - daytime_dysfunction: 日间功能障碍程度 (1-4)
                
        Returns:
            包含PSQI总分和各分量得分的字典
        """
        # 验证必要字段
        required_fields = [
            'bed_time', 'sleep_onset_time', 'wake_up_time',
            'subjective_quality', 'sleep_latency_minutes'
        ]
        
        for field in required_fields:
            if field not in sleep_data:
                raise ValueError(f"缺少必要字段: {field}")
        
        # 计算各分量得分
        component_scores = {}
        
        # 1. 主观睡眠质量
        component_scores['subjective_quality'] = self._score_subjective_quality(
            sleep_data.get('subjective_quality', 3)
        )
        
        # 2. 入睡潜伏期
        component_scores['sleep_latency'] = self._score_sleep_latency(
            sleep_data.get('sleep_latency_minutes', 30)
        )
        
        # 3. 睡眠时长
        total_sleep_time = self._calculate_total_sleep_time(sleep_data)
        component_scores['sleep_duration'] = self._score_sleep_duration(total_sleep_time)
        
        # 4. 睡眠效率
        sleep_efficiency = self._calculate_sleep_efficiency(sleep_data, total_sleep_time)
        component_scores['sleep_efficiency'] = self._score_sleep_efficiency(sleep_efficiency)
        
        # 5. 睡眠 disturbances
        component_scores['sleep_disturbances'] = self._score_sleep_disturbances(
            sleep_data.get('disturbances_count', 0)
        )
        
        # 6. 使用安眠药物
        component_scores['use_of_sleeping_pills'] = self._score_sleeping_pills_use(
            sleep_data.get('use_sleeping_pills', False)
        )
        
        # 7. 日间功能障碍
        component_scores['daytime_dysfunction'] = self._score_daytime_dysfunction(
            sleep_data.get('daytime_dysfunction', 2)
        )
        
        # 计算总分
        total_score = sum(component_scores.values())
        
        # 评估睡眠质量
        quality_assessment = self._assess_psqi_score(total_score)
        
        return {
            'total_score': total_score,
            'component_scores': component_scores,
            'quality_assessment': quality_assessment,
            'total_sleep_time_hours': total_sleep_time / 3600,
            'sleep_efficiency_percent': sleep_efficiency * 100
        }
    
    def _score_subjective_quality(self, quality: int) -> int:
        """评分主观睡眠质量 (1-4 -> 0-3)"""
        if not 1 <= quality <= 4:
            warnings.warn(f"主观睡眠质量值 {quality} 超出范围 1-4，使用默认值 3")
            quality = 3
        
        # 映射: 1=很好(0分), 2=较好(1分), 3=较差(2分), 4=很差(3分)
        return quality - 1
    
    def _score_sleep_latency(self, latency_minutes: float) -> int:
        """评分入睡潜伏期"""
        if latency_minutes <= 15:
            return 0
        elif latency_minutes <= 30:
            return 1
        elif latency_minutes <= 60:
            return 2
        else:
            return 3
    
    def _calculate_total_sleep_time(self, sleep_data: Dict) -> float:
        """计算总睡眠时间(秒)"""
        try:
            sleep_onset = sleep_data['sleep_onset_time']
            final_awakening = sleep_data.get('final_awakening_time', sleep_data['wake_up_time'])
            
            if isinstance(sleep_onset, datetime) and isinstance(final_awakening, datetime):
                total_seconds = (final_awakening - sleep_onset).total_seconds()
                return max(0, total_seconds)
            else:
                # 如果提供的是时间字符串，尝试解析
                warnings.warn("时间数据格式可能不正确，使用默认值")
                return 7 * 3600  # 默认7小时
        except Exception as e:
            warnings.warn(f"计算总睡眠时间时出错: {e}")
            return 7 * 3600
    
    def _score_sleep_duration(self, total_sleep_seconds: float) -> int:
        """评分睡眠时长"""
        hours = total_sleep_seconds / 3600
        
        if hours > 7:
            return 0
        elif hours > 6:
            return 1
        elif hours > 5:
            return 2
        else:
            return 3
    
    def _calculate_sleep_efficiency(self, sleep_data: Dict, total_sleep_seconds: float) -> float:
        """计算睡眠效率"""
        try:
            bed_time = sleep_data['bed_time']
            wake_up_time = sleep_data['wake_up_time']
            
            if isinstance(bed_time, datetime) and isinstance(wake_up_time, datetime):
                total_bed_time = (wake_up_time - bed_time).total_seconds()
                if total_bed_time > 0:
                    return total_sleep_seconds / total_bed_time
                else:
                    return 0.85  # 默认值
            else:
                return 0.85
        except Exception as e:
            warnings.warn(f"计算睡眠效率时出错: {e}")
            return 0.85
    
    def _score_sleep_efficiency(self, efficiency: float) -> int:
        """评分睡眠效率"""
        if efficiency > 0.85:
            return 0
        elif efficiency > 0.75:
            return 1
        elif efficiency > 0.65:
            return 2
        else:
            return 3
    
    def _score_sleep_disturbances(self, disturbances_count: int) -> int:
        """评分睡眠 disturbances"""
        if disturbances_count == 0:
            return 0
        elif disturbances_count <= 2:
            return 1
        elif disturbances_count <= 4:
            return 2
        else:
            return 3
    
    def _score_sleeping_pills_use(self, use_pills: bool) -> int:
        """评分安眠药物使用"""
        return 3 if use_pills else 0
    
    def _score_daytime_dysfunction(self, dysfunction_level: int) -> int:
        """评分日间功能障碍"""
        if not 1 <= dysfunction_level <= 4:
            warnings.warn(f"日间功能障碍值 {dysfunction_level} 超出范围 1-4，使用默认值 2")
            dysfunction_level = 2
        
        # 映射: 1=无(0分), 2=轻微(1分), 3=明显(2分), 4=严重(3分)
        return dysfunction_level - 1
    
    def _assess_psqi_score(self, total_score: int) -> Dict:
        """评估PSQI总分"""
        if total_score <= 5:
            assessment = "睡眠质量很好"
            severity = "正常"
            recommendation = "继续保持良好的睡眠习惯"
        elif total_score <= 10:
            assessment = "睡眠质量一般"
            severity = "轻度睡眠问题"
            recommendation = "建议改善睡眠习惯，减少睡前刺激"
        elif total_score <= 15:
            assessment = "睡眠质量较差"
            severity = "中度睡眠问题"
            recommendation = "建议咨询医生，进行睡眠评估"
        else:
            assessment = "睡眠质量很差"
            severity = "严重睡眠问题"
            recommendation = "强烈建议就医，进行专业睡眠治疗"
        
        return {
            'assessment': assessment,
            'severity': severity,
            'recommendation': recommendation
        }
    
    def calculate_sleep_score(self, sleep_stages: List[Dict], sleep_params: Dict) -> Dict:
        """
        计算综合睡眠评分
        
        Args:
            sleep_stages: 睡眠阶段数据列表，每个元素包含:
                - stage: 阶段名称 ('Wake', 'N1', 'N2', 'N3', 'REM')
                - start_time: 开始时间(秒)
                - duration: 持续时间(秒)
            sleep_params: 睡眠参数，包含:
                - total_sleep_time: 总睡眠时间(秒)
                - sleep_latency: 入睡潜伏期(秒)
                - wake_after_sleep_onset: 睡眠中醒来时间(秒)
                - rem_latency: REM潜伏期(秒)
                
        Returns:
            综合睡眠评分结果
        """
        # 计算各阶段时间
        stage_durations = {'Wake': 0, 'N1': 0, 'N2': 0, 'N3': 0, 'REM': 0}
        
        for stage_data in sleep_stages:
            stage = stage_data.get('stage', 'Wake')
            duration = stage_data.get('duration', 0)
            if stage in stage_durations:
                stage_durations[stage] += duration
        
        total_sleep_time = sleep_params.get('total_sleep_time', sum(stage_durations.values()))
        if total_sleep_time == 0:
            return {'overall_score': 0, 'component_scores': {}, 'recommendations': []}
        
        # 计算各阶段比例
        stage_percentages = {
            stage: duration / total_sleep_time 
            for stage, duration in stage_durations.items()
        }
        
        # 计算各维度得分 (0-100分)
        component_scores = {}
        
        # 1. 睡眠效率得分
        sleep_efficiency = self._calculate_sleep_efficiency_score(sleep_params, total_sleep_time)
        component_scores['sleep_efficiency'] = sleep_efficiency
        
        # 2. 睡眠结构得分
        sleep_structure = self._calculate_sleep_structure_score(stage_percentages)
        component_scores['sleep_structure'] = sleep_structure
        
        # 3. 睡眠连续性得分
        sleep_continuity = self._calculate_sleep_continuity_score(sleep_params, sleep_stages)
        component_scores['sleep_continuity'] = sleep_continuity
        
        # 4. 睡眠潜伏期得分
        sleep_latency_score = self._calculate_sleep_latency_score(sleep_params.get('sleep_latency', 1800))
        component_scores['sleep_latency'] = sleep_latency_score
        
        # 5. REM睡眠得分
        rem_score = self._calculate_rem_score(stage_percentages.get('REM', 0), sleep_params.get('rem_latency', 5400))
        component_scores['rem_sleep'] = rem_score
        
        # 计算综合得分 (加权平均)
        weights = {
            'sleep_efficiency': 0.25,
            'sleep_structure': 0.25,
            'sleep_continuity': 0.20,
            'sleep_latency': 0.15,
            'rem_sleep': 0.15
        }
        
        overall_score = sum(
            component_scores[component] * weight 
            for component, weight in weights.items()
        )
        
        # 生成建议
        recommendations = self._generate_sleep_recommendations(component_scores, stage_percentages)
        
        return {
            'overall_score': round(overall_score, 1),
            'component_scores': {k: round(v, 1) for k, v in component_scores.items()},
            'stage_percentages': {k: round(v * 100, 1) for k, v in stage_percentages.items()},
            'recommendations': recommendations,
            'quality_level': self._get_quality_level(overall_score)
        }
    
    def _calculate_sleep_efficiency_score(self, sleep_params: Dict, total_sleep_time: float) -> float:
        """计算睡眠效率得分"""
        bed_time = sleep_params.get('time_in_bed', total_sleep_time / 0.85)  # 默认假设85%效率
        if bed_time <= 0:
            return 0
        
        efficiency = total_sleep_time / bed_time
        
        # 映射到0-100分
        if efficiency >= 0.90:
            return 100
        elif efficiency >= 0.85:
            return 80 + (efficiency - 0.85) * 400  # 85-90%: 80-100分
        elif efficiency >= 0.75:
            return 60 + (efficiency - 0.75) * 200  # 75-85%: 60-80分
        elif efficiency >= 0.65:
            return 40 + (efficiency - 0.65) * 200  # 65-75%: 40-60分
        elif efficiency >= 0.50:
            return 20 + (efficiency - 0.50) * 133  # 50-65%: 20-40分
        else:
            return max(0, efficiency * 40)  # 0-50%: 0-20分
    
    def _calculate_sleep_structure_score(self, stage_percentages: Dict) -> float:
        """计算睡眠结构得分"""
        score = 0
        
        # N3(深睡)比例得分
        n3_percent = stage_percentages.get('N3', 0)
        if n3_percent >= 0.20:
            score += 40  # 理想值
        elif n3_percent >= 0.15:
            score += 30 + (n3_percent - 0.15) * 200  # 15-20%: 30-40分
        elif n3_percent >= 0.10:
            score += 20 + (n3_percent - 0.10) * 200  # 10-15%: 20-30分
        elif n3_percent >= 0.05:
            score += 10 + (n3_percent - 0.05) * 200  # 5-10%: 10-20分
        else:
            score += n3_percent * 200  # 0-5%: 0-10分
        
        # REM比例得分
        rem_percent = stage_percentages.get('REM', 0)
        if rem_percent >= 0.25:
            score += 40  # 理想值
        elif rem_percent >= 0.20:
            score += 30 + (rem_percent - 0.20) * 200  # 20-25%: 30-40分
        elif rem_percent >= 0.15:
            score += 20 + (rem_percent - 0.15) * 200  # 15-20%: 20-30分
        elif rem_percent >= 0.10:
            score += 10 + (rem_percent - 0.10) * 200  # 10-15%: 10-20分
        else:
            score += rem_percent * 100  # 0-10%: 0-10分
        
        # N1比例扣分 (N1过多不好)
        n1_percent = stage_percentages.get('N1', 0)
        if n1_percent > 0.10:
            score -= min(20, (n1_percent - 0.10) * 200)  # 超过10%每1%扣2分，最多扣20分
        
        # Wake比例扣分
        wake_percent = stage_percentages.get('Wake', 0)
        if wake_percent > 0.05:
            score -= min(20, (wake_percent - 0.05) * 200)  # 超过5%每1%扣2分，最多扣20分
        
        return max(0, min(100, score))
    
    def _calculate_sleep_continuity_score(self, sleep_params: Dict, sleep_stages: List[Dict]) -> float:
        """计算睡眠连续性得分"""
        waso = sleep_params.get('wake_after_sleep_onset', 0)  # 睡眠中醒来时间(秒)
        total_sleep_time = sleep_params.get('total_sleep_time', 0)
        
        if total_sleep_time == 0:
            return 0
        
        # 计算醒来比例
        wake_ratio = waso / total_sleep_time if total_sleep_time > 0 else 0
        
        # 映射到0-100分
        if wake_ratio <= 0.02:  # ≤2%
            return 100
        elif wake_ratio <= 0.05:  # 2-5%
            return 80 + (0.05 - wake_ratio) * 666  # 80-100分
        elif wake_ratio <= 0.10:  # 5-10%
            return 60 + (0.10 - wake_ratio) * 400  # 60-80分
        elif wake_ratio <= 0.20:  # 10-20%
            return 40 + (0.20 - wake_ratio) * 200  # 40-60分
        elif wake_ratio <= 0.30:  # 20-30%
            return 20 + (0.30 - wake_ratio) * 200  # 20-40分
        else:
            return max(0, 20 - (wake_ratio - 0.30) * 66)  # >30%: 0-20分
    
    def _calculate_sleep_latency_score(self, sleep_latency: float) -> float:
        """计算睡眠潜伏期得分"""
        latency_minutes = sleep_latency / 60
        
        if latency_minutes <= 15:
            return 100
        elif latency_minutes <= 30:
            return 80 + (30 - latency_minutes) * 1.33  # 80-100分
        elif latency_minutes <= 45:
            return 60 + (45 - latency_minutes) * 1.33  # 60-80分
        elif latency_minutes <= 60:
            return 40 + (60 - latency_minutes) * 1.33  # 40-60分
        elif latency_minutes <= 90:
            return 20 + (90 - latency_minutes) * 0.67  # 20-40分
        else:
            return max(0, 20 - (latency_minutes - 90) * 0.22)  # >90分钟: 0-20分
    
    def _calculate_rem_score(self, rem_percentage: float, rem_latency: float) -> float:
        """计算REM睡眠得分"""
        # REM比例得分 (50分)
        rem_percent_score = 0
        if rem_percentage >= 0.25:
            rem_percent_score = 50
        elif rem_percentage >= 0.20:
            rem_percent_score = 40 + (rem_percentage - 0.20) * 100  # 20-25%: 40-50分
        elif rem_percentage >= 0.15:
            rem_percent_score = 30 + (rem_percentage - 0.15) * 100  # 15-20%: 30-40分
        elif rem_percentage >= 0.10:
            rem_percent_score = 20 + (rem_percentage - 0.10) * 100  # 10-15%: 20-30分
        elif rem_percentage >= 0.05:
            rem_percent_score = 10 + (rem_percentage - 0.05) * 100  # 5-10%: 10-20分
        else:
            rem_percent_score = rem_percentage * 200  # 0-5%: 0-10分
        
        # REM潜伏期得分 (50分)
        rem_latency_hours = rem_latency / 3600
        rem_latency_score = 0
        
        if rem_latency_hours <= 1.0:
            rem_latency_score = 50
        elif rem_latency_hours <= 1.5:
            rem_latency_score = 40 + (1.5 - rem_latency_hours) * 20  # 1-1.5小时: 40-50分
        elif rem_latency_hours <= 2.0:
            rem_latency_score = 30 + (2.0 - rem_latency_hours) * 20  # 1.5-2小时: 30-40分
        elif rem_latency_hours <= 2.5:
            rem_latency_score = 20 + (2.5 - rem_latency_hours) * 20  # 2-2.5小时: 20-30分
        elif rem_latency_hours <= 3.0:
            rem_latency_score = 10 + (3.0 - rem_latency_hours) * 20  # 2.5-3小时: 10-20分
        else:
            rem_latency_score = max(0, 10 - (rem_latency_hours - 3.0) * 3.33)  # >3小时: 0-10分
        
        return (rem_percent_score + rem_latency_score) / 2
    
    def _generate_sleep_recommendations(self, component_scores: Dict, stage_percentages: Dict) -> List[str]:
        """生成睡眠改善建议"""
        recommendations = []
        
        # 基于各维度得分生成建议
        if component_scores.get('sleep_efficiency', 100) < 70:
            recommendations.append("提高睡眠效率：减少卧床时间，只在困倦时上床")
        
        if component_scores.get('sleep_structure', 100) < 70:
            n3_percent = stage_percentages.get('N3', 0)
            rem_percent = stage_percentages.get('REM', 0)
            
            if n3_percent < 0.15:
                recommendations.append("增加深睡时间：保持规律作息，避免睡前饮酒和咖啡因")
            
            if rem_percent < 0.20:
                recommendations.append("改善REM睡眠：保证充足睡眠时间，减少压力")
        
        if component_scores.get('sleep_continuity', 100) < 70:
            recommendations.append("减少夜间醒来：保持卧室黑暗安静，避免睡前大量饮水")
        
        if component_scores.get('sleep_latency', 100) < 70:
            recommendations.append("缩短入睡时间：建立睡前放松 routine，避免睡前使用电子设备")
        
        if component_scores.get('rem_sleep', 100) < 70:
            recommendations.append("优化REM睡眠：保持情绪稳定，适当进行放松训练")
        
        # 通用建议
        if not recommendations:
            recommendations.append("睡眠质量良好，继续保持当前习惯")
        else:
            recommendations.insert(0, "根据您的睡眠数据，建议：")
        
        return recommendations
    
    def _get_quality_level(self, score: float) -> str:
        """根据得分获取质量等级"""
        if score >= 90:
            return "优秀"
        elif score >= 80:
            return "良好"
        elif score >= 70:
            return "一般"
        elif score >= 60:
            return "需要改善"
        else:
            return "较差"