import pytest
import asyncio
from unittest.mock import MagicMock, patch
from aisleep.hardware.manager import HardwareManager



@pytest.fixture
def hardware_manager():
    return HardwareManager()

@pytest.mark.integration
@pytest.mark.asyncio

async def test_full_hardware_workflow():
    """测试完整硬件工作流程"""
    manager = HardwareManager()
    
    # 测试连接
    bci_result = await manager.connect_device("bci", {"serial_port": "COM3"})
    assert bci_result["status"] == "connected"
    
    # 测试数据获取
    data = await manager.get_latest_data()
    assert isinstance(data, dict)
    assert "bci" in data
    
    # 测试增强数据
    enhanced_data = manager.get_enhanced_data()
    assert "stress_index" in enhanced_data
    assert "sleep_score" in enhanced_data

async def test_connect_bci_success(hardware_manager):
    """测试成功连接BCI设备"""
    with patch('brainflow.board_shim.BoardShim.prepare_session') as mock_prepare:
        result = await hardware_manager.connect_device("bci", {"serial_port": "COM3"})
        assert result["status"] == "connected"
        assert hardware_manager.connections["bci"] is True

@pytest.mark.asyncio
async def test_connect_smartwatch_success(hardware_manager):
    """测试成功连接智能手表"""
    with patch('bleak.BleakClient.connect') as mock_connect:
        result = await hardware_manager.connect_device(
            "smartwatch", 
            {"device_address": "00:11:22:33:44:55"}
        )
        assert result["status"] == "connected"

@pytest.mark.asyncio
async def test_connect_unsupported_device(hardware_manager):
    """测试连接不支持的设备类型"""
    with pytest.raises(ValueError):
        await hardware_manager.connect_device("unsupported", {})

@pytest.mark.asyncio
async def test_get_bci_data(hardware_manager):
    """测试获取BCI数据"""
    with patch('brainflow.board_shim.BoardShim.get_current_board_data') as mock_get_data:
        mock_get_data.return_value = [0.1, 0.2, 0.3]
        hardware_manager.bci_client = MagicMock()
        data = hardware_manager._get_bci_data()
        assert "eeg" in data
        assert len(data["eeg"]) == 3

@pytest.mark.asyncio
async def test_get_wearable_data(hardware_manager):
    """测试获取穿戴设备数据"""
    with patch('bleak.BleakClient.read_gatt_char') as mock_read:
        mock_read.return_value = bytes([72])  # 72 bpm
        hardware_manager.wearable_client = MagicMock()
        data = await hardware_manager._get_wearable_data()
        assert data["heart_rate"] == 72

@pytest.mark.asyncio
async def test_get_latest_data(hardware_manager):
    """测试获取多设备数据"""
    with patch.object(hardware_manager, '_get_bci_data') as mock_bci, \
         patch.object(hardware_manager, '_get_wearable_data') as mock_wearable:
        mock_bci.return_value = {"eeg": [0.1, 0.2]}
        mock_wearable.return_value = {"heart_rate": 72}
        
        data = await hardware_manager.get_latest_data()
        assert "bci" in data
        assert "wearables" in data
