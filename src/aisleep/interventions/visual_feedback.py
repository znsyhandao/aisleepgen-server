class VisualFeedback:
    def __init__(self, device_manager):
        print("VisualFeedback initialized")
    
    async def apply(self, biometrics):
        return {
            'type': 'visual',
            'pattern': 'calming_wave',
            'duration': 300  # 默认5分钟
        }