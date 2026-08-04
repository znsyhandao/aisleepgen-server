import pytest
from src.aisleep.interventions.music_therapy import MusicTherapy

def test_analyze_eeg_empty_data():
    """测试空 EEG 数据的分析"""
    music_therapy = MusicTherapy(device_manager=None)
    result = music_therapy._analyze_eeg([])
    assert result == {'alpha': 0, 'theta': 0, 'beta': 0}, "Empty EEG data should return zeroed features"

def test_analyze_eeg_normal_data():
    """测试正常 EEG 数据的分析"""
    music_therapy = MusicTherapy(device_manager=None)
    eeg_data = [0.1, 0.2, 0.3, 0.4, 0.5]
    result = music_therapy._analyze_eeg(eeg_data)
    assert result['alpha'] >= 0, "Alpha value should be non-negative"
    assert result['theta'] >= 0, "Theta value should be non-negative"
    assert result['beta'] >= 0, "Beta value should be non-negative"

def test_analyze_eeg_large_data():
    """测试大数据量 EEG 数据的分析"""
    music_therapy = MusicTherapy(device_manager=None)
    eeg_data = [0.1] * 1024  # 模拟 1024 个采样点的 EEG 数据
    result = music_therapy._analyze_eeg(eeg_data)
    assert result['alpha'] >= 0, "Alpha value should be non-negative"
    assert result['theta'] >= 0, "Theta value should be non-negative"
    assert result['beta'] >= 0, "Beta value should be non-negative"

def test_adjust_music_preferences():
    """测试根据用户反馈调整音乐选择逻辑"""
    music_therapy = MusicTherapy(device_manager=None)
    feedback = {'preferred_music': 'relax'}
    music_therapy.adjust_music_preferences(feedback)
    assert 'user_favorite_track' in music_therapy.music_library['relax']

def test_update_music_during_playback():
    """测试实时调整音乐类型"""
    music_therapy = MusicTherapy(device_manager=None)
    eeg_analysis = {'alpha': 0.7, 'theta': 0.8, 'beta': 0.3}
    music_therapy.update_music_during_playback(eeg_analysis)
    # 检查是否正确切换音乐类型（示例中打印输出）

def test_select_music_based_on_eeg():
    """测试根据 EEG 分析结果选择音乐"""
    music_therapy = MusicTherapy(device_manager=None)
    eeg_analysis = {'alpha': 0.7, 'theta': 0.8, 'beta': 0.3}
    selected_music = music_therapy._select_music(eeg_analysis)
    assert selected_music in music_therapy.music_library['sleep']
def test_analyze_eeg_with_valid_data():
    """测试正常 EEG 数据的分析"""
    music_therapy = MusicTherapy(device_manager=None)
    eeg_data = [0.1, 0.2, 0.3, 0.4, 0.5]
    result = music_therapy._analyze_eeg(eeg_data)
    assert result['alpha'] >= 0, "Alpha value should be non-negative"
    assert result['theta'] >= 0, "Theta value should be non-negative"
    assert result['beta'] >= 0, "Beta value should be non-negative"
def test_music_therapy_with_empty_user_profile():
    """测试空用户配置的行为"""
    db = UserDatabase(":memory:")
    music_therapy = MusicTherapy(device_manager=None)

    # 模拟空用户配置
    user_profile = None
    eeg_analysis = {'alpha': 0.5, 'theta': 0.6, 'beta': 0.4}
    selected_music = music_therapy._select_music(eeg_analysis, user_profile)
    assert selected_music in music_therapy.music_library['focus'], "Default music should be selected for empty profile"

    
def test_bulk_user_profiles():
    """测试批量用户配置的性能"""
    db = UserDatabase(":memory:")  # 使用内存数据库进行测试
    for i in range(1000):
        profile = UserProfile(
            user_id=f"user_{i}",
            name=f"User {i}",
            age=30 + i % 10,
            sleep_goals={"deep_sleep": 2.0 + i % 5},
            preferences={"preferred_music": "relax" if i % 2 == 0 else "focus"}
        )
        db.save_profile(profile)
    assert db.get_profile("user_999").name == "User 999"