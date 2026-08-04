import pytest
from scripts.credential_rotator import *
from unittest.mock import patch, MagicMock

def test_credential_rotation(monkeypatch):
    # 模拟环境变量
    monkeypatch.setenv('IAM_ADMIN_AK', 'test_ak')
    monkeypatch.setenv('IAM_ADMIN_SK', 'test_sk')
    
    # 测试密钥轮换流程
    with pytest.raises(Exception):
        rotate_credentials()  # 实际项目应使用mock替换真实API调用



@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv('IAM_ADMIN_AK', 'test_ak')
    monkeypatch.setenv('IAM_ADMIN_SK', 'test_sk')
    monkeypatch.setenv('OBS_ACCESS_KEY', 'test_obs_ak')
    monkeypatch.setenv('OBS_SECRET_KEY', 'test_obs_sk')

def test_get_temp_credentials(mock_env):
    with patch('huaweicloudsdkiam.v3.IamClient.create_temporary_authentication') as mock_create:
        mock_create.return_value = MagicMock()
        result = get_temp_credentials()
        assert result is not None

def test_credential_rotation_flow(mock_env):
    with patch('huaweicloudsdkiam.v3.IamClient.create_credentials') as mock_create:
        mock_create.return_value = MagicMock(ak='new_ak', sk='new_sk')
        new_creds = rotate_credentials()
        assert new_creds.ak == 'new_ak'
        assert new_creds.sk == 'new_sk'
