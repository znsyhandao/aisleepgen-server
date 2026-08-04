import pytest
from data_generator import PERGDataLoader, AFDataLoader

@pytest.fixture
def perg_loader():
    return PERGDataLoader()

@pytest.fixture 
def af_loader():
    return AFDataLoader()

def test_perg_data_integrity(perg_loader):
    """测试PERG数据完整性"""
    # 1. 验证文件完整性
    assert perg_loader.verify_data_integrity(), "PERG数据完整性验证失败"
    
    # 2. 测试文件数量
    assert len(perg_loader.csv_files) >= 10, "CSV文件数量不足"
    
    # 3. 测试样本加载
    sample = perg_loader.load_csv(1)
    assert sample is not None, "样本加载失败"
    assert 'RE_1' in sample.columns and 'LE_1' in sample.columns, "信号列缺失"
    
    # 4. 测试数据统计特征
    stats = sample.describe()
    assert stats.loc['mean'].abs().max() < 10, "信号均值异常"
    
    # 修改点：只检查信号列的标准差，排除时间列
    signal_stats = stats[['RE_1', 'LE_1']]
    assert signal_stats.loc['std'].min() > 0.1, "信号标准差过小"

def test_af_data_integrity(af_loader):
    """测试AF数据完整性"""
    # 1. 验证文件完整性
    assert af_loader.verify_data_integrity(), "AF数据完整性验证失败"
    
    # 2. 测试数据加载
    data = af_loader.load_data('learning')
    assert data.shape[0] > 1000, "数据量不足"
    assert data.shape[1] == 2, "数据维度异常"
    
    # 3. 测试数据范围
    assert data.min() >= -5 and data.max() <= 5, "数据幅度异常"
