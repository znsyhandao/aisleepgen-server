class AudioFeedback:
    def __init__(self, device_manager):
        print("AudioFeedback initialized")
    
    async def apply(self, biometrics):
        return {
            'type': 'audio',
            'sound': 'white_noise',
            'volume': 0.5,  # 默认音量
            'duration': 300  # 默认5分钟
        }