
from plugin_manager import BasePlugin, PluginInfo, PluginType

class BreathingMeditationPlugin(BasePlugin):
    """呼吸冥想插件"""
    
    def __init__(self):
        super().__init__()
        self.info = PluginInfo(
            name="呼吸冥想",
            version="1.0.0",
            plugin_type=PluginType.MEDITATION_METHOD,
            description="引导式呼吸冥想方法",
            author="AISleepGen"
        )
    
    def execute(self, data):
        duration = data.get('duration', 300)
        technique = data.get('technique', '4-7-8')
        
        return {
            "method": "breathing",
            "duration": duration,
            "technique": technique,
            "steps": [
                "深吸气4秒",
                "屏息7秒", 
                "缓慢呼气8秒",
                "重复循环"
            ]
        }
