import pytest
from src.aisleep.interventions.music_therapy import MusicTherapy
from src.aisleep.database.user_db import UserDatabase, UserProfile

def test_music_therapy_with_user_database():
    """测试 MusicTherapy 与 UserDatabase 的集成"""
    # 初始化 UserDatabase
    db = UserDatabase(":memory:")  # 使用内存数据库进行测试
    profile = UserProfile(
        user_id="test_user",
        name="Test User",
        age=30,
        sleep_goals={"deep_sleep": 2.0},
        preferences={"preferred_music": "relax"}
    )
    db.save_profile(profile)

    # 初始化 MusicTherapy
    music_therapy = MusicTherapy(device_manager=None)

    # 从数据库获取用户配置
    user_profile = db.get_profile("test_user")
    assert user_profile is not None, "User profile should be retrieved from the database"
    assert user_profile.preferences['preferred_music'] == "relax", "User preference should match saved data"

    # 根据用户偏好和 EEG 数据选择音乐
    eeg_analysis = {'alpha': 0.5, 'theta': 0.6, 'beta': 0.4}
    selected_music = music_therapy._select_music(eeg_analysis, user_profile.preferences)
    assert selected_music in music_therapy.music_library['relax'], "Selected music should match user preference"