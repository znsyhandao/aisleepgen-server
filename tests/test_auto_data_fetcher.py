# test_auto_data_fetcher.py
"""
测试自动数据获取器的各个功能模块
"""

import unittest
import logging
import numpy as np
import torch
from pathlib import Path
import tempfile
import shutil
from datetime import datetime
from dataclasses import dataclass, field
import sys
import os
# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestNeuroForge")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# 导入需要测试的类
from auto_data_fetcher import (
    DataSource, DatasetInfo, EEGSpecificAugmentation,
    AdvancedTransformerBlock, MultiScaleTransformer,
    NeuroForgeModel, LSTMModel, CNNModel, EnsembleModel,
    MultiModalFeatureExtractor, MultiModalFusionModel,
    AutoDataFetcher, AugmentedAutoDataFetcher, NeuroForgeDataIntegration
)


# 测试配置
# 在测试文件中，更新配置定义
@dataclass
class DataConfig:
    data_dir: str
    cache_dir: str
    sampling_rate: int = 100


@dataclass
class ModelConfig:
    hidden_dim: int = 64  # 减小维度加快测试
    num_heads: int = 4
    num_classes: int = 5
    dropout: float = 0.1


@dataclass
class GlobalConfig:
    data: DataConfig
    model: ModelConfig = field(default_factory=ModelConfig)  # 确保有model属性


def setUp(self):
    # 在测试类的setUp方法中正确初始化
    self.config = GlobalConfig(
        data=DataConfig(data_dir="test", cache_dir="test_cache"),
        model=ModelConfig()  # 显式创建ModelConfig
    )


class TestEEGAugmentation(unittest.TestCase):
    """测试EEG增强模块"""
    
    def setUp(self):
        self.augmenter = EEGSpecificAugmentation(sampling_rate=100)
        # 创建测试数据：5通道，1000时间点
        self.test_eeg = np.random.randn(5, 1000) * 10  # 模拟EEG信号
        
    def test_channel_dropout(self):
        """测试通道丢弃"""
        augmented = self.augmenter.channel_dropout(self.test_eeg, p=1.0)  # 强制执行
        self.assertEqual(self.test_eeg.shape, augmented.shape)
        # 检查是否有通道被置零
        zero_channels = np.sum(augmented == 0, axis=1) > 0
        self.assertTrue(np.any(zero_channels))
        print("[SYMBOL] 通道丢弃测试通过")
        
    def test_channel_shuffle(self):
        """测试通道洗牌"""
        augmented = self.augmenter.channel_shuffle(self.test_eeg, p=1.0)
        self.assertEqual(self.test_eeg.shape, augmented.shape)
        # 检查通道顺序是否改变
        self.assertFalse(np.array_equal(self.test_eeg, augmented))
        print("[SYMBOL] 通道洗牌测试通过")
        
    def test_gaussian_noise(self):
        """测试高斯噪声"""
        augmented = self.augmenter.add_gaussian_noise(self.test_eeg, snr_db=20)
        self.assertEqual(self.test_eeg.shape, augmented.shape)
        # 检查信号是否变化
        self.assertFalse(np.array_equal(self.test_eeg, augmented))
        print("[SYMBOL] 高斯噪声测试通过")
        
    def test_time_shift(self):
        """测试时间偏移"""
        augmented = self.augmenter.time_shift(self.test_eeg, max_shift_ms=100)
        self.assertEqual(self.test_eeg.shape, augmented.shape)
        print("[SYMBOL] 时间偏移测试通过")
        
    def test_frequency_shift(self):
        """测试频率偏移"""
        augmented = self.augmenter.frequency_shift(self.test_eeg, max_shift_hz=0.5)
        self.assertEqual(self.test_eeg.shape, augmented.shape)
        print("[SYMBOL] 频率偏移测试通过")
        
    def test_cutout(self):
        """测试遮盖"""
        augmented = self.augmenter.cutout(self.test_eeg, cut_length_ms=500, max_cuts=2)
        self.assertEqual(self.test_eeg.shape, augmented.shape)
        print("[SYMBOL] 遮盖测试通过")
        
    def test_selective_augment(self):
        """测试选择性增强"""
        stages = ['W', 'N1', 'N2', 'N3', 'REM']
        for stage in stages:
            augmented = self.augmenter.selective_augment(self.test_eeg, stage)
            self.assertEqual(self.test_eeg.shape, augmented.shape)
        print("[SYMBOL] 选择性增强测试通过")


