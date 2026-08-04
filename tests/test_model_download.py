import pytest
from src.aisleep.obs_utils import OBSHelper

@pytest.fixture
def downloader():
    return OBSHelper()

def test_model_download(downloader):
    test_file = "DeepSeek-R1-Distill-Qwen-1.5B/model.bin"  # 测试模型路径
    try:
        local_path = downloader.download_model(test_file)
        assert os.path.exists(local_path)
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)
