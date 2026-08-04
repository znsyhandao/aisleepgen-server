import pytest
from src.aisleep.database.user_db import UserDatabase, UserProfile

def test_database_initialization():
    """测试数据库初始化"""
    db = UserDatabase(":memory:")
    cursor = db.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    assert cursor.fetchone() is not None, "Users table should be created"

def test_save_and_get_profile():
    """测试保存和获取用户配置"""
    db = UserDatabase(":memory:")
    profile = UserProfile(
        user_id="test_user",
        name="Test User",
        age=30,
        sleep_goals={"deep_sleep": 2.0},
        preferences={"preferred_music": "relax"}
    )
    db.save_profile(profile)
    retrieved_profile = db.get_profile("test_user")
    assert retrieved_profile == profile, "Retrieved profile should match the saved profile"

def test_get_intervention_history():
    """测试获取用户的干预历史记录"""
    db = UserDatabase(":memory:")
    history = db.get_intervention_history("test_user", days=7)
    assert isinstance(history, list), "Intervention history should be a list"
    assert len(history) == 0, "Default intervention history should be empty"

def test_check_connection():
    """测试数据库连接检查"""
    db = UserDatabase(":memory:")
    assert db.check_connection() is True, "Database connection should be active"