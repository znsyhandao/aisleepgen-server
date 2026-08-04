import pytest
import numpy as np
from data_generator import VirtualSubjectGAN, PERGDataLoader

@pytest.fixture
def gan():
    return VirtualSubjectGAN()

@pytest.fixture
def loader():
    return PERGDataLoader()

def test_gan_training(gan, loader):
    """测试GAN训练流程"""
    # 加载数据
    data = loader.load_all_csvs()
    X_train = data[['RE_1', 'LE_1']].values[:1000]  # 使用部分数据
    
    # 训练
    gan.train(X_train, epochs=1, batch_size=32)
    
    # 验证训练记录
    assert len(gan.g_loss_history) > 0, "生成器未记录损失"
    assert len(gan.d_loss_history) > 0, "判别器未记录损失"
    
    # 验证模型更新
    initial_weights = gan.weight_history[0]
    final_weights = gan.weight_history[-1]
    assert not np.allclose(initial_weights, final_weights), "模型权重未更新"

def test_gan_generation(gan):
    """测试GAN生成能力"""
    # 生成样本
    samples = gan.generate(100)
    
    # 验证结果
    assert samples.shape == (100, 2), "生成样本维度错误"
    assert np.abs(samples).max() < 5, "生成信号幅度异常"

def test_spectral_constraint(gan):
    """测试频谱约束"""
    # 生成测试数据
    real_data = np.random.normal(0, 0.1, (2048, 2))
    
    # 计算约束损失
    loss = gan._apply_spectral_constraint(real_data)
    
    # 验证结果
    assert 0 <= loss <= 5.0, "频谱约束损失超出预期范围"
