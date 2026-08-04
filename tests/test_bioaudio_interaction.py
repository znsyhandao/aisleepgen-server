def test_biofeedback_to_audio():
    """测试生物反馈如何影响音频生成"""
    bio_analyzer = BioFeedbackAnalyzer()
    audio_engine = AudioTherapyEngine()
    
    # 模拟不同压力水平
    for stress in [0.2, 0.5, 0.8]:
        mock_signal = {'eeg': np.random.normal(0, stress, 1000)}
        bio_data = bio_analyzer.analyze(mock_signal)
        
        # 验证音频参数调整
        therapy_sound = audio_engine.sound_generator.generate_therapy_sound(
            stress_level=bio_data['stress']
        )
        assert therapy_sound.frequency_range[0] > 20  # 最低频率限制
