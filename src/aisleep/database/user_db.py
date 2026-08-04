from typing import Dict, Optional
import sqlite3
from dataclasses import dataclass
import json  # 添加导入

@dataclass
class UserProfile:
    user_id: str
    name: str
    age: int
    sleep_goals: Dict[str, float]
    preferences: Dict[str, str]

class UserDatabase:
    def __init__(self, db_path: str = "users.db"):
        self.conn = sqlite3.connect(db_path)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表结构"""
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            profile_data TEXT
        )
        """)

    def save_profile(self, profile: UserProfile):
        """保存用户配置"""
        self.conn.execute(
            "INSERT OR REPLACE INTO users VALUES (?, ?)",
            (profile.user_id, json.dumps(profile.__dict__))  # 使用 json.dumps 序列化
        )
        self.conn.commit()

    def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """获取用户配置"""
        cursor = self.conn.execute(
            "SELECT profile_data FROM users WHERE user_id = ?", 
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            data = json.loads(row[0])  # 使用 json.loads 反序列化
            return UserProfile(**data)
        return None

    def get_intervention_history(self, user_id: str, days: int) -> list:
        """获取用户的干预历史记录"""
        return []  # 返回一个空列表作为占位

    def check_connection(self) -> bool:
        """检查数据库连接状态"""
        try:
            self.conn.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False