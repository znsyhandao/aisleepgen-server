"""
科学版压力分析插件 - 基于心率变异性(HRV)的压力评估
修复原算法的问题，提供更科学的压力分析
"""

import numpy as np
from plugin_manager import BasePlugin, PluginInfo, PluginType


class ScientificStressAnalyzerPlugin(BasePlugin):
    """科学版压力分析插件 - 基于HRV的压力评估"""
    
    def __init__(self):
        super().__init__()
        self.info = PluginInfo(
            name="科学压力分析",
            version="2.0.0",
            plugin_type=PluginType.DATA_ANALYSIS,
            description="基于心率变异性(HRV)的科学压力评估",
            author="眠小兔科学团队"
        )
    
    def calculate_hrv_metrics(self, heart_rate):
        """
        计算心率变异性(HRV)指标
        
        参数:
            heart_rate: 心率列表 (bpm)
            
        返回:
            dict: HRV指标字典
        """
        if len(heart_rate) < 10:
            return None
        
        # 将心率转换为RR间期 (毫秒)
        rr_intervals = [60000.0 / hr for hr in heart_rate]
        
        metrics = {}
        
        # 1. 基本统计
        metrics['avg_heart_rate'] = float(np.mean(heart_rate))
        metrics['min_heart_rate'] = float(min(heart_rate))
        metrics['max_heart_rate'] = float(max(heart_rate))
        metrics['hr_std'] = float(np.std(heart_rate))
        
        # 2. 时域指标
        # SDNN: 全部RR间期的标准差
        metrics['sdnn'] = float(np.std(rr_intervals))
        
        # RMSSD: 相邻RR间期差值的均方根 (副交感神经活动指标)
        if len(rr_intervals) > 1:
            differences = np.diff(rr_intervals)
            metrics['rmssd'] = float(np.sqrt(np.mean(differences ** 2)))
        else:
            metrics['rmssd'] = 0.0
        
        # 3. 几何指标
        # HRV三角指数 (简化版)
        hist, bin_edges = np.histogram(rr_intervals, bins=10)
        metrics['triangular_index'] = float(len(rr_intervals) / max(hist)) if max(hist) > 0 else 0
        
        return metrics
    
    def calculate_stress_score(self, hrv_metrics):
        """
        基于HRV指标计算压力评分 (0-1)
        
        压力越大，分数越高
        基于以下科学依据:
        1. 高压时RMSSD降低 (副交感神经活动减少)
        2. 高压时平均心率升高
        3. 高压时心率变异性降低
        """
        if not hrv_metrics:
            return 0.5  # 默认中等压力
        
        score = 0.0
        weights = {
            'rmssd': 0.4,      # RMSSD最重要
            'avg_heart_rate': 0.3,
            'hr_std': 0.2,
            'triangular_index': 0.1
        }
        
        # 1. RMSSD评分 (越低压力越大)
        rmssd = hrv_metrics['rmssd']
        if rmssd > 50:      # 优秀
            rmssd_score = 0.0
        elif rmssd > 30:    # 良好
            rmssd_score = 0.2
        elif rmssd > 20:    # 一般
            rmssd_score = 0.4
        elif rmssd > 10:    # 较差
            rmssd_score = 0.7
        else:               # 很差
            rmssd_score = 1.0
        score += rmssd_score * weights['rmssd']
        
        # 2. 平均心率评分 (越高压力越大)
        avg_hr = hrv_metrics['avg_heart_rate']
        if avg_hr < 60:     # 优秀 (运动员水平)
            hr_score = 0.0
        elif avg_hr < 70:   # 良好
            hr_score = 0.2
        elif avg_hr < 80:   # 一般
            hr_score = 0.4
        elif avg_hr < 90:   # 较高
            hr_score = 0.7
        else:               # 很高
            hr_score = 1.0
        score += hr_score * weights['avg_heart_rate']
        
        # 3. 心率变异性评分 (标准差，越低压力越大)
        hr_std = hrv_metrics['hr_std']
        if hr_std > 15:     # 优秀
            std_score = 0.0
        elif hr_std > 10:   # 良好
            std_score = 0.3
        elif hr_std > 5:    # 一般
            std_score = 0.6
        else:               # 很差
            std_score = 1.0
        score += std_score * weights['hr_std']
        
        # 确保分数在0-1之间
        return min(max(score, 0.0), 1.0)
    
    def get_stress_level_description(self, score):
        """根据压力分数返回描述"""
        if score < 0.3:
            return "低压力", "状态优秀，保持良好生活习惯"
        elif score < 0.5:
            return "轻度压力", "状态良好，注意适当休息"
        elif score < 0.7:
            return "中度压力", "建议进行放松练习，如深呼吸"
        elif score < 0.85:
            return "较高压力", "建议休息调整，避免过度劳累"
        else:
            return "高压力", "建议寻求专业帮助，进行深度放松"
    
    def get_recommendations(self, score, hrv_metrics):
        """根据压力水平和HRV指标提供个性化建议"""
        recommendations = []
        
        # 基于压力水平
        if score > 0.7:
            recommendations.append("立即进行5-10分钟深呼吸练习")
            recommendations.append("考虑短暂休息15-20分钟")
            recommendations.append("避免咖啡因和刺激性食物")
        elif score > 0.5:
            recommendations.append("进行3-5分钟深呼吸")
            recommendations.append("每小时起身活动5分钟")
            recommendations.append("保持充足水分摄入")
        
        # 基于HRV指标
        if hrv_metrics:
            if hrv_metrics['rmssd'] < 20:
                recommendations.append("副交感神经活动较低，建议冥想练习")
            if hrv_metrics['avg_heart_rate'] > 85:
                recommendations.append("心率偏高，建议放松活动")
            if hrv_metrics['hr_std'] < 5:
                recommendations.append("心率变异性低，建议有氧运动")
        
        # 默认建议
        if not recommendations:
            recommendations.append("状态良好，保持当前节奏")
            recommendations.append("定期监测压力水平")
        
        return recommendations
    
    def execute(self, data):
        """
        执行压力分析
        
        参数:
            data: 包含'heart_rate'键的字典
            
        返回:
            dict: 压力分析结果
        """
        heart_rate = data.get('heart_rate', [])
        
        # 数据验证
        if not heart_rate:
            return {"error": "未提供心率数据"}
        
        if len(heart_rate) < 10:
            return {
                "error": "数据不足",
                "message": f"至少需要10个心率数据点，当前只有{len(heart_rate)}个",
                "suggestion": "请收集更长时间的心率数据"
            }
        
        # 检查数据有效性
        heart_rate = [float(hr) for hr in heart_rate if 30 <= hr <= 200]
        if len(heart_rate) < 10:
            return {"error": "有效数据不足", "valid_points": len(heart_rate)}
        
        try:
            # 计算HRV指标
            hrv_metrics = self.calculate_hrv_metrics(heart_rate)
            
            if not hrv_metrics:
                return {"error": "HRV计算失败"}
            
            # 计算压力分数
            stress_score = self.calculate_stress_score(hrv_metrics)
            
            # 获取描述和建议
            level, description = self.get_stress_level_description(stress_score)
            recommendations = self.get_recommendations(stress_score, hrv_metrics)
            
            # 构建结果
            result = {
                "stress_level": float(stress_score),
                "stress_description": level,
                "analysis": description,
                "recommendations": recommendations,
                "hrv_metrics": {
                    "avg_heart_rate": hrv_metrics['avg_heart_rate'],
                    "heart_rate_std": hrv_metrics['hr_std'],
                    "rmssd": hrv_metrics['rmssd'],
                    "sdnn": hrv_metrics['sdnn']
                },
                "data_summary": {
                    "data_points": len(heart_rate),
                    "valid_points": len(heart_rate),
                    "heart_rate_range": f"{min(heart_rate):.1f}-{max(heart_rate):.1f} bpm"
                }
            }
            
            return result
            
        except Exception as e:
            return {
                "error": "分析过程中出现错误",
                "exception": str(e),
                "suggestion": "请检查心率数据格式是否正确"
            }