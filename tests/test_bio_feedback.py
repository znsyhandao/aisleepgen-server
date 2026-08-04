import random
import unittest
from unittest.mock import MagicMock
from user_interface import UserInterface
import matplotlib
matplotlib.use('Agg')  # 设置非交互式后端，避免测试时弹出窗口


class TestBioFeedback(unittest.TestCase):
    def setUp(self):
        # 创建模拟引擎
        self.mock_engine = MagicMock()
        self.mock_engine.PROTOCOLS = {"default": {}}
        
        # 初始化UI
        self.ui = UserInterface(self.mock_engine)
        
    def test_bio_feedback_update(self):
        """测试生物反馈数据更新"""
        test_data = {
            'stress': random.uniform(0, 1),
            'fatigue': random.uniform(0, 1)
        }
        
        # 模拟消息处理
        msg = {
            'type': 'bio_feedback',
            'data': test_data
        }
        self.ui._process_message(msg)
        
        # 验证标签更新
        for key in test_data:
            self.assertIn(f"{key}: {test_data[key]:.2f}", 
                         self.ui.bio_labels[key].cget("text"))
        
        # 验证图表更新（通过检查图表对象是否存在）
        self.assertIsNotNone(self.ui.bio_ax.lines if hasattr(self.ui.bio_ax, 'lines') 
                            else self.ui.bio_ax.patches)

    def test_invalid_bio_data(self):
        """测试无效生物数据"""
        invalid_data = {'invalid_metric': 0.5}
        msg = {
            'type': 'bio_feedback',
            'data': invalid_data
        }
        
        # 应不抛出异常
        self.ui._process_message(msg)

if __name__ == "__main__":
    # 可视化测试
    import tkinter as tk
    from dummy_engine import DummyTherapyEngine
    
    root = tk.Tk()
    engine = DummyTherapyEngine()
    ui = UserInterface(engine)
    
    def update_test():
        data = {
            'stress': random.random(),
            'fatigue': random.random()
        }
        ui.message_queue.put({
            'type': 'bio_feedback',
            'data': data
        })
        root.after(1000, update_test)
    
    root.after(1000, update_test)
    ui.run()
