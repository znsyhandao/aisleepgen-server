def test_biofeedback_analysis():
    """生物反馈分析测试函数"""
    # 模拟输入信号
    signals = {
        'eeg': np.random.normal(0, 1, 1700),
        'hrv': np.random.normal(50, 5, 1700),
        'respiration': np.random.normal(0.3, 0.1, 1700),
        'reference_noise': np.random.normal(0, 0.5, 1700)
    }
    
    # 执行分析流程
    analyzer = BioFeedbackAnalyzer()
    results = analyzer.analyze(signals)
    report = analyzer.generate_report(results)
    
    print("分析结果:", results)
    print("临床报告:", report)
