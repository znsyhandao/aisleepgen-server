from data_generator import VirtualSubjectGAN, PERGDataLoader  # 添加PERGDataLoader导入
import pytest
import os
import pandas as pd  # 添加这行导入
def test_perg_data_loading():
    """测试PERG数据加载功能"""
    # 使用PERGDataLoader替代VirtualSubjectGAN
    loader = PERGDataLoader()
    test_file = os.path.join(
        r"D:\AISleepGen\data",
        "a-comprehensive-dataset-of-pattern-electroretinograms-for-ocular-electrophysiology-research-the-perg-ioba-dataset-1.0.0",
        "csv",
        "0001.csv"
    )

    if not os.path.exists(test_file):
        pytest.skip(f"测试数据文件不存在: {test_file}")

    print(f"尝试加载文件: {test_file}")
    print(f"文件存在: {os.path.exists(test_file)}")

    # 使用PERGDataLoader加载数据
    data = loader.load_csv(test_file)
    assert data is not None
    assert not data.empty

    # 验证数据基本属性
    assert data.shape[0] >= 255
    assert isinstance(data, pd.DataFrame)
    assert {'RE_1', 'LE_1'}.issubset(data.columns)