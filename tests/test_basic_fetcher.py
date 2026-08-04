"""
基础功能测试 - 只测试不依赖PyTorch的部分
"""

import sys
import os
import logging
from pathlib import Path

# 添加项目根目录
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BasicTest")

print("=" * 50)
print("测试基础功能（不依赖PyTorch）")
print("=" * 50)

# 先检查PyTorch状态
try:
    import torch
    print(f"[OK] PyTorch可用: {torch.__version__}")
    USE_PYTORCH = True
except:
    print("[WARN] PyTorch不可用，只能测试基础功能")
    USE_PYTORCH = False

print("\n1. 测试基础类导入")
try:
    from auto_data_fetcher import (
        DataSource, 
        DatasetInfo,
        EEGSpecificAugmentation,
        DataConfig,
        GlobalConfig
    )
    print("[OK] 基础类导入成功")
except Exception as e:
    print(f"[FAIL] 基础类导入失败: {e}")

print("\n2. 测试EEG增强功能")
try:
    from auto_data_fetcher import EEGSpecificAugmentation
    import numpy as np
    
    augmenter = EEGSpecificAugmentation(sampling_rate=100)
    test_eeg = np.random.randn(5, 1000)
    
    # 测试增强方法
    aug_methods = [
        ("通道丢弃", augmenter.channel_dropout(test_eeg, p=1.0)),
        ("通道洗牌", augmenter.channel_shuffle(test_eeg, p=1.0)),
        ("高斯噪声", augmenter.add_gaussian_noise(test_eeg, snr_db=20)),
        ("时间偏移", augmenter.time_shift(test_eeg, max_shift_ms=100)),
    ]
    
    for name, result in aug_methods:
        print(f"  {name}: {result.shape} [OK]")
    
    print("[OK] EEG增强功能测试通过")
except Exception as e:
    print(f"[FAIL] EEG增强测试失败: {e}")

print("\n3. 测试配置功能")
try:
    from auto_data_fetcher import DataConfig, GlobalConfig
    
    data_config = DataConfig()
    print(f"  data_dir: {data_config.data_dir}")
    print(f"  sampling_rate: {data_config.sampling_rate}")
    
    global_config = GlobalConfig(data=data_config)
    print("[OK] 配置功能测试通过")
except Exception as e:
    print(f"[FAIL] 配置测试失败: {e}")

print("\n4. 测试数据获取器基础功能")
try:
    from auto_data_fetcher import AutoDataFetcher
    
    config = GlobalConfig(data=DataConfig())
    fetcher = AutoDataFetcher(config, logger)
    
    print(f"  数据源数量: {len(fetcher.sources)}")
    print(f"  增强状态: {fetcher.augmentation_enabled}")
    
    stats = fetcher.get_stats()
    print(f"  统计信息: {stats}")
    print("[OK] 数据获取器基础功能测试通过")
except Exception as e:
    print(f"[FAIL] 数据获取器测试失败: {e}")

print("\n5. 测试特征提取器")
try:
    from auto_data_fetcher import MultiModalFeatureExtractor
    
    config = GlobalConfig(data=DataConfig())
    extractor = MultiModalFeatureExtractor(config)
    print("[OK] 特征提取器创建成功")
except Exception as e:
    print(f"[FAIL] 特征提取器测试失败: {e}")

print("\n" + "=" * 50)
print("基础功能测试完成！")
print("=" * 50)

# 如果PyTorch不可用，给出修复建议
if not USE_PYTORCH:
    print("\n[WARN] PyTorch不可用，建议修复:")
    print("""
    1. 创建新环境:
       conda deactivate
       conda remove -n neuroforge_311 --all -y
       conda create -n neuroforge python=3.10 -y
       conda activate neuroforge
       pip install torch --index-url https://download.pytorch.org/whl/cpu
    
    2. 或者暂时使用基础功能
    """)