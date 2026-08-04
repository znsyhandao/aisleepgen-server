# sensor_base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import time

class SensorBase(ABC):
    """传感器抽象基类，定义统一接口"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.is_initialized = False
        self.is_running = False
        self.last_data = None
        self.last_timestamp = 0
        
    @abstractmethod
    def initialize(self) -> bool:
        """初始化传感器"""
        pass
        
    @abstractmethod
    def start(self) -> bool:
        """启动传感器"""
        pass
        
    @abstractmethod
    def stop(self) -> bool:
        """停止传感器"""
        pass
        
    @abstractmethod
    def read_data(self) -> Optional[Dict[str, Any]]:
        """读取传感器数据"""
        pass
        
    def get_status(self) -> Dict[str, Any]:
        """获取传感器状态"""
        return {
            'initialized': self.is_initialized,
            'running': self.is_running,
            'last_timestamp': self.last_timestamp,
            'type': self.__class__.__name__
        }
        
    def validate_config(self) -> bool:
        """验证配置"""
        try:
            self._validate_config()
            return True
        except Exception as e:
            print(f"配置验证失败: {e}")
            return False
            
    def _validate_config(self):
        """子类实现具体的配置验证"""
        pass