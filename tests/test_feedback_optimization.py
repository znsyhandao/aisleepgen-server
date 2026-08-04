def test_parameter_optimization():
    manager = EEGHardwareManager()
    
    # 模拟差评反馈
    manager.record_feedback('dreem2', 2, "信号噪声大")
    
    # 验证参数优化
    params = manager.optimize_params_based_on_feedback('dreem2')
    assert params['filter_low'] > 1.0  # 验证已增强滤波
    assert params['notch_filter'] is True
