import numpy as np
from data_generator import AudioTherapyEngine
from user_interface import UserInterface

def test_user_interface():
    """测试用户界面系统"""
    # 1. 初始化引擎和界面
    engine = AudioTherapyEngine(sample_rate=44100, buffer_size=2048)
    ui = UserInterface(engine)
    
    # 2. 模拟生物反馈数据
    def mock_bio_feedback():
        while ui.is_running:
            # 生成随机但合理的生理数据
            stress = np.clip(np.random.normal(0.5, 0.2), 0, 1)
            fatigue = np.clip(np.random.normal(0.6, 0.15), 0, 1)
            sleep_stage = np.random.choice(["清醒", "浅睡", "深睡", "REM"])
            
            # 发送到界面
            ui.message_queue.put({
                'type': 'bio_feedback',
                'data': {
                    'stress': stress,
                    'fatigue': fatigue,
                    'sleep_stage': sleep_stage
                }
            })
            time.sleep(1)  # 每秒更新一次
    
    # 3. 启动模拟线程
    import threading
    import time
    
    bio_thread = threading.Thread(target=mock_bio_feedback, daemon=True)
    bio_thread.start()
    
    # 4. 运行主界面
    ui.run()

def test_voice_control():
    """测试语音控制系统"""
    engine = AudioTherapyEngine()
    voice = VoiceControl(engine)
    
    # 测试语音命令
    commands = [
        "开始治疗",
        "增大音量", 
        "切换协议 alpha_enhance",
        "减小音量",
        "停止治疗"
    ]
    
    for cmd in commands:
        print(f"执行命令: {cmd}")
        success = voice.process_command(cmd)
        print(f"结果: {'成功' if success else '失败'}")
        print(f"当前状态: 运行中={engine._running}, 协议={engine.current_protocol}, 音量={engine.user_prefs['volume']}")
        print("-"*40)

def test_mobile_app():
    """测试手机APP接口"""
    engine = AudioTherapyEngine()
    app = MobileAppInterface(engine)
    
    # 模拟连接
    print("尝试连接设备...")
    if app.connect("device_123"):
        print("连接成功")
        
        # 同步设置
        settings = {
            'volume': 0.8,
            'pitch_pref': 'high',
            'sound_type': 'white'
        }
        if app.sync_settings(settings):
            print("设置同步成功:", engine.user_prefs)
        
        # 获取状态
        status = app.get_status()
        print("当前状态:", status)
    else:
        print("连接失败")

if __name__ == "__main__":
    print("1. 测试图形界面")
    print("2. 测试语音控制") 
    print("3. 测试手机APP接口")
    choice = input("请选择测试模式(1-3): ")
    
    if choice == "1":
        test_user_interface()
    elif choice == "2":
        test_voice_control()
    elif choice == "3":
        test_mobile_app()
    else:
        print("无效选择")
