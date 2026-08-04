def test_engine_safety():
    """测试安全监控系统"""
    engine = AudioTherapyEngine()
    test_signal = np.random.uniform(-1, 1, 2048)
    
    # 测试安全检查
    is_safe, _ = engine._check_audio_safety(test_signal)
    assert isinstance(is_safe, bool)

def test_realtime_processing():
    """测试实时处理流水线"""
    engine = AudioTherapyEngine()
    input_data = np.zeros(2048)
    output = engine.realtime_processing(input_data)
    
    assert len(output) == 2048
    assert np.max(np.abs(output)) <= 1.0  # 验证限幅
