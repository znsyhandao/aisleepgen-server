"""
完整的测试脚本 - 测试所有功能
包括需要PyTorch的模型测试
"""

import sys
import os
import logging
from pathlib import Path
import numpy as np

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("CompleteTest")

def test_all_imports():
    """测试所有导入"""
    print("=" * 50)
    print("测试所有模块导入")
    print("=" * 50)
    
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
        print("[OK] 成功导入所有模块！")
        return True
    except Exception as e:
        print(f"[FAIL] 导入失败: {e}")
        return False

def test_torch_basic():
    """测试PyTorch基本功能"""
    print("\n" + "=" * 50)
    print("测试PyTorch基本功能")
    print("=" * 50)
    
    try:
        import torch
        
        # 创建张量
        x = torch.randn(3, 3)
        print(f"[OK] 张量创建: {x.shape}")
        
        # 基本运算
        y = x * 2
        print(f"[OK] 基本运算: {y.shape}")
        
        # 创建简单模型
        model = torch.nn.Linear(10, 5)
        print(f"[OK] 模型创建: {model}")
        
        return True
    except Exception as e:
        print(f"[FAIL] PyTorch测试失败: {e}")
        return False

def test_model_creation():
    """测试模型创建"""
    print("\n" + "=" * 50)
    print("测试模型创建")
    print("=" * 50)
    
    try:
        from auto_data_fetcher import ModelConfig, GlobalConfig, DataConfig
        from auto_data_fetcher import (
            MultiScaleTransformer, NeuroForgeModel, 
            LSTMModel, CNNModel, EnsembleModel
        )
        import torch
        
        # 创建配置
        config = GlobalConfig(
            data=DataConfig(),
            model=ModelConfig(
                hidden_dim=64,
                num_heads=4,
                num_classes=5,
                dropout=0.1
            )
        )
        
        # 测试输入
        batch_size = 4
        seq_len = 1000
        test_input = torch.randn(batch_size, 1, seq_len)
        print(f"测试输入形状: {test_input.shape}")
        
        # 测试各个模型
        models = [
            ("MultiScaleTransformer", MultiScaleTransformer(config)),
            ("NeuroForgeModel", NeuroForgeModel(config)),
            ("LSTMModel", LSTMModel(config)),
            ("CNNModel", CNNModel(config)),
            ("EnsembleModel", EnsembleModel(config))
        ]
        
        for name, model in models:
            try:
                output = model(test_input)
                print(f"[OK] {name}: 输出形状 {output.shape}")
            except Exception as e:
                print(f"[FAIL] {name}: {e}")
        
        return True
    except Exception as e:
        print(f"[FAIL] 模型测试失败: {e}")
        return False

def test_eeg_augmentation():
    """测试EEG增强"""
    print("\n" + "=" * 50)
    print("测试EEG增强功能")
    print("=" * 50)
    
    try:
        from auto_data_fetcher import EEGSpecificAugmentation
        import numpy as np
        
        augmenter = EEGSpecificAugmentation(sampling_rate=100)
        
        # 创建测试数据
        n_channels = 5
        n_times = 1000
        test_eeg = np.random.randn(n_channels, n_times) * 10
        
        print(f"原始数据形状: {test_eeg.shape}")
        
        # 测试各种增强
        tests = [
            ("通道丢弃", augmenter.channel_dropout(test_eeg, p=1.0)),
            ("通道洗牌", augmenter.channel_shuffle(test_eeg, p=1.0)),
            ("高斯噪声", augmenter.add_gaussian_noise(test_eeg, snr_db=20)),
            ("时间偏移", augmenter.time_shift(test_eeg, max_shift_ms=100)),
            ("频率偏移", augmenter.frequency_shift(test_eeg, max_shift_hz=0.5)),
            ("遮盖", augmenter.cutout(test_eeg, cut_length_ms=500)),
        ]
        
        for name, result in tests:
            print(f"  {name}: {result.shape} [OK]")
        
        # 测试选择性增强
        stages = ['W', 'N1', 'N2', 'N3', 'REM']
        for stage in stages:
            result = augmenter.selective_augment(test_eeg, stage)
            print(f"  选择性增强 ({stage}): {result.shape} [OK]")
        
        return True
    except Exception as e:
        print(f"[FAIL] EEG增强测试失败: {e}")
        return False

def test_data_fetcher_basic():
    """测试数据获取器基础功能"""
    print("\n" + "=" * 50)
    print("测试数据获取器基础功能")
    print("=" * 50)
    
    try:
        from auto_data_fetcher import AutoDataFetcher, DataConfig, GlobalConfig
        
        config = GlobalConfig(data=DataConfig())
        fetcher = AutoDataFetcher(config, logger)
        
        print(f"数据源数量: {len(fetcher.sources)}")
        print(f"增强状态: {fetcher.augmentation_enabled}")
        
        # 测试统计信息
        stats = fetcher.get_stats()
        print(f"统计信息: {stats}")
        
        return True
    except Exception as e:
        print(f"[FAIL] 数据获取器测试失败: {e}")
        return False

def test_training_pipeline():
    """测试训练流水线（不实际训练）"""
    print("\n" + "=" * 50)
    print("测试训练流水线初始化")
    print("=" * 50)
    
    try:
        from auto_data_fetcher import TrainingPipeline, DataConfig, GlobalConfig
        
        config = GlobalConfig(data=DataConfig())
        pipeline = TrainingPipeline(config, logger)
        
        print(f"[OK] 训练流水线创建成功")
        print(f"设备: {pipeline.device}")
        print(f"模型类型: {type(pipeline.model).__name__}")
        
        return True
    except Exception as e:
        print(f"[FAIL] 训练流水线测试失败: {e}")
        return False

if __name__ == "__main__":
    print("开始完整测试...\n")
    
    # 运行所有测试
    tests = [
        ("所有模块导入", test_all_imports),
        ("PyTorch基本功能", test_torch_basic),
        ("模型创建", test_model_creation),
        ("EEG增强", test_eeg_augmentation),
        ("数据获取器基础", test_data_fetcher_basic),
        ("训练流水线", test_training_pipeline)
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n▶️ 运行测试: {name}")
        try:
            result = test_func()
            results.append((name, "[OK] 通过" if result else "[FAIL] 失败"))
        except Exception as e:
            print(f"测试执行出错: {e}")
            results.append((name, f"[FAIL] 错误: {e}"))
    
    # 打印总结
    print("\n" + "=" * 50)
    print("测试结果总结")
    print("=" * 50)
    for name, result in results:
        print(f"{name}: {result}")
    
    print("\n" + "=" * 50)
    print("测试完成！")