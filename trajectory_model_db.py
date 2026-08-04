#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
trajectory_model_db.py — 轨迹预测模型持久化 + 跨用户 LightGBM 训练

设计：
1. SQLite 表 trajectory_samples：存特征+标签（跨用户持久化，重启不丢）
2. 样本 ≥ 30 时自动训练 LightGBM 回归器
3. 模型 pickle 存到 .surgical_backups/trajectory_lgb_{ts}.pkl
4. 轻量接口与 state_topology 的 _TRAJECTORY_BUFFER 打通
"""

import os, sys, json, time, pickle, hashlib
import math
import sqlite3
import threading

SQLITE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'aisleepgen.db')
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

_local = threading.local()

def _get_conn():
    """获取线程本地 SQLite 连接"""
    if not hasattr(_local, 'traj_conn') or _local.traj_conn is None:
        os.makedirs(os.path.dirname(SQLITE_DB), exist_ok=True)
        _local.traj_conn = sqlite3.connect(SQLITE_DB, check_same_thread=False, timeout=30)
        _local.traj_conn.execute('PRAGMA journal_mode=WAL')
        _local.traj_conn.execute('PRAGMA synchronous=NORMAL')
    return _local.traj_conn


# ═══ 特征定义（与 state_topology._extract_trajectory_features 对齐） ═══
FEATURE_NAMES = [
    'd_current',        # 当前距好状态距离
    'avg_change_3',     # 近3步平均变化
    'mu_7',             # 近7步均值
    'sigma_7',          # 近7步标准差
    'has_strategy',     # 是否指定策略 (0/1)
    'avg_effect',       # 策略历史平均效果
]

# ═══ 全局模型缓存 ═══
_TRAJECTORY_LGB = None       # LightGBM 模型实例
_TRAJECTORY_LGB_COUNT = 0    # 训练样本数
_TRAJECTORY_LGB_FEATURES = FEATURE_NAMES  # 特征名列表


def _ensure_table():
    """建表"""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trajectory_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            openid TEXT NOT NULL,
            strategy_id TEXT,
            ts REAL NOT NULL,
            d_current REAL,
            avg_change_3 REAL,
            mu_7 REAL,
            sigma_7 REAL,
            has_strategy REAL,
            avg_effect REAL,
            label REAL,           -- 实际距离变化 Δ_{t+1}
            created_at REAL DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_traj_samples_openid ON trajectory_samples(openid)
    """)
    conn.commit()


