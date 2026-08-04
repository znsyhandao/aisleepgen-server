from typing import Dict, Any  # Add this import at the top
import os
import json


# 默认配置常量
DEFAULT_CONFIG = {
    'name': '默认配置',
    'theme': 'light',
    'voice': 'female',
    'difficulty': 'medium',
    'breath_patterns': {
        '4-7-8': {'inhale': 4, 'hold': 7, 'exhale': 8},
        'box': {'inhale': 4, 'hold': 4, 'exhale': 4, 'rest': 4},
        'coh': {'inhale': 5, 'hold': 0, 'exhale': 5, 'rest': 2}
    },
    'audio_settings': {
        'volume': 0.7,
        'background': 'nature'
    }
}

# 使用默认配置初始化cfg变量
cfg = DEFAULT_CONFIG.copy()

class InvalidConfigError(Exception):
    """配置验证失败时抛出的异常"""
    pass
def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """
    从配置文件加载配置
    参数:
        config_path: 配置文件路径
    返回:
        配置字典
    异常:
        FileNotFoundError: 当配置文件不存在时抛出
        json.JSONDecodeError: 当配置文件不是有效的JSON时抛出
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            raise InvalidConfigError(f"Invalid JSON config: {str(e)}")
def validate_config(config: dict) -> None:
        """
    验证配置字典是否符合要求
    参数:
        config: 要验证的配置字典
    异常:
        InvalidConfigError: 当配置无效时抛出
    """
        required_keys = {
            'monitor_interval': int,
            'hardware_timeout': (int, float)
        
        }

    # 新增：检查是否有未知参数
        unknown_keys = set(config.keys()) - set(required_keys.keys())
        if unknown_keys:
            print(f"⚠️ 警告：配置中包含未验证的参数: {unknown_keys}") 

        for key, typ in required_keys.items():
            if key not in config:
                raise InvalidConfigError(f"Missing required config key: {key}")
            if not isinstance(config[key], typ):
                expected_types = typ.__name__ if isinstance(typ, type) else " or ".join(t.__name__ for t in typ)
                raise InvalidConfigError(
                    f"Invalid type for {key}: expected {expected_types}, got {type(config[key]).__name__}"
                )