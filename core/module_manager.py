# module_manager.py
from typing import Dict, List, Type, Optional, Any
import importlib
import os

class ModuleManager:
    """模块管理器，负责模块的注册、发现和生命周期管理"""
    
    def __init__(self):
        self.modules: Dict[str, Any] = {}
        self.module_classes: Dict[str, Type] = {}
        self.config: Dict[str, Dict] = {}
        
    def register_module(self, name: str, module_class: Type, config: Dict = None):
        """注册模块"""
        self.module_classes[name] = module_class
        if config:
            self.config[name] = config
            
    def instantiate_module(self, name: str, config: Dict = None) -> Optional[Any]:
        """实例化模块"""
        if name not in self.module_classes:
            print(f"模块 {name} 未注册")
            return None
            
        try:
            merged_config = self.config.get(name, {}).copy()
            if config:
                merged_config.update(config)
            module = self.module_classes[name](merged_config)
            self.modules[name] = module
            return module
        except Exception as e:
            print(f"实例化模块 {name} 失败: {e}")
            return None
            
    def get_module(self, name: str) -> Optional[Any]:
        """获取已实例化的模块"""
        return self.modules.get(name)
        
    def initialize_all(self) -> bool:
        """初始化所有模块"""
        success = True
        for name, module in self.modules.items():
            if hasattr(module, 'initialize'):
                if not module.initialize():
                    print(f"初始化模块 {name} 失败")
                    success = False
        return success
        
    def start_all(self) -> bool:
        """启动所有模块"""
        success = True
        for name, module in self.modules.items():
            if hasattr(module, 'start'):
                if not module.start():
                    print(f"启动模块 {name} 失败")
                    success = False
        return success
        
    def stop_all(self) -> bool:
        """停止所有模块"""
        success = True
        for name, module in self.modules.items():
            if hasattr(module, 'stop'):
                if not module.stop():
                    print(f"停止模块 {name} 失败")
                    success = False
        return success