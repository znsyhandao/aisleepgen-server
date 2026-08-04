import pytest
from data_generator import BioSignalGenerator

def test_perg_generation():
    """测试PERG信号生成"""
    generator = BioSignalGenerator(age=30, bmi=22, stress_level=0.5)
    df = generator.generate_physiological_rhythm()
    
    # 验证输出数据结构
    assert 'PERG' in df.columns
    assert len(df['PERG']) > 200
    assert 0 < df['stress'].iloc[0] <= 1

def test_spectral_analysis():
    """测试频谱分析"""
    generator = BioSignalGenerator()
    signal = np.random.normal(0, 1, 1000)
    features = generator.analyze_spectral_features(signal)
    
    # 验证关键频段
    assert 'alpha_power' in features
    assert features['total_power'] > 0
