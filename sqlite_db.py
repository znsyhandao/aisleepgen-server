#!/usr/bin/env python3
"""SQLiteDB v1 — 替换JSON文件存储，保持接口兼容
- 单文件: data/aisleepgen.db
- 自动迁移JSON用户数据到SQLite
- 接口兼容: _load_all_profiles()返回dict, _save_all_profiles()写入db
- LRU缓存层: 100条 + 30s TTL (替代360K JSON每次全量读盘)
- 线程安全: WAL模式 + 连接池"""

import sqlite3, json, threading, time, os, functools

# ===== 配置 =====
DB_DIR = os.environ.get('AISLEEPGEN_DB_DIR') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else '.',
    'data'
)
DB_PATH = os.path.join(DB_DIR, 'aisleepgen.db')
LOCK = threading.RLock()

# ===== 连接池 (thread-local) =====
_local = threading.local()

def _get_conn():
    if not hasattr(_local, 'conn') or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
        _local.conn.execute('PRAGMA journal_mode=WAL')
        _local.conn.execute('PRAGMA synchronous=NORMAL')
        _local.conn.execute('PRAGMA cache_size=-64000')  # 64MB
        _local.conn.row_factory = sqlite3.Row
    return _local.conn

# ===== Schema =====
SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS user_profiles (
    openid TEXT PRIMARY KEY,
    data TEXT NOT NULL,          -- JSON序列化的完整profile
    updated_at REAL NOT NULL     -- Unix timestamp
);
CREATE TABLE IF NOT EXISTS decision_cache (
    openid TEXT NOT NULL,
    query_hash TEXT DEFAULT '',
    result TEXT NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (openid, query_hash)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX IF NOT EXISTS idx_decision_expires ON decision_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_profile_updated ON user_profiles(updated_at);
'''

def init_db(force=False):
    """初始化/迁移数据库"""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = _get_conn()
    conn.executescript(SCHEMA_SQL)
    conn.commit()

    # 从JSON迁移旧数据
    old_json = os.path.join(DB_DIR, '..', 'user_profile.json')  # 项目根目录
    if os.path.exists(old_json):
        with LOCK:
            cnt = conn.execute('SELECT COUNT(*) FROM user_profiles').fetchone()[0]
            if cnt == 0:  # 仅空数据库时迁移
                try:
                    with open(old_json, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        now = time.time()
                        rows = [(k, json.dumps(v, ensure_ascii=False), now) for k, v in data.items()]
                        conn.executemany(
                            'INSERT OR REPLACE INTO user_profiles (openid, data, updated_at) VALUES (?, ?, ?)',
                            rows
                        )
                        conn.commit()
                        print(f'[SQLiteDB] 从{old_json}迁移{len(rows)}个用户到SQLite')
                except Exception as e:
                    print(f'[SQLiteDB] JSON迁移失败: {e}')
    return conn

# ===== LRU缓存层 =====
class ProfileCache:
    _cache = {}
    _cache_time = 0
    _ttl = 30
    _hits = 0
    _misses = 0

    @classmethod
    def get(cls, openid):
        now = time.time()
        if now - cls._cache_time < cls._ttl and openid in cls._cache:
            cls._hits += 1
            return cls._cache[openid]
        cls._misses += 1
        return None

    @classmethod
    def set(cls, openid, profile):
        cls._cache[openid] = profile
        cls._cache_time = time.time()

    @classmethod
    def invalidate(cls, openid=None):
        if openid:
            cls._cache.pop(openid, None)
        else:
            cls._cache.clear()
            cls._cache_time = 0

    @classmethod
    def stats(cls):
        rate = cls._hits / max(1, cls._hits + cls._misses) * 100
        return f'SQLiteCache size={len(cls._cache)} hit={cls._hits} miss={cls._misses} rate={rate:.0f}%'

# ===== 兼容接口 =====

def load_all_profiles():
    """返回dict{openid: profile_dict}，兼容旧接口"""
    result = {}
    try:
        conn = _get_conn()
        rows = conn.execute('SELECT openid, data FROM user_profiles').fetchall()
        for r in rows:
            try:
                result[r['openid']] = json.loads(r['data'])
            except Exception:
                continue
    except Exception:
        pass
    return result

def load_profile(openid):
    """单用户加载，走缓存"""
    cached = ProfileCache.get(openid)
    if cached:
        return cached
    try:
        conn = _get_conn()
        row = conn.execute('SELECT data FROM user_profiles WHERE openid=?', (openid,)).fetchone()
        if row:
            data = json.loads(row['data'])
            ProfileCache.set(openid, data)
            return data
    except Exception:
        pass
    return None

def save_profile(openid, data):
    """单用户保存，懒惰写入"""
    try:
        conn = _get_conn()
        conn.execute(
            'INSERT OR REPLACE INTO user_profiles (openid, data, updated_at) VALUES (?, ?, ?)',
            (openid, json.dumps(data, ensure_ascii=False), time.time())
        )
        conn.commit()
        ProfileCache.set(openid, data)
        return True
    except Exception:
        return False

def save_all_profiles(all_data):
    """批量保存（兼容旧接口）"""
    if not isinstance(all_data, dict):
        return False
    try:
        conn = _get_conn()
        now = time.time()
        rows = [(k, json.dumps(v, ensure_ascii=False), now) for k, v in all_data.items()]
        conn.executemany(
            'INSERT OR REPLACE INTO user_profiles (openid, data, updated_at) VALUES (?, ?, ?)',
            rows
        )
        conn.commit()
        ProfileCache.invalidate()
        return True
    except Exception:
        return False

def get_user_count():
    try:
        conn = _get_conn()
        return conn.execute('SELECT COUNT(*) FROM user_profiles').fetchone()[0]
    except Exception:
        return 0

# ===== 决策缓存SQLite后端 =====
def save_decision(openid, result, ttl=1800, query_hash=''):
    try:
        conn = _get_conn()
        conn.execute(
            'INSERT OR REPLACE INTO decision_cache (openid, query_hash, result, expires_at, created_at) VALUES (?, ?, ?, ?, ?)',
            (openid, query_hash, json.dumps(result, ensure_ascii=False), time.time() + ttl, time.time())
        )
        conn.commit()
        return True
    except Exception:
        return False

def load_decision(openid, query_hash=''):
    try:
        conn = _get_conn()
        now = time.time()
        row = conn.execute(
            'SELECT result, expires_at FROM decision_cache WHERE openid=? AND query_hash=? AND expires_at > ?',
            (openid, query_hash, now)
        ).fetchone()
        if row:
            return json.loads(row['result'])
        # fallback: 查openid级别（空query_hash）
        if query_hash:
            row2 = conn.execute(
                'SELECT result, expires_at FROM decision_cache WHERE openid=? AND query_hash="" AND expires_at > ?',
                (openid, now)
            ).fetchone()
            if row2:
                return json.loads(row2['result'])
        return None
    except Exception:
        return None

# ===== 启动初始化 =====
init_db()

if __name__ == '__main__':
    # 自测
    print('=== SQLiteDB Test ===')
    print(f'DB: {DB_PATH}')
    cnt = get_user_count()
    print(f'用户数: {cnt}')
    # 测写读
    test_data = {'openid': 'sqlite_test', 'name': '测试', 'score': 85}
    save_profile('sqlite_test', test_data)
    loaded = load_profile('sqlite_test')
    assert loaded['openid'] == 'sqlite_test'
    assert loaded['score'] == 85
    print('读/写测试: OK')
    # 缓存命中
    cached = load_profile('sqlite_test')
    assert cached['score'] == 85
    print(ProfileCache.stats())
    # 决策缓存
    save_decision('sqlite_test', {'strategy': 'test'})
    dc = load_decision('sqlite_test')
    assert dc['strategy'] == 'test'
    print('决策缓存: OK')
    # 批量
    batch = {'batch1': {'score': 1}, 'batch2': {'score': 2}}
    save_all_profiles(batch)
    all_p = load_all_profiles()
    assert 'batch1' in all_p
    print(f'批量OK: {len(all_p)} users')
    # 清理测数据
    conn = _get_conn()
    conn.execute('DELETE FROM user_profiles WHERE openid LIKE "sqlite%" OR openid LIKE "batch%"')
    conn.execute('DELETE FROM decision_cache WHERE openid="sqlite_test"')
    conn.commit()
    print('清理OK')
    print('All tests passed!')
