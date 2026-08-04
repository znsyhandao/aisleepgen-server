"""
完整功能测试 - 测试所有模块
"""

import sys
import os
import logging
from pathlib import Path
import numpy as np
import torch

# 添加项目根目录
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FullTest")

print("=" * 50)
print("完整功能测试")
print("=" * 50)

# 1. 测试所有导入
print("\n1. 测试所有模块导入")
try:
    from auto_data_fetcher import (
        # 基础类
        DataSource, DatasetInfo,
        # EEG增强
        EEGSpecificAugmentation,
        # 配置
        DataConfig, ModelConfig, GlobalConfig,
        # 预处理和数据管理
        EEGDataPreprocessor, DataManager,
        # Transformer模型
        AdvancedTransformerBlock, MultiScaleTransformer,
        # 基础模型
        NeuroForgeModel, LSTMModel, CNNModel,
        # 集成模型
        EnsembleModel,
        # 多模态
        MultiModalFeatureExtractor, MultiModalFusionModel,
        # 数据获取器
        AutoDataFetcher, AugmentedAutoDataFetcher,
        # 训练流水线
        TrainingPipeline,
        # 集成类
        NeuroForgeDataIntegration
    )
    print("[OK] 所有模块导入成功")
except Exception as e:
    print(f"[FAIL] 导入失败: {e}")

# 2. 测试模型创建
print("\n2. 测试模型创建")
try:
    config = GlobalConfig(
        data=DataConfig(),
        model=ModelConfig(
            hidden_dim=64,
            num_heads=4,
            num_classes=5,
            dropout=0.1
        )
    )
    
    batch_size = 4
    seq_len = 1000
    test_input = torch.randn(batch_size, 1, seq_len)
    print(f"测试输入形状: {test_input.shape}")
    
    # 测试每个模型
    models = [
        ("MultiScaleTransformer", MultiScaleTransformer(config)),
        ("NeuroForgeModel", NeuroForgeModel(config)),
        ("LSTMModel", LSTMModel(config)),
        ("CNNModel", CNNModel(config)),
        ("EnsembleModel", EnsembleModel(config))
    ]
    
    for name, model in models:
        output = model(test_input)
        print(f"  {name}: 输出形状 {output.shape} [OK]")
    
    print("[OK] 所有模型创建成功")
except Exception as e:
    print(f"[FAIL] 模型测试失败: {e}")

# 3. 测试数据获取器增强功能
print("\n3. 测试数据获取器增强功能")
try:
    fetcher = AutoDataFetcher(config, logger)
    
    # 创建模拟数据
    n_samples = 5
    n_channels = 4
    n_times = 1000
    test_data = np.random.randn(n_samples, n_channels, n_times)
    test_labels = np.random.randint(0, 5, n_samples)
    
    print(f"原始数据: {test_data.shape}, 标签: {test_labels.shape}")
    
    # 增强数据
    augmented_data, augmented_labels = fetcher.augment_data(test_data, test_labels)
    
    print(f"增强后数据: {augmented_data.shape}, 标签: {augmented_labels.shape}")
    print(f"数据量增加: {len(test_data)} -> {len(augmented_data)}")
    print("[OK] 数据增强功能测试通过")
except Exception as e:
    print(f"[FAIL] 数据增强测试失败: {e}")

# 4. 测试AugmentedAutoDataFetcher
print("\n4. 测试增强版数据获取器")
try:
    aug_fetcher = AugmentedAutoDataFetcher(config, logger)
    
    # 测试process_and_augment
    test_data = np.random.randn(3, 4, 1000)
    test_labels = np.random.randint(0, 5, 3)
    
    result_data, result_labels = aug_fetcher.process_and_augment(test_data, test_labels)
    
    print(f"process_and_augment: {result_data.shape}, 标签: {result_labels.shape}")
    print(f"增强统计: {aug_fetcher.get_augmentation_stats()}")
    print("[OK] 增强版数据获取器测试通过")
except Exception as e:
    print(f"[FAIL] 增强版数据获取器测试失败: {e}")

# 5. 测试TrainingPipeline（只初始化，不训练）
print("\n5. 测试训练流水线初始化")
try:
    pipeline = TrainingPipeline(config, logger)
    print(f"设备: {pipeline.device}")
    print(f"模型类型: {type(pipeline.model).__name__}")
    print("[OK] 训练流水线初始化成功")
except Exception as e:
    print(f"[FAIL] 训练流水线测试失败: {e}")

# 6. 测试NeuroForgeDataIntegration
print("\n6. 测试系统集成类")
try:
    # 创建一个模拟的neuroforge_system
    class MockSystem:
        def __init__(self):
            self.config = config
            self.logger = logger
    
    mock_system = MockSystem()
    integration = NeuroForgeDataIntegration(mock_system)
    
    print(f"集成类创建成功")
    print(f"获取器类型: {type(integration.fetcher).__name__}")
    print("[OK] 系统集成类测试通过")
except Exception as e:
    print(f"[FAIL] 系统集成类测试失败: {e}")

print("\n" + "=" * 50)
print("完整功能测试完成！")
print("=" * 50)