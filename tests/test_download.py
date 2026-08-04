# 创建测试脚本 test_download.py
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from auto_data_fetcher import AutoDataFetcher, GlobalConfig, DataConfig
import logging



logging.basicConfig(level=logging.INFO)
config = GlobalConfig(data=DataConfig())
fetcher = AutoDataFetcher(config, logging.getLogger("test"))

# 手动下载一个测试文件
fetcher.manual_download(
    url="https://www.physionet.org/files/sleep-edfx/1.0.0/sleep-cassette/SC4001E0-PSG.edf",
    name="SC4001"
)