import numpy as np
import json
from aisleep.biofeedback import BioFeedbackAnalyzer

def test_biofeedback_analysis():
    """BioFeedbackAnalyzer 功能测试"""
    # 1. 准备模拟输入信号
    signals = {
        'eeg': np.random.normal(0, 0.5, 8500),  # 5秒EEG信号(1700Hz采样率)
        'hrv': np.random.normal(800, 50, 300),  # 5分钟HRV数据(1Hz采样率)
        'respiration': np.random.normal(0, 0.3, 8500),  # 5秒呼吸信号
        'reference_noise': np.random.normal(0, 0.1, 8500)  # 参考噪声
    }

    # 2. 初始化分析器
    analyzer = BioFeedbackAnalyzer(sample_rate=1700)

    # 3. 执行分析
    results = analyzer.analyze(signals)

    # 验证基本结果结构
    assert 'modern' in results
    assert 'traditional' in results
    assert 'clinical' in results
    
    # 新增详细验证
    # 1. 验证临床评估内容
    assert 'risks' in results['clinical']
    assert 'recommendations' in results['clinical']
    
    # 2. 验证传统方法对比
    assert 'hrv_analysis' in results['traditional'] or 'time_domain' in results['traditional']
    
    # 3. 验证频带能量比
    # 增强频带验证
    bands = results['band_ratios']
    assert 0 < bands['alpha'] < 0.3  # α波合理范围
    assert bands['delta'] + bands['theta'] > 0.3  # 慢波睡眠特征
    assert np.isclose(sum(bands.values()), 1.0, atol=0.1)  # 能量守恒
    
    assert set(bands.keys()) == {'delta', 'theta', 'alpha', 'beta', 'gamma'}
    assert 0.9 < sum(bands.values()) < 1.1  # 能量总和约等于1
    
    # 4. 打印结果用于调试
    print("\n=== 测试结果 ===")
    print(f"压力指数: {results['modern']['stress']:.2f}")
    print(f"频带能量分布: {results['band_ratios']}")

    # 5. 生成测试报告
    report = analyzer.generate_report(results)
    assert 'summary' in report

def test_clinical_consistency():
    """验证临床评估与传统/现代方法的一致性"""
    analyzer = BioFeedbackAnalyzer()
    results = analyzer.analyze(test_signals)
    
    # 当传统和现代方法都检测到高压时，临床评估应有对应风险
    if (results['modern']['stress'] > 0.7 and 
        results['traditional']['stress_index'] > 0.7):
        assert any('高压' in risk for risk in results['clinical']['risks'])

    # 增强传统方法验证
    traditional = results['traditional']
    assert 'hrv_time_domain' in traditional  # 时域指标
    assert 'hrv_frequency_domain' in traditional  # 频域指标
    assert abs(traditional['hrv_rmssd'] - traditional['hrv_sdnn']) < 50  # 合理性检查

    # 增强临床评估验证
    assert isinstance(results['clinical']['risks'], list)
    assert isinstance(results['clinical']['recommendations'], list)
    assert 'severity' in results['clinical']  # 新增严重程度评估

    # 验证临床规则应用
    if results['modern']['stress'] > 0.7:
        assert '高压风险' in results['clinical']['risks']

def test_pathological_patterns():
    """病理模式专项测试"""
    # 1. 准备包含癫痫特征的EEG信号
    epileptic_eeg = np.random.normal(0, 0.3, 8500)
    spike_positions = np.random.randint(0, 8500, 5)
    epileptic_eeg[spike_positions] += 2.0  # 添加癫痫尖波
    
    signals = {
        'eeg': epileptic_eeg,
        'hrv': np.random.normal(800, 50, 300),
        'respiration': np.random.normal(0, 0.3, 8500),
        'reference_noise': np.random.normal(0, 0.1, 8500)
    }
    
    # 2. 执行分析并验证
    analyzer = BioFeedbackAnalyzer(sample_rate=1700)
    results = analyzer.analyze(signals)
    
    # 验证能检测到异常放电
    assert results['clinical']['risks'] != []
    assert '异常脑电活动' in str(results['clinical']['risks'])

def test_demographic_baselines():
    """不同人口统计基线验证"""
    test_cases = [
        {'age': 20, 'gender': 'male', 'expected_alpha': (0.15, 0.25)},
        {'age': 65, 'gender': 'female', 'expected_alpha': (0.10, 0.20)},
    ]
    
    for case in test_cases:
        # 初始化带用户档案的分析器
        analyzer = BioFeedbackAnalyzer(
            sample_rate=1700,
            user_profile={'age': case['age'], 'gender': case['gender']}
        )
        
        # 使用标准测试信号
        results = analyzer.analyze(test_signals)
        alpha = results['band_ratios']['alpha']
        
        # 验证基线范围
        assert case['expected_alpha'][0] < alpha < case['expected_alpha'][1], \
            f"{case['gender']} {case['age']}岁α波异常: {alpha}"

def test_report_generation():
    """自动化报告生成测试"""
    analyzer = BioFeedbackAnalyzer(sample_rate=1700)
    results = analyzer.analyze(test_signals)
    
    # 1. 生成报告
    report = analyzer.generate_report(results)
    
    # 2. 验证报告结构
    required_sections = ['summary', 'analysis', 'recommendations', 'metadata']
    for section in required_sections:
        assert section in report
    
    # 3. 验证内容一致性
    assert report['summary']['stress'] == results['modern']['stress']
    assert len(report['recommendations']) > 0
    
    # 4. 验证JSON格式
    try:
        json.dumps(report)  # 测试可序列化
    except TypeError:
        pytest.fail("报告包含不可序列化的数据")

# ... 已有代码 ...

def test_gdpr_compliance():
    """GDPR合规性测试"""
    raw_data = {
        'user_id': 'patient_123',
        'eeg': np.random.normal(0, 0.5, 100),
        'age': 35,
        'metadata': {'name': '张三', 'address': '北京'}
    }
    
    anonymizer = GDPRAnonymizer()
    
    # 假名化测试
    pseudonymized = anonymizer.pseudonymize(raw_data)
    assert pseudonymized['user_id'] != raw_data['user_id']
    assert 'name' not in pseudonymized['metadata']
    
    # 匿名化测试
    anonymized = anonymizer.anonymize(raw_data)
    assert anonymized['age_group'] == '21-40'
    assert anonymized['gender'] == 'unknown'
    
    # 可逆性验证
    try:
        Fernet(anonymizer.cipher_key).decrypt(pseudonymized['eeg'])
    except:
        pytest.fail("加密解密失败")



if __name__ == "__main__":
    test_biofeedback_analysis()
