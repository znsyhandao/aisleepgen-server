class DummyTherapyEngine:
    def __init__(self):
        self.PROTOCOLS = {
            "放松模式": {},
            "深度睡眠": {}
        }
        self._running = False
        
    def start_engine(self):
        self._running = True
        
    def stop_engine(self):
        self._running = False
        
    def validate_protocol(self, protocol, profile):
        return True, ""
