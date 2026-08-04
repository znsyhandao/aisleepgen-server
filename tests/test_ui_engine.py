def test_ui_protocol_selection():
    """测试协议选择功能"""
    engine = AudioTherapyEngine()
    ui = UserInterface(engine)
    
    # 模拟用户选择协议
    test_protocol = 'alpha_enhance'
    ui.protocol_combo.set(test_protocol)
    ui.start_therapy()
    
    assert engine.current_protocol == test_protocol
    assert '_processing_thread' in dir(engine)
