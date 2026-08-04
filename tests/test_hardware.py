from drivers.dreem import DreemDriver
from core.hardware_manager import EEGHardwareManager

def test_dreem_integration():
    # 初始化
    manager = EEGHardwareManager()
    dreem = DreemDriver()
    
    # 注册驱动
    manager.register_driver('dreem2', dreem)
    
    # 获取数据
    data = manager.get_device_data('dreem2')
    assert 'timestamp' in data
    assert 'channels' in data
    print("测试通过，获取数据:", data)