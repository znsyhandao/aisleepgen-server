# test_fetcher_only.py
import sys
import os
import logging
from pathlib import Path

# 添加项目根目录
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Test")

# 只导入不依赖PyTorch的模块
from auto_data_fetcher import (
    DataSource, 
    DatasetInfo, 
    EEGSpecificAugmentation,
    DataConfig,
    GlobalConfig,
    AutoDataFetcher,
    AugmentedAutoDataFetcher,
    MultiModalFeatureExtractor
)

print("[OK] 基础模块导入成功！")

# 测试EEG增强
augmenter = EEGSpecificAugmentation(sampling_rate=100)
print("[OK] EEG增强模块导入成功！")

# 测试配置
config = GlobalConfig(data=DataConfig())
print("[OK] 配置模块导入成功！")

# 测试数据获取器
fetcher = AutoDataFetcher(config, logger)
print("[OK] 数据获取器导入成功！")

print("\n所有基础功能测试通过！")