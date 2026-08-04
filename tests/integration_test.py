# 修改导入路径为实际文件位置
from audio_therapy_engine import AudioTherapyEngine  # 而不是从data_generator导入
from user_interface import UserInterface
from voice_control import VoiceControl
import numpy as np

class TestIntegratedSystem:
    @classmethod
    def setup_class(cls):
        cls.engine = AudioTherapyEngine()
        cls.ui = UserInterface(cls.engine)
        cls.voice = VoiceControl(cls.engine, cls.ui)  # 传入UI实例
        
    def setUp(self):
        self.engine = AudioTherapyEngine()  # 确保创建的是真实实例
        
    def test_full_workflow(self):
        """测试从生物信号到音频输出的完整流程"""
        # 1. 模拟生物信号输入
        biosignal = np.random.normal(0, 0.5, 5000)

        # 2. 通过语音控制启动
        print(f"引擎运行前状态: {self.engine._running}")  # 调试信息
        self.voice.process_command("开始治疗")
        print(f"引擎运行后状态: {self.engine._running}")  # 调试信息
        print(f"UI运行状态: {self.ui.is_running}")  # 调试信息

        # 3. 验证引擎状态
        assert self.engine._running
        assert self.ui.is_running


