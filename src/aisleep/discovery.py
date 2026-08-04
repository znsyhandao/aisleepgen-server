class ServiceRegistry:
    def __init__(self):
        self.services = {}

    def register(self, name: str, obj: object):
        self.services[name] = obj

    async def initialize(self):
        """异步初始化所有已注册服务"""
        for name, service in self.services.items():
            if hasattr(service, 'async_init'):
                await service.async_init()
class ServiceRegistry:
    def __init__(self):
        self.services = {}
        self._initialized = False

    def register(self, name: str, service: object):
        """注册服务"""
        if self._initialized:
            raise RuntimeError("Cannot register after initialization")
        self.services[name] = service

    async def initialize(self):
        """初始化所有已注册服务"""
        for name, service in self.services.items():
            if hasattr(service, 'async_init'):
                await service.async_init()
        self._initialized = True

    def get(self, name: str):
        """获取已注册服务"""
        return self.services.get(name)
