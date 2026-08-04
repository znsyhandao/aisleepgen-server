import pytest
import numpy as np
from data_generator import TopoMapVisualizer, VirtualSubjectGAN

@pytest.fixture
def visualizer():
    return TopoMapVisualizer()

@pytest.fixture
def gan():
    return VirtualSubjectGAN()

def test_band_power_calculation(visualizer):
    """测试频段功率计算"""
    # 生成测试信号
    fs = visualizer.sample_rate
    t = np.arange(0, 1, 1/fs)
    test_signal = np.sin(2*np.pi*10*t)  # 10Hz正弦波
    
    # 计算频段功率
    band_powers = visualizer._calculate_band_power(test_signal)
    
    # 验证结果
    assert 'alpha' in band_powers, "缺少alpha频段"
    assert band_powers['alpha'] > band_powers['delta'], "alpha功率应大于delta"
    assert 0 <= band_powers['beta'] <= 1, "beta功率值异常"

def test_low_freq_analysis(gan):
    """测试低频分析"""
    # 生成低频测试信号
    fs = gan.sample_rate
    t = np.arange(0, 5, 1/fs)  # 5秒信号
    low_freq_signal = 0.5*np.sin(2*np.pi*0.5*t)  # 0.5Hz
    
    # 计算低频功率
    power = gan._calculate_low_freq_power(low_freq_signal)
    
    # 验证结果
    assert 0.1 <= power <= 1.0, "低频功率值超出预期范围"
    assert power > 0.3, "低频信号功率不足"

def test_spectral_constraint(gan):
    """测试频谱约束"""
    # 生成测试数据
    real_data = np.random.normal(0, 0.1, (2048, 2))
    
    # 计算约束损失
    loss = gan._apply_spectral_constraint(real_data)
    
    # 验证结果
    assert 0 <= loss <= 5.0, "频谱约束损失超出预期范围"
