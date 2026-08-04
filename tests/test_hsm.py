def test_hsm_integration():
    config = {
        'hsm_enabled': True,
        'hsm_lib_path': '/usr/lib/cloudhsm/libcloudhsm_pkcs11.so',
        'hsm_slot': 1,
        'key_id': 'aes_key_01'
    }
    pipeline = SecureDataPipeline(config)
    assert len(pipeline.encryption_key) == 32  # 验证密钥长度
