import unittest
from unittest.mock import MagicMock, patch
from user_interface import UserInterface
import queue

class TestMessageHandling(unittest.TestCase):
    def setUp(self):
        self.mock_engine = MagicMock()
        # 添加协议配置
        self.mock_engine.PROTOCOLS = {
            "放松模式": {}, 
            "深度睡眠": {}
        }
        self.ui = UserInterface(self.mock_engine)
        
    def test_status_message(self):
        """测试状态消息处理"""
        test_msg = {'type': 'status', 'text': "测试状态"}
        self.ui._process_message(test_msg)
        self.assertEqual(self.ui.status_label.cget("text"), "测试状态")
        
    def test_bio_feedback_message(self):
        """测试生物反馈消息处理"""
        test_data = {'stress': 0.75, 'fatigue': 0.6}
        test_msg = {'type': 'bio_feedback', 'data': test_data}
        self.ui._process_message(test_msg)
        
        for key, value in test_data.items():
            self.assertIn(f"{key}: {value:.2f}", self.ui.bio_labels[key].cget("text"))

    def test_protocol_change_message(self):
        """测试协议切换消息处理"""
        test_msg = {'type': 'protocol_change', 'protocol': "放松模式"}
        self.ui._process_message(test_msg)
        self.assertEqual(self.ui.current_protocol, "放松模式")

    def test_error_message(self):
        """测试错误消息处理"""
        test_msg = {'type': 'error', 'text': "测试错误"}
        self.ui._process_message(test_msg)
        self.assertEqual(self.ui.error_label.cget("text"), "测试错误")

    def test_audio_level_message(self):
        """测试音频电平消息处理"""
        test_msg = {'type': 'audio_level', 'level': 0.8}
        self.ui._process_message(test_msg)
        self.assertEqual(self.ui.audio_level, 0.8)

if __name__ == "__main__":
    unittest.main()
