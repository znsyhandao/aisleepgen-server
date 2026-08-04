def test_feedback_flow():
    manager = EEGHardwareManager()
    
    # 模拟用户反馈
    manager.record_feedback('dreem2', 4, "信号偶尔不稳定")
    manager.record_feedback('neurosky', 2, "佩戴不舒适")
    
    # 验证反馈收集
    feedbacks = manager.get_recent_feedback('dreem2')
    assert len(feedbacks) == 1
    assert feedbacks[0]['rating'] == 4