class TestModels(unittest.TestCase):
    """测试模型模块"""
    
    def setUp(self):
        self.config = GlobalConfig(
            data=DataConfig(data_dir="test", cache_dir="test_cache")
        )
        self.batch_size = 4
        self.seq_len = 1000
        self.n_channels = 5
        # 创建测试输入
        self.test_input = torch.randn(self.batch_size, 1, self.seq_len)
        
    def test_advanced_transformer_block(self):
        """测试Transformer块"""
        block = AdvancedTransformerBlock(
            hidden_dim=64, num_heads=4, ff_dim=256, dropout=0.1
        )
        x = torch.randn(self.batch_size, 10, 64)  # (batch, seq, hidden)
        output = block(x)
        self.assertEqual(x.shape, output.shape)
        print("[SYMBOL] Transformer块测试通过")
        
    def test_multi_scale_transformer(self):
        """测试多尺度Transformer"""
        model = MultiScaleTransformer(self.config)
        output = model(self.test_input)
        self.assertEqual(output.shape, (self.batch_size, self.config.model.num_classes))
        print("[SYMBOL] 多尺度Transformer测试通过")
        
    def test_neuroforge_model(self):
        """测试基础模型"""
        model = NeuroForgeModel(self.config)
        output = model(self.test_input)
        self.assertEqual(output.shape, (self.batch_size, self.config.model.num_classes))
        print("[SYMBOL] NeuroForge模型测试通过")
        
    def test_lstm_model(self):
        """测试LSTM模型"""
        model = LSTMModel(self.config)
        output = model(self.test_input)
        self.assertEqual(output.shape, (self.batch_size, self.config.model.num_classes))
        print("[SYMBOL] LSTM模型测试通过")
        
    def test_cnn_model(self):
        """测试CNN模型"""
        model = CNNModel(self.config)
        output = model(self.test_input)
        self.assertEqual(output.shape, (self.batch_size, self.config.model.num_classes))
        print("[SYMBOL] CNN模型测试通过")
        
    def test_ensemble_model(self):
        """测试集成模型"""
        model = EnsembleModel(self.config)
        output = model(self.test_input)
        self.assertEqual(output.shape, (self.batch_size, self.config.model.num_classes))
        print("[SYMBOL] 集成模型测试通过")


class TestDataFetcher(unittest.TestCase):
    """测试数据获取器"""
    
    def setUp(self):
        # 创建临时目录
        self.test_dir = tempfile.mkdtemp()
        self.cache_dir = tempfile.mkdtemp()
        
        self.config = GlobalConfig(
            data=DataConfig(
                data_dir=self.test_dir,
                cache_dir=self.cache_dir,
                sampling_rate=100
            )
        )
        self.fetcher = AutoDataFetcher(self.config, logger)
        
    def tearDown(self):
        # 清理临时目录
        shutil.rmtree(self.test_dir)
        shutil.rmtree(self.cache_dir)
        
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.fetcher)
        self.assertEqual(len(self.fetcher.sources), len(AutoDataFetcher.DEFAULT_SOURCES))
        print("[SYMBOL] 初始化测试通过")
        
    def test_load_sources(self):
        """测试加载数据源"""
        sources = self.fetcher._load_sources()
        self.assertGreater(len(sources), 0)
        print("[SYMBOL] 加载数据源测试通过")
        
    def test_should_download(self):
        """测试下载判断"""
        dataset = DatasetInfo(
            name="test-sleep-edf",
            source="physionet",
            url="http://test.com/test.edf"
        )
        # 应该返回True（因为磁盘空间足够，且包含sleep关键词）
        result = self.fetcher._should_download(dataset)
        self.assertTrue(result)
        print("[SYMBOL] 下载判断测试通过")
        
    def test_stats(self):
        """测试统计信息"""
        stats = self.fetcher.get_stats()
        self.assertIn('total_discovered', stats)
        self.assertIn('total_downloaded', stats)
        self.assertIn('augmentation_enabled', stats)
        print("[SYMBOL] 统计信息测试通过")
        
    def test_augment_data(self):
        """测试数据增强"""
        # 创建测试数据
        test_data = np.random.randn(10, 5, 1000)  # 10个样本
        test_labels = np.random.randint(0, 5, 10)
        
        # 启用增强
        self.fetcher.enable_augmentation(True)
        
        # 增强数据
        augmented_data, augmented_labels = self.fetcher.augment_data(test_data, test_labels)
        
        # 验证数据量翻倍
        self.assertEqual(len(augmented_data), len(test_data) * 2)
        self.assertEqual(len(augmented_labels), len(test_labels) * 2)
        print("[SYMBOL] 数据增强测试通过")


