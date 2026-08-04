import pytest  # Add this at the top
from unittest.mock import patch
from aisleep.monitoring import PerformanceMonitor


@pytest.mark.stress
def test_extreme_latency_handling():
    """测试极端网络延迟下的音频同步"""
    guide = MeditationGuide()
    
    # 模拟不同延迟场景
    latency_cases = [10, 500, 2000]  # 毫秒
    for latency in latency_cases:
        # 强制设置延迟
        guide.network_latency = latency / 1000  
        
        # 验证同步机制
        sync_result = guide.sync_audio_with_visual()
        assert sync_result['drift'] < 100  # 确保音画同步误差<100ms
