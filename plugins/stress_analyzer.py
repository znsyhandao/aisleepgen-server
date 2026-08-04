
from plugin_manager import BasePlugin, PluginInfo, PluginType

class StressAnalyzerPlugin(BasePlugin):
    """压力分析插件"""
    
    def __init__(self):
        super().__init__()
        self.info = PluginInfo(
            name="压力分析",
            version="1.0.0",
            plugin_type=PluginType.DATA_ANALYSIS,
            description="基于心率变异的压力分析",
            author="AISleepGen"
        )
    
    def execute(self, data):
        heart_rate = data.get('heart_rate', [])
        
        # 简单压力分析逻辑
        if len(heart_rate) > 10:
            avg_hr = sum(heart_rate) / len(heart_rate)
            hr_variability = max(heart_rate) - min(heart_rate)
            
            stress_level = 0.0
            if avg_hr > 80:
                stress_level += 0.4
            if hr_variability < 10:
                stress_level += 0.3
            if max(heart_rate) > 100:
                stress_level += 0.3
            
            return {
                "stress_level": min(stress_level, 1.0),
                "analysis": "基于心率数据的压力评估",
                "recommendation": "建议进行呼吸练习" if stress_level > 0.6 else "状态良好"
            }
        
        return {"error": "数据不足"}
