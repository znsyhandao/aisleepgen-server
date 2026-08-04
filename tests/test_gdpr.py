def test_pseudonymization():
    original = {'user_id': 'user123', 'phone': '13800138000'}
    anonymized = GDPRAnonymizer().pseudonymize(original)
    assert original['user_id'] != anonymized['user_id']
    assert len(anonymized['phone']) == 13  # 验证假电话号码格式