class TestAugmentedFetcher(unittest.TestCase):
    """测试增强版数据获取器"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache_dir = tempfile.mkdtemp()
        
        self.config = GlobalConfig(
            data=DataConfig(
                data_dir=self.test_dir,
                cache_dir=self.cache_dir,
                sampling_rate=100
            )
        )
        self.fetcher = AugmentedAutoDataFetcher(self.config, logger)
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)
        shutil.rmtree(self.cache_dir)
        
    def test_process_and_augment(self):
        """测试处理并增强"""
        test_data = np.random.randn(5, 5, 1000)  # 5个样本
        test_labels = np.random.randint(0, 5, 5)
        
        augmented_data, augmented_labels = self.fetcher.process_and_augment(
            test_data, test_labels
        )
        
        self.assertEqual(len(augmented_data), 10)  # 原始5个 + 增强5个
        self.assertEqual(len(augmented_labels), 10)
        print("[SYMBOL] process_and_augment测试通过")
        
    def test_augmentation_stats(self):
        """测试增强统计"""
        stats = self.fetcher.get_augmentation_stats()
        self.assertIn('enabled', stats)
        self.assertIn('methods', stats)
        self.assertIn('sampling_rate', stats)
        print("[SYMBOL] 增强统计测试通过")


class TestFeatureExtractor(unittest.TestCase):
    """测试特征提取器"""
    
    def setUp(self):
        self.config = GlobalConfig(
            data=DataConfig(data_dir="test", cache_dir="test_cache")
        )
        self.extractor = MultiModalFeatureExtractor(self.config)
        
    def test_eog_features(self):
        """测试EOG特征提取"""
        test_eog = np.random.randn(2, 1000)
        features = self.extractor.extract_eog_features(test_eog)
        self.assertIsNotNone(features)
        print("[SYMBOL] EOG特征提取测试通过")
        
    def test_emg_features(self):
        """测试EMG特征提取"""
        test_emg = np.random.randn(1, 1000)
        features = self.extractor.extract_emg_features(test_emg)
        self.assertIsNotNone(features)
        print("[SYMBOL] EMG特征提取测试通过")


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("开始测试 NeuroForge 自动数据获取器")
    print("=" * 50)
    
    # 创建测试套件
    suite = unittest.TestSuite()
    
    # 添加测试用例
    suite.addTest(unittest.makeSuite(TestEEGAugmentation))
    suite.addTest(unittest.makeSuite(TestModels))
    suite.addTest(unittest.makeSuite(TestDataFetcher))
    suite.addTest(unittest.makeSuite(TestAugmentedFetcher))
    suite.addTest(unittest.makeSuite(TestFeatureExtractor))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 50)
    print(f"测试完成: 运行 {result.testsRun} 个测试")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")
    print("=" * 50)
    
    return result


if __name__ == "__main__":
    # 方式1：运行所有测试
    run_all_tests()
    
    # 方式2：单独运行某个测试类
    # unittest.main()
    
    # 方式3：手动测试各个功能
    print("\n" + "=" * 50)
    print("手动测试 EEG 增强功能")
    print("=" * 50)
    
    augmenter = EEGSpecificAugmentation(sampling_rate=100)
    test_eeg = np.random.randn(5, 1000)
    
    print(f"原始数据形状: {test_eeg.shape}")
    print(f"通道丢弃: {augmenter.channel_dropout(test_eeg, p=1.0).shape}")
    print(f"通道洗牌: {augmenter.channel_shuffle(test_eeg, p=1.0).shape}")
    print(f"高斯噪声: {augmenter.add_gaussian_noise(test_eeg, snr_db=20).shape}")
    print(f"时间偏移: {augmenter.time_shift(test_eeg, max_shift_ms=100).shape}")
    print(f"频率偏移: {augmenter.frequency_shift(test_eeg, max_shift_hz=0.5).shape}")
    print(f"遮盖: {augmenter.cutout(test_eeg, cut_length_ms=500).shape}")
    
    # 测试选择性增强
    stages = ['W', 'N1', 'N2', 'N3', 'REM']
    for stage in stages:
        augmented = augmenter.selective_augment(test_eeg, stage)
        print(f"选择性增强 ({stage}): {augmented.shape}")