import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class SecureDataPipeline:
    def __init__(self, config: dict = None):
        """安全数据处理管道初始化"""
        self.encryption_key = os.urandom(32)  # AES-256密钥
        
        # 默认配置
        self.config = {
            'retention_days': 30,
            'encryption': True
        }
        if config:
            self.config.update(config)

    def process(self, raw_data):
        """安全处理原始数据"""
        if self.config['encryption']:
            return self._encrypt_data(raw_data)
        return raw_data

    def _encrypt_data(self, data):
        """使用AES-GCM加密数据"""
        aesgcm = AESGCM(self.encryption_key)
        nonce = os.urandom(12)
        return nonce + aesgcm.encrypt(nonce, data.encode(), None)

    def _decrypt_data(self, encrypted_data):
        """解密数据"""
        aesgcm = AESGCM(self.encryption_key)
        nonce = encrypted_data[:12]
        return aesgcm.decrypt(nonce, encrypted_data[12:], None)
