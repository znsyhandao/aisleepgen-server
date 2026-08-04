class DataCollector:
    def __init__(self, device_manager):
        self.device = device_manager
        
    async def collect_long_term_data(self):
        """持续收集用户睡眠数据"""
        while True:
            data = {
                'timestamp': datetime.now(),
                'biometrics': await self.device.get_realtime_data(),
                'environment': self.device.get_environment_data()
            }
            self._save_to_db(data)
            await asyncio.sleep(300)  # 每5分钟采集一次
