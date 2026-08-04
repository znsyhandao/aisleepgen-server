import pytest
import numpy as np
import matplotlib.pyplot as plt
from data_generator import TopoMapVisualizer, DynamicSpectrumPlayer

@pytest.fixture
def visualizer():
    return TopoMapVisualizer()

@pytest.fixture
def player():
    return DynamicSpectrumPlayer()

def test_topo_map_visualization(visualizer):
    """测试地形图可视化"""
    # 生成测试信号
    test_signals = np.random.normal(0, 0.1, (2, 2048))
    
    # 生成图形
    fig = visualizer.plot(test_signals)
    
    # 验证结果
    assert fig is not None, "图形生成失败"
    assert len(fig.axes) == 3, "应包含3个子图"
    plt.close(fig)

def test_dynamic_spectrum(player):
    """测试动态频谱"""
    # 生成测试信号
    fs = player.sample_rate
    t = np.arange(0, 1, 1/fs)
    test_signal = np.sin(2*np.pi*10*t) + 0.5*np.sin(2*np.pi*20*t)
    
    # 生成动画
    anim = player.animate(test_signal)
    
    # 验证结果
    assert anim is not None, "动画生成失败"
    assert len(anim._fig.axes) == 2, "应包含2个子图"
    plt.close(anim._fig)

def test_low_freq_visualization(visualizer):
    """测试低频分析可视化"""
    # 生成测试信号
    test_signals = np.random.normal(0, 0.1, (3, 5000))
    
    # 生成图形
    fig = visualizer.plot_low_freq_analysis(test_signals)
    
    # 验证结果
    assert fig is not None, "图形生成失败"
    assert len(fig.axes) == 3, "应包含3个子图"
    plt.close(fig)
