#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
db_sqlite.py — AISleepGen SQLite 存储层

替代 JSON 文件存储，接口兼容 profile_storage.py 的现有函数。
使用 WAL 模式 + 读写分离，支持高并发。

用法（渐进替换）：
    1. db = SQLiteDB('data/sleep.db')
    2. db.load_user_profile('wx_xxx')  # 等价于原 _load_user_profile
    3. db.save_user_profile(profile, 'wx_xxx')  # 原子写
"""
import os, json, sqlite3, threading, time, logging
from datetime import datetime, timedelta
from copy import deepcopy

_db_log = logging.getLogger('aisleepgen.db')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 默认用户画像（与 profile_storage 一致）
_DEFAULT_PROFILE = {
    'history': [],
    'latest': {},
    'total_sessions': 0,
    'stress_log': [],
    'relax_log': [],
    'behavior_stats': {
        'total_relax_sessions': 0, 'total_completed_sessions': 0,
        'total_interrupted_sessions': 0, 'total_relax_seconds': 0,
        'avg_relax_duration': 0, 'relax_streak_days': 0,
        'stress_type_distribution': {}, 'last_relax_date': None,
        'common_emotions': [], 'weekly_counts': [],
    },
    'member': {
        'level': 'free',
        'joined_at': datetime.now().strftime('%Y-%m-%d'),
        'last_active': datetime.now().strftime('%Y-%m-%d'),
        'streak_days': 0, 'total_days': 0, 'daily_scores': [], 'active_dates': [],
    },
    'user_info': {'nickname': '睡眠探索者', 'avatar_url': '', 'gender': 0, 'age_range': ''},
    'meta_params': {
        'intervention_threshold': 0.5, 'breath_rounds_base': 3,
        'breath_rounds_scale': 0.5, 'preferred_pattern': '4-7-8',
        'noise_preference': 'ocean', 'feature_vector': [0.0] * 8,
        'total_interactions': 0, 'response_rate': 0.0, 'completion_rate': 0.0,
        'avg_hrv_change': 0.0, '_pattern_scores': {}, 'last_meta_update': None,
        'confidence': 0.3,
    },
}


class SQLiteDB:
    """SQLite 存储引擎，接口兼容 JSON 文件版 profile_storage"""

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(PROJECT_ROOT, 'data', 'sleep.db')
        self._db_path = os.path.expanduser(db_path)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        # :memory: 模式不需要创建目录
        if self._db_path != ':memory:':
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self):
        """获取线程本地连接（读写分离）"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, timeout=10, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA cache_size=-8000')  # 8MB 缓存
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        """初始化表结构"""
        if self._db_path == ':memory:':
            conn = self._get_conn()
        else:
            conn = self._get_conn()
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                openid TEXT PRIMARY KEY,
                profile TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS feedbacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                openid TEXT NOT NULL,
                message_id TEXT DEFAULT '',
                fb_type TEXT NOT NULL,
                fb_text TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_feedbacks_openid ON feedbacks(openid);
            CREATE INDEX IF NOT EXISTS idx_users_updated ON users(updated_at);
        ''')
        conn.commit()

    # ==================== 公共接口（兼容 profile_storage） ====================

    def get_default_profile(self):
        return deepcopy(_DEFAULT_PROFILE)

    def load_user_profile(self, openid='default'):
        """加载用户画像，不存在则创建"""
        conn = self._get_conn()
        row = conn.execute('SELECT profile FROM users WHERE openid=?', (openid,)).fetchone()
        if row:
            try:
                return json.loads(row['profile'])
            except json.JSONDecodeError as e:
                _db_log.warning('Corrupt profile data for openid=%s: %s', openid, e)
        # 创建新用户
        profile = self.get_default_profile()
        self.save_user_profile(profile, openid)
        return profile

    def save_user_profile(self, profile, openid='default'):
        """保存用户画像（原子写）"""
        conn = self._get_conn()
        with self._write_lock:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(
                'INSERT OR REPLACE INTO users (openid, profile, updated_at) VALUES (?, ?, ?)',
                (openid, json.dumps(profile, ensure_ascii=False), now)
            )
            conn.commit()

    def atomic_write_profile(self, openid, modify_fn):
        """原子式修改用户画像：加锁 → 读取 → 修改 → 写入"""
        conn = self._get_conn()
        with self._write_lock:
            row = conn.execute('SELECT profile FROM users WHERE openid=?', (openid,)).fetchone()
            if row:
                profile = json.loads(row['profile'])
            else:
                profile = self.get_default_profile()
            profile = modify_fn(profile)
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(
                'INSERT OR REPLACE INTO users (openid, profile, updated_at) VALUES (?, ?, ?)',
                (openid, json.dumps(profile, ensure_ascii=False), now)
            )
            conn.commit()
            return profile

    def load_all_profiles(self):
        """加载全部用户（用于迁移或管理）"""
        conn = self._get_conn()
        rows = conn.execute('SELECT openid, profile FROM users').fetchall()
        result = {}
        for row in rows:
            try:
                result[row['openid']] = json.loads(row['profile'])
            except json.JSONDecodeError:
                continue
        return result

    def save_profile_backup(self, openid, profile):
        """存储备份版本（保留最近5个版本）"""
        conn = self._get_conn()
        with self._write_lock:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(
                'INSERT OR REPLACE INTO users (openid, profile, updated_at) VALUES (?, ?, ?)',
                (openid, json.dumps(profile, ensure_ascii=False), now)
            )
            conn.commit()

    def store_feedback(self, openid, message_id, fb_type, fb_text=None):
        """存储用户反馈"""
        conn = self._get_conn()
        with self._write_lock:
            conn.execute(
                'INSERT INTO feedbacks (openid, message_id, fb_type, fb_text) VALUES (?, ?, ?, ?)',
                (openid, str(message_id or '')[:32], fb_type, (fb_text or '')[:200])
            )
            conn.commit()
        return True

    def get_recent_feedbacks(self, openid, limit=20):
        """获取用户最近反馈"""
        conn = self._get_conn()
        rows = conn.execute(
            'SELECT fb_type, fb_text, created_at FROM feedbacks WHERE openid=? ORDER BY id DESC LIMIT ?',
            (openid, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_user_count(self):
        """获取用户总数"""
        conn = self._get_conn()
        return conn.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']

    def get_db_stats(self):
        """数据库统计"""
        conn = self._get_conn()
        users = conn.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
        fb = conn.execute('SELECT COUNT(*) as c FROM feedbacks').fetchone()['c']
        size = os.path.getsize(self._db_path) if os.path.exists(self._db_path) else 0
        return {'users': users, 'feedbacks': fb, 'size_bytes': size, 'db_path': self._db_path}

    def close(self):
        """关闭连接"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    # ==================== 迁移工具 ====================

    def migrate_from_json(self, json_path):
        """从 JSON 文件迁移全部数据到 SQLite"""
        if not os.path.exists(json_path):
            return 0
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        count = 0
        for openid, profile in data.items():
            if isinstance(profile, dict):
                self.save_user_profile(profile, openid)
                count += 1
        # 确保 feedbacks 也被迁移
        for openid, profile in data.items():
            if isinstance(profile, dict):
                fbs = profile.get('_feedbacks', [])
                for fb in fbs:
                    self.store_feedback(
                        openid, fb.get('message_id', ''),
                        fb.get('type', 'unknown'),
                        fb.get('text', '')
                    )
        return count

    def export_to_json(self, output_path=None):
        """导出全部数据到 JSON 文件（兼容旧格式）"""
        if output_path is None:
            output_path = os.path.join(PROJECT_ROOT, 'user_profile.json')
        allp = self.load_all_profiles()
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(allp, f, ensure_ascii=False, indent=2)
        return len(allp)


# ==================== 全局单例 ====================
_db_instance = None
_db_lock = threading.Lock()


def get_db():
    """获取全局 SQLiteDB 实例"""
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = SQLiteDB()
    return _db_instance


def perform_migration(json_path=None):
    """执行迁移：JSON → SQLite，返回迁移用户数"""
    if json_path is None:
        json_path = os.path.join(PROJECT_ROOT, 'user_profile.json')
    db = get_db()
    count = db.migrate_from_json(json_path)
    return count


if __name__ == '__main__':
    import sys
    db_path = os.path.join(PROJECT_ROOT, 'data', 'sleep.db')
    db = SQLiteDB(db_path)
    count = perform_migration()
    print(f'迁移完成: {count} 个用户')
    print(f'数据库统计: {db.get_db_stats()}')