def record_sample(openid, strategy_id, features, actual_delta):
    """写入一条训练样本（SQLite 持久化）
    
    Args:
        openid: 用户ID
        strategy_id: 策略ID（可能为 None）
        features: [d_current, avg_change_3, mu_7, sigma_7, has_strategy, avg_effect]
        actual_delta: 实际距离变化（负值=好转）
    """
    if features is None or len(features) != 6:
        return False
    try:
        _ensure_table()
        conn = _get_conn()
        conn.execute("""
            INSERT INTO trajectory_samples
                (openid, strategy_id, ts, d_current, avg_change_3, mu_7, sigma_7,
                 has_strategy, avg_effect, label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (openid, strategy_id, time.time(),
              features[0], features[1], features[2], features[3],
              features[4], features[5], actual_delta))
        conn.commit()
        # 新数据到达 → 清除缓存模型
        global _TRAJECTORY_LGB
        _TRAJECTORY_LGB = None
        return True
    except Exception as e:
        print(f'[TrajectoryDB] record_sample error: {e}')
        return False


def count_samples():
    """返回总样本数"""
    try:
        _ensure_table()
        row = _get_conn().execute("SELECT COUNT(*) FROM trajectory_samples").fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def _get_training_data(min_samples=30):
    """从 SQLite 读取训练数据
    
    Returns:
        (X, y) or (None, None) if insufficient
    """
    n = count_samples()
    if n < min_samples:
        return None, None
    
    conn = _get_conn()
    rows = conn.execute("""
        SELECT d_current, avg_change_3, mu_7, sigma_7, has_strategy, avg_effect, label
        FROM trajectory_samples
        WHERE label IS NOT NULL
          AND d_current IS NOT NULL
        ORDER BY id
    """).fetchall()
    
    if len(rows) < min_samples:
        return None, None
    
    X = [[r[0], r[1], r[2], r[3], r[4], r[5]] for r in rows]
    y = [r[6] for r in rows]
    return X, y


def _train_lightgbm(X, y):
    """训练 LightGBM 回归器
    
    自动调参：num_leaves=12, min_data=10（防过拟合）
    小数据量场景（30~200条），控制模型复杂度
    """
    try:
        import lightgbm as lgb
        import numpy as np
    except ImportError:
        print('[TrajectoryDB] lightgbm not installed, falling back')
        return None
    
    X_arr = np.array(X, dtype=np.float64)
    y_arr = np.array(y, dtype=np.float64)
    
    # 样本量适配参数
    n = len(X)
    if n < 30:
        return None
    
    params = {
        'objective': 'regression',
        'metric': 'mae',
        'num_leaves': min(12, max(4, n // 10)),
        'min_data_in_leaf': max(5, n // 20),
        'learning_rate': 0.05,
        'feature_fraction': 0.8,
        'verbosity': -1,
        'random_state': 42,
        'num_threads': 2,
    }
    
    try:
        ds = lgb.Dataset(X_arr, label=y_arr, feature_name=FEATURE_NAMES)
        model = lgb.train(params, ds, num_boost_round=min(100, max(20, n * 2)))
        
        # 保存模型（两份：命名版+最新版）
        os.makedirs(MODEL_DIR, exist_ok=True)
        ts = time.strftime('%Y%m%d_%H%M%S')
        model_path = os.path.join(MODEL_DIR, f'trajectory_lgb_{ts}_{n}samples.pkl')
        with open(model_path, 'wb') as f:
            pickle.dump({'model': model, 'features': FEATURE_NAMES, 'n': n, 'ts': ts}, f)
        # 也写入 lgbm_tracker_model.pkl（生产路径）
        prod_path = os.path.join(MODEL_DIR, 'lgbm_tracker_model.pkl')
        with open(prod_path, 'wb') as f:
            pickle.dump({'model': model, 'features': FEATURE_NAMES, 'n': n, 'ts': ts}, f)
        
        print(f'[TrajectoryDB] LightGBM trained: {n} samples, mae=?, saved={os.path.basename(model_path)}')
        return model
    except Exception as e:
        print(f'[TrajectoryDB] LightGBM training error: {e}')
        return None


def build_trajectory_model(force=False):
    """构建/重建轨迹预测模型（惰性加载+自动重训）
    
    规则：
    - 样本 < 30 → 返回 None（降级）
    - 样本 ≥ 30 → 训练/加载 LightGBM
    - force=True → 强制重新训练
    
    Returns:
        model or None
    """
    global _TRAJECTORY_LGB, _TRAJECTORY_LGB_COUNT
    
    if not force and _TRAJECTORY_LGB is not None:
        return _TRAJECTORY_LGB
    
    X, y = _get_training_data(min_samples=30)
    if X is None:
        _TRAJECTORY_LGB = None
        _TRAJECTORY_LGB_COUNT = 0
        return None
    
    model = _train_lightgbm(X, y)
    if model is None:
        _TRAJECTORY_LGB = None
        _TRAJECTORY_LGB_COUNT = 0
        return None
    
    _TRAJECTORY_LGB = model
    _TRAJECTORY_LGB_COUNT = len(X)
    return model


def predict_delta(features):
    """用 LightGBM 模型预测一步距离变化
    
    Args:
        features: [d_current, avg_change_3, mu_7, sigma_7, has_strategy, avg_effect]
    
    Returns:
        float: 预测的距离变化（负值=好转），或 None（降级）
    """
    global _TRAJECTORY_LGB, _TRAJECTORY_LGB_COUNT
    if _TRAJECTORY_LGB is None and _TRAJECTORY_LGB_COUNT == 0:
        build_trajectory_model()
    if _TRAJECTORY_LGB is None or features is None:
        return None
    try:
        import numpy as np
        delta = _TRAJECTORY_LGB.predict(np.array([features], dtype=np.float64))[0]
        return max(-0.15, min(0.15, float(delta)))
    except Exception as e:
        print(f'[TrajectoryDB] predict error: {e}')
        return None


def get_model_info():
    """返回模型状态摘要（供日志/诊断）"""
    return {
        'total_samples': count_samples(),
        'model_ready': _TRAJECTORY_LGB is not None,
        'training_samples': _TRAJECTORY_LGB_COUNT,
    }


# 初始化表
_ensure_table()

if __name__ == '__main__':
    print('=== Trajectory Model DB ===')
    info = get_model_info()
    print(f'Total samples: {info["total_samples"]}')
    print(f'Model ready: {info["model_ready"]}')
