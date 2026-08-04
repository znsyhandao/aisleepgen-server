import unittest
from unittest.mock import MagicMock
from user_interface import UserInterface

class TestSystemState(unittest.TestCase):
    def setUp(self):
        self.mock_engine = MagicMock()
        # 添加协议配置
        self.mock_engine.PROTOCOLS = {
            "放松模式": {}, 
            "深度睡眠": {}
        }
        self.ui = UserInterface(self.mock_engine)
        
    def test_start_stop_state(self):
        """测试系统启动/停止状态切换"""
        # 初始状态
        self.assertFalse(self.ui.is_running)
        
        # 启动系统
        self.ui._on_start()
        self.assertTrue(self.ui.is_running)
        
        # 停止系统
        self.ui._on_stop()
        self.assertFalse(self.ui.is_running)

if __name__ == "__main__":
    unittest.main()
