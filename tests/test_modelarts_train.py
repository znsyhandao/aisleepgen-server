import pytest
import time
from src.aisleep.modelarts_utils import ModelArtsTrainer, generate_train_config
from settings import settings
import sys
import matplotlib
import numpy as np

# 环境验证
def pytest_configure(config):
    print("\n=== 测试环境验证 ===")
    print(f"Python版本: {sys.version}")
    print(f"Matplotlib版本: {matplotlib.__version__}")
    print(f"NumPy版本: {np.__version__}")
    print(f"华为云OBS Bucket: {settings.obs_bucket}")
    print("==================\n")

@pytest.fixture
def trainer():
    return ModelArtsTrainer()

@pytest.fixture
def test_config():
    return generate_train_config(
        model_name="test_model",
        data_path="obs://aisleepgenbucket/test_data",
        epochs=5,
        batch_size=32
    )

def test_credentials_validation():
    """验证华为云凭证有效性"""
    assert settings.obs_access_key and settings.obs_secret_key, "缺少OBS凭证"
    assert settings.HUAWEI_PROJECT_ID, "缺少项目ID"
    assert settings.modelarts_api_key, "缺少ModelArts API Key"

def test_resource_availability():
    """验证测试资源是否可用"""
    assert settings.modelarts_endpoint, "缺少ModelArts端点配置"
    assert settings.train_instance_type == "modelarts.vm.cpu.2u", "实例类型不匹配"
    assert settings.train_code_dir, "缺少训练代码目录配置"

def test_train_job_creation(trainer, test_config):
    """测试训练任务创建"""
    job_id = trainer.create_train_job(test_config)
    assert job_id is not None
    
    # 验证任务状态
    status = trainer.get_job_status(job_id)
    assert status['status'] in ['RUNNING', 'WAITING', 'COMPLETED']
    assert status['progress'] >= 0

def test_job_monitoring(trainer, test_config):
    """测试训练监控功能"""
    job_id = trainer.create_train_job(test_config)
    
    # 等待任务启动
    time.sleep(30)
    
    # 获取指标
    metrics = trainer.get_job_metrics(job_id)
    assert metrics is not None
    assert 'cpu_usage' in metrics
    
    # 测试停止功能
    assert trainer.stop_job(job_id)
    final_status = trainer.get_job_status(job_id)
    assert final_status['status'] in ['STOPPED', 'FAILED']

def test_invalid_config_handling(trainer):
    """测试无效配置处理"""
    with pytest.raises(ValueError):
        invalid_config = {"job_name": "test"}
        trainer.create_train_job(invalid_config)