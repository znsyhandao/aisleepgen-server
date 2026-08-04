import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.aisleep.hardware.manager import HardwareManager
import asyncio

"""
测试执行说明：
1. 常规测试: pytest tests/hardware/
2. 性能测试: pytest tests/hardware/ -m "not integration"
3. 集成测试: pytest tests/hardware/ --integration
4. 模拟测试: pytest tests/hardware/ -m simulation

测试数据规范参考：
- 心率正常范围: 60-100 bpm
- HRV正常范围: 50-200 ms
- 皮电反应: 5-25 μS
- EEG频谱: 各波段总和应>0
"""


@pytest.mark.asyncio
async def test_bci_connection():
    """Test BCI device connection"""
    manager = HardwareManager()
    with patch('brainflow.board_shim.BoardShim.prepare_session'):
        result = await manager.connect_device("bci", {"serial_port": "COM3"})
        assert result["status"] == "connected"

@pytest.mark.asyncio
async def test_wearable_connection():
    """Test wearable device connection"""
    manager = HardwareManager()
    
    with patch('bleak.BleakClient.connect'):
        result = await manager.connect_device(
            "smartwatch", 
            {"device_address": "00:11:22:33:44:55"}
        )
        assert result["status"] == "connected"
@pytest.mark.asyncio
async def test_stress_calculation():
    """测试压力指数计算"""
    manager = HardwareManager()
    test_data = {
        "wearables": {"heart_rate": 85, "hrv": 150, "galvanic_skin": 15},
        "bci": {"attention": 0.6}
    }
    stress = manager._calculate_stress_index(test_data)
    assert 0 <= stress <= 1

@pytest.mark.asyncio 
async def test_sleep_score_prediction():
    """测试睡眠评分预测"""
    manager = HardwareManager()
    test_data = {
        "wearables": {
            "hr_variance": 2.5, 
            "breath_rate": 14,
            "movement": 3
        },
        "bci": {
            "eeg_spectrum": {
                "delta": 30,
                "theta": 20,
                "alpha": 10,
                "beta": 5
            }
        }
    }
    score = manager._predict_sleep_score(test_data)
    assert 0 <= score <= 100


@pytest.mark.asyncio
async def test_stress_calculation_boundary():
    """测试压力计算的边界情况"""
    manager = HardwareManager()
    # 极低生理指标
    low_data = {
        "wearables": {"heart_rate": 50, "hrv": 250, "galvanic_skin": 5},
        "bci": {"attention": 0.9}
    }
    # 极高生理指标
    high_data = {
        "wearables": {"heart_rate": 120, "hrv": 50, "galvanic_skin": 25},
        "bci": {"attention": 0.2}
    }
    assert manager._calculate_stress_index(low_data) < 0.3
    assert manager._calculate_stress_index(high_data) > 0.7


@pytest.mark.asyncio
async def test_invalid_data_handling():
    """测试异常数据输入处理"""
    manager = HardwareManager()
    # 缺失关键字段
    missing_data = {"wearables": {}}
    # 错误数据类型
    wrong_type_data = {"wearables": {"heart_rate": "invalid"}}
    
    assert 0 <= manager._calculate_stress_index(missing_data) <= 1
    assert 0 <= manager._predict_sleep_score(wrong_type_data) <= 100


@pytest.mark.asyncio
async def test_performance():
    """确保算法在50ms内完成计算"""
    manager = HardwareManager()
    test_data = {
        "wearables": {
            "heart_rate": 75,
            "hrv": 180,
            "galvanic_skin": 12,
            "hr_variance": 2.0,
            "breath_rate": 15,
            "movement": 2
        },
        "bci": {
            "attention": 0.7,
            "eeg_spectrum": {
                "delta": 25,
                "theta": 15,
                "alpha": 8,
                "beta": 4
            }
        }
    }
    start = time.perf_counter()  # 使用更高精度的计时器
    start = time.time()
    manager._calculate_stress_index(test_data)
    manager._predict_sleep_score(test_data)
    elapsed = (time.time() - start) * 1000
    
    assert elapsed < 50  # 毫秒


@pytest.mark.integration
@pytest.mark.asyncio 
async def test_real_device_integration():
    """实际硬件集成测试"""
    # 需要真实设备连接
    manager = HardwareManager()
    # ... 实际设备测试代码



@pytest.mark.asyncio
async def test_algorithm_consistency():
    """验证算法输出的稳定性"""
    manager = HardwareManager()
    test_data = {...}  # 复用性能测试的数据
    
    # 连续运行10次验证结果波动范围
    results = [
        manager._calculate_stress_index(test_data)
        for _ in range(10)
    ]
    assert max(results) - min(results) < 0.01  # 波动小于1%



@pytest.mark.simulation
@pytest.mark.asyncio
async def test_simulated_device():
    """模拟设备环境测试"""
    with patch('brainflow.board_shim.BoardShim.get_current_board_data') as mock_bci, \
         patch('bleak.BleakClient.read_gatt_char') as mock_ble:
        
        mock_bci.return_value = [0.1, 0.2, 0.3]
        mock_ble.return_value = bytes([72])
        
        manager = HardwareManager()
        await manager.connect_device("bci", {"serial_port": "COM3"})
        await manager.connect_device("smartwatch", {"device_address": "00:11:22:33:44:55"})
        
        data = await manager.get_latest_data()
        assert data["bci"]["eeg"] == [0.1, 0.2, 0.3]
        assert data["wearables"]["heart_rate"] == 72

@pytest.mark.asyncio
async def test_wearable_data_reading():
    """测试穿戴设备数据读取和解析"""
    manager = HardwareManager()
    manager.wearable_client = AsyncMock()
    
    # 设置模拟返回值
    manager.wearable_client.read_gatt_char = AsyncMock(side_effect=[
        b'\x48',  # 心率: 72
        b'\x62'   # 血氧: 98
    ])
    
    # 只测试核心数据解析逻辑
    data = await manager._read_wearable_data()
    assert data["heart_rate"] == 72
    assert data["blood_oxygen"] == 98



class HardwareManager:
    # ... existing code ...

    async def _read_wearable_data(self):
        """Async method to read data from wearable device"""
        if not hasattr(self, 'wearable_client') or not self.wearable_client:
            return None
            
        try:
            hr = await self.wearable_client.read_gatt_char(self.HEART_RATE_UUID)
            spo2 = await self.wearable_client.read_gatt_char(self.BLOOD_OXYGEN_UUID)
            return {
                'heart_rate': int.from_bytes(hr, 'little'),
                'blood_oxygen': int.from_bytes(spo2, 'little')
            }
        except Exception as e:
            logging.error(f"Error reading wearable data: {e}")
            return None

    async def get_latest_data(self):
        """Get latest data from all connected devices"""
        bci_data = await self._read_bci_data() if hasattr(self, 'bci_connected') and self.bci_connected else None
        wearable_data = await self._read_wearable_data() if hasattr(self, 'wearable_connected') and self.wearable_connected else None
        
        return {
            'bci': bci_data,
            'wearables': wearable_data
        }
    def _calculate_stress_index(self, data):
        """计算压力指数"""
        # ... 实现压力计算逻辑
        return 0.5

    def _predict_sleep_score(self, data):
        """预测睡眠评分"""
        # ... 实现睡眠评分逻辑
        return 80