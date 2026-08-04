import unittest
from unittest.mock import MagicMock
from user_interface import UserInterface

class TestProtocolSelection(unittest.TestCase):
    def setUp(self):
        self.mock_engine = MagicMock()
        self.mock_engine.PROTOCOLS = {
            "放松模式": {}, 
            "深度睡眠": {},
            "快速恢复": {}
        }
        self.ui = UserInterface(self.mock_engine)
        
    def test_protocol_selection(self):
        """测试协议选择功能"""
        # 模拟选择不同协议
        for protocol in self.mock_engine.PROTOCOLS:
            self.ui.protocol_combo.set(protocol)
            selected = self.ui.protocol_combo.get()
            self.assertEqual(selected, protocol)
            
    def test_default_protocol(self):
        """测试默认协议选择"""
        self.assertEqual(self.ui.protocol_combo.get(), "放松模式")

if __name__ == "__main__":
    unittest.main()
