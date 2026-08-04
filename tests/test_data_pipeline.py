def test_role_based_access():
    pipeline = SecureDataPipeline()
    signals = {...}  # 测试用信号数据
    
    # 测试不同角色的访问权限
    research_data = pipeline.process(signals, user_role='researcher')
    assert 'raw_data' not in research_data
    
    doctor_data = pipeline.process(signals, user_role='doctor') 
    assert 'raw_data' not in doctor_data
    
    admin_data = pipeline.process(signals, user_role='admin')
    assert 'raw_data' in admin_data
