#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
effectiveness_loop.py — 有效性闭循环验证层

使命：对每个干预推荐标记预期效果 → 24h后验证 → 有效加固 / 无效探索
这是系统从"推荐了"到"真的有效吗"的最后闭环。

增强 v2.0 (2026-07-09):
  引入架构边界层 — 推荐前检查依赖/麻醉/回避边界
  - record_recommendation() 前调用 arch_boundary.MetaRuleEngine
  - verify_pending() 后执行麻醉检测
  - 依赖锁定 → 自动 force_switch 策略
  - 虚假反馈 → 标记到合规日志
"""

import json, time, math
from datetime import datetime, timedelta
from sqlite_db import _get_conn, save_decision, load_decision

# 架构边界层（可选 import，允许降级）
try:
    from arch_boundary import MetaRuleEngine, NarcosisDetector, DependencyDetector
    _HAS_ARCH_BOUNDARY = True
except ImportError:
    _HAS_ARCH_BOUNDARY = False
    MetaRuleEngine = None

# Meta-meta 审计（可选 import）
try:
    from meta_meta_audit import (
        check_md5_drift,
        anchor_boundary_md5,
        track_param_drift,
        log_boundary_evolution,
        DependencyReinforcementDetector as MetaReinforcementDetector
    )
    _HAS_META_META = True
except ImportError:
    _HAS_META_META = False
    MetaReinforcementDetector = None

# 预期效果定义的策略权重基线
EFFECTIVENESS_DEFAULTS = {
    'strategy_weights': {
        'maintenance': 0.3,        # 维持策略的预期提升较小
        'adjust_env': 0.4,         # 环境调整预期中度提升
        'relaxation': 0.5,         # 放松策略预期较高
        'intervention': 0.6,       # 干预策略预期显著
        'deep_intervention': 0.7,  # 深度干预预期最强（风险也高）
    },
    'evaluation_window_hours': 24,  # 验证窗口
    'improvement_threshold': 0.05,  # 5%以上算有效
    'degradation_threshold': -0.05, # 5%以下算恶化（触发降级）
    'min_samples_before_trust': 5,  # 5次有效反馈后才信任策略
}

# 架构边界增强配置
EFFECTIVENESS_BOUNDARY_CONFIG = {
    'enable_arch_boundary': True,  # 是否启用架构边界层
    'consecutive_dependency_switch': True,  # 依赖时自动切换策略
    'narcosis_mark_and_penalize': True,  # 标记麻醉并降权
    'feedback_sanity_check': True,  # 反馈真实性校验
    'min_records_for_narcosis': 10,  # 至少10条记录才执行麻醉检测
}

# ── 全局边界层实例 ──
_ARCH_ENGINE = None


def _get_arch_engine():
    global _ARCH_ENGINE
    if _ARCH_ENGINE is None and _HAS_ARCH_BOUNDARY:
        _ARCH_ENGINE = MetaRuleEngine()
    return _ARCH_ENGINE


def _ensure_table():
    """SQLite表初始化"""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS effectiveness_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            openid TEXT NOT NULL,
            recommendation_id TEXT,
            timestamp REAL NOT NULL,
            strategy TEXT NOT NULL,
            expected_improvement REAL DEFAULT 0.0,
            actual_score_before REAL,
            actual_score_after REAL,
            improvement REAL,
            user_engaged INTEGER DEFAULT 0,
            outcome TEXT,  -- 'success','neutral','degradation','unknown'
            verified_at REAL,
            created_at REAL DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_eff_openid ON effectiveness_tracking(openid)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_eff_strategy ON effectiveness_tracking(strategy)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_eff_pending ON effectiveness_tracking(verified_at)
    """)
    conn.commit()


# 全局缓存（惰性初始化）
_EFF_CACHE = None


def _get_config():
    global _EFF_CACHE
    if _EFF_CACHE is None:
        _ensure_table()
        config = dict(EFFECTIVENESS_DEFAULTS)
        # 从SQLite加载覆盖配置
        try:
            r = load_decision('__effectiveness_config__')
            if r and isinstance(r, dict):
                config.update(r)
        except Exception:
            pass
        _EFF_CACHE = config
    return _EFF_CACHE


def record_recommendation(openid, strategy, score_before, recommendation_id=None, expected_improvement=None, recent_recommendations=None, interactions=None, timeline=None):
    """记录一次推荐（标记预期效果）

    增强 v2.0：推荐前检查架构边界（依赖/麻醉/回避）

    Args:
        openid: 用户ID
        strategy: 策略名
        score_before: 推荐时的睡眠评分
        recommendation_id: 推荐ID（可选）
        expected_improvement: 预期提升值（0-1），None则自动计算
        recent_recommendations: 近期推荐记录（边界检查用）
        interactions: 用户交互记录（回避检测用）
        timeline: 时间线数据（麻醉检测用）

    Returns:
        Dict: {'recorded': bool, 'arch_check': dict, 'note': str, ...}
    """
    config = _get_config()
    weights = config['strategy_weights']
    if expected_improvement is None:
        expected_improvement = weights.get(strategy, 0.3)

    result = {'recorded': False, 'force_switch': None, 'arch_check': None, 'note': ''}

    # ═══ 架构边界检查 ═══
    engine = _get_arch_engine()
    if engine and EFFECTIVENESS_BOUNDARY_CONFIG.get('enable_arch_boundary', True):
        recents = recent_recommendations or _get_recent_records(openid, 20)
        eff_data = {str(strategy): {'openid': openid}}  # 简化传入
        inters = interactions or []
        tl = timeline or []

        arch_check = engine.check_recommendation(
            openid=openid,
            strategy=strategy,
            recents=recents,
            effectiveness=eff_data,
            interactions=inters,
            timeline=tl,
        )
        result['arch_check'] = arch_check

        if arch_check.get('blocked'):
            force_to = arch_check.get('force_switch')
            if force_to and EFFECTIVENESS_BOUNDARY_CONFIG.get('consecutive_dependency_switch', True):
                result['force_switch'] = force_to
                result['note'] = f"边界拦截: 策略'{strategy}'被依赖锁定，强制切换到'{force_to}'"
                result['blocked'] = True
                print(f'[Effectiveness][Boundary] {result["note"]}')
                return result
            else:
                result['note'] = f"边界告警: 策略'{strategy}'有违规但无法自动切换"
                result['blocked'] = True
                print(f'[Effectiveness][Boundary] {result["note"]}')
                return result
        elif arch_check.get('warnings'):
            result['note'] = f"边界警告: {'; '.join(w['detail'] for w in arch_check['warnings'])}"
            print(f'[Effectiveness][Boundary] {result["note"]}')

    # ═══ 记录推荐 ═══
    conn = _get_conn()
    conn.execute("""
        INSERT INTO effectiveness_tracking
            (openid, recommendation_id, timestamp, strategy,
             expected_improvement, actual_score_before)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (openid, recommendation_id or str(time.time()),
          time.time(), strategy, expected_improvement, score_before))
    conn.commit()
    result['recorded'] = True
    result['strategy'] = strategy
    print(f'[Effectiveness] Recorded {strategy} for {openid} (exp={expected_improvement:.2f})')
    return result


def _get_recent_records(openid, limit=20):
    """获取用户的近期推荐记录（供架构边界层使用）"""
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT strategy, timestamp, outcome
            FROM effectiveness_tracking
            WHERE openid=?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (openid, limit)).fetchall()
        results = []
        for strategy, ts, outcome in rows:
            dt = datetime.fromtimestamp(ts) if ts else datetime.now()
            results.append({
                'strategy': strategy,
                'timestamp': ts,
                'date': dt.strftime('%Y-%m-%d'),
                'result': outcome or 'unknown',
            })
        return results
    except Exception:
        return []


def verify_pending(max_age_hours=None):
    """验证所有待处理的推荐（已超过窗口期的）

    Returns:
        int: 验证的条目数
    """
    config = _get_config()
    window = max_age_hours or config['evaluation_window_hours']
    cutoff = time.time() - window * 3600

    conn = _get_conn()
    pending = conn.execute("""
        SELECT id, openid, strategy, actual_score_before, timestamp
        FROM effectiveness_tracking
        WHERE verified_at IS NULL AND timestamp < ?
    """, (cutoff,)).fetchall()

    if not pending:
        return 0

    verified = 0
    for row in pending:
        _id, openid, strategy, score_before, ts = row
        # 获取当前用户的最新评分
        score_after = _get_user_latest_score(openid)
        if score_after is None:
            continue

        # 计算提升率
        if score_before and score_before > 0:
            improvement = (score_after - score_before) / score_before
        else:
            improvement = 0.0

        # 分类
        threshold = config['improvement_threshold']
        degrade = config['degradation_threshold']
        if improvement >= threshold:
            outcome = 'success'
        elif improvement <= degrade:
            outcome = 'degradation'
        else:
            outcome = 'neutral'

        conn.execute("""
            UPDATE effectiveness_tracking
            SET actual_score_after=?, improvement=?, outcome=?, verified_at=?
            WHERE id=?
        """, (score_after, improvement, outcome, time.time(), _id))
        verified += 1

    conn.commit()
    if verified:
        print(f'[Effectiveness] Verified {verified} pending recommendations')
    return verified


def _get_user_latest_score(openid):
    """从SQLite获取用户的最新睡眠评分"""
    try:
        conn = _get_conn()
        row = conn.execute("""
            SELECT actual_score_after FROM effectiveness_tracking
            WHERE openid=? AND actual_score_after IS NOT NULL
            ORDER BY verified_at DESC LIMIT 1
        """, (openid,)).fetchone()
        if row:
            return row[0]
    except Exception:
        pass
    # fallback: 从user_profile读取
    from sqlite_db import load_profile
    profile = load_profile(openid)
    if profile and isinstance(profile, dict):
        latest = profile.get('latest', {})
        return latest.get('score', None)
    return None


def get_effectiveness_report(openid=None, check_narcosis=True):
    """生成策略有效性报告

    增强 v2.0：加入麻醉检测 → 标记并降权

    Args:
        openid: 可选，指定用户则生成个性化报告
        check_narcosis: 是否执行麻醉检测

    Returns:
        dict: 策略有效性报告
    """
    conn = _get_conn()
    if openid:
        rows = conn.execute("""
            SELECT strategy,
                   COUNT(*) as n,
                   SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) as successes,
                   SUM(CASE WHEN outcome='degradation' THEN 1 ELSE 0 END) as degradations,
                   AVG(improvement) as avg_improvement
            FROM effectiveness_tracking
            WHERE verified_at IS NOT NULL AND openid=?
            GROUP BY strategy
            ORDER BY avg_improvement DESC
        """, (openid,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT strategy,
                   COUNT(*) as n,
                   SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) as successes,
                   SUM(CASE WHEN outcome='degradation' THEN 1 ELSE 0 END) as degradations,
                   AVG(improvement) as avg_improvement
            FROM effectiveness_tracking
            WHERE verified_at IS NOT NULL
            GROUP BY strategy
            ORDER BY avg_improvement DESC
        """).fetchall()

    report = {}
    for strategy, n, successes, degradations, avg_imp in rows:
        report[strategy] = {
            'samples': n,
            'success_rate': successes / n if n > 0 else 0,
            'degradation_rate': degradations / n if n > 0 else 0,
            'avg_improvement': round(avg_imp, 4) if avg_imp else 0,
            'narcosis_detected': False,  # 麻醉检测结果
            'narcosis_score': 0,          # 麻醉得分
        }

    # ═══ 麻醉检测 ═══
    if check_narcosis and _HAS_ARCH_BOUNDARY and EFFECTIVENESS_BOUNDARY_CONFIG.get('narcosis_mark_and_penalize', True):
        narcosis_detector = NarcosisDetector()
        min_records = EFFECTIVENESS_BOUNDARY_CONFIG.get('min_records_for_narcosis', 10)

        if openid:
            timeline = _build_timeline(openid)
            for strategy in report:
                nar_result = narcosis_detector.evaluate(openid, strategy, timeline)
                if nar_result['is_narcosis']:
                    report[strategy]['narcosis_detected'] = True
                    report[strategy]['narcosis_score'] = nar_result['narcosis_score']
                    report[strategy]['narcosis_label'] = nar_result.get('label')
                    print(f'[Effectiveness][Narcosis] 策略 {strategy}: 麻醉得分 {nar_result["narcosis_score"]:.2f}')

    # 更新策略权重（含麻醉降权）
    _update_strategy_weights(report)
    return report


def _build_timeline(openid):
    """构建用户时间线（供麻醉检测使用）"""
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT timestamp, strategy, actual_score_before, actual_score_after, outcome, verified_at
            FROM effectiveness_tracking
            WHERE openid=?
            ORDER BY timestamp ASC
        """, (openid,)).fetchall()
        timeline = []
        for ts, strategy, before, after, outcome, verified in rows:
            if before is not None:
                timeline.append({
                    'ts': ts,
                    'score': before,
                    'strategy': strategy or '',
                    'source': 'rec',
                })
            if after is not None:
                timeline.append({
                    'ts': verified or ts + 1,
                    'score': after,
                    'strategy': strategy or '',
                    'source': 'verify',
                })
        return timeline
    except Exception:
        return []


def _update_strategy_weights(report):
    """基于有效性数据自动调整策略权重

    增强 v2.0：麻醉标记的策略不调整，依赖锁定策略降权50%
    """
    config = _get_config()
    weights = dict(config['strategy_weights'])
    min_samples = config['min_samples_before_trust']
    changed = False

    for strategy, stats in report.items():
        if stats['samples'] < min_samples:
            continue  # 样本不足，不调整
        if strategy not in weights:
            continue

        success_rate = stats['success_rate']
        old_weight = weights[strategy]

        # ── 麻醉检测降权 ──
        if stats.get('narcosis_detected'):
            new_weight = max(0.05, old_weight * 0.5)  # 麻醉策略直接折半
            weights[strategy] = new_weight
            if abs(new_weight - old_weight) > 0.001:
                changed = True
                print(f'[Effectiveness][Narcosis] 策略 {strategy} 麻醉降权: {old_weight:.2f} -> {new_weight:.2f}')
            continue

        # ── 正常权重调整 ──
        if success_rate > 0.6:
            new_weight = min(0.9, old_weight + 0.05)
        elif success_rate < 0.2:
            new_weight = max(0.1, old_weight - 0.05)
        else:
            continue  # 稳定区间不动

        weights[strategy] = new_weight
        if abs(new_weight - old_weight) > 0.001:
            changed = True
            print(f'[Effectiveness] Weight {strategy}: {old_weight:.2f} -> {new_weight:.2f}')

    if changed:
        new_config = dict(config)
        new_config['strategy_weights'] = weights
        save_decision('__effectiveness_config__', new_config)
        global _EFF_CACHE
        _EFF_CACHE = new_config


def best_strategy_for_user(openid):
    """基于历史有效性数据，为用户推荐最佳策略"""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT strategy, AVG(improvement) as avg_imp, COUNT(*) as n
        FROM effectiveness_tracking
        WHERE openid=? AND verified_at IS NOT NULL
        GROUP BY strategy
        ORDER BY avg_imp DESC
    """, (openid,)).fetchall()

    if rows:
        best = rows[0]
        return {
            'strategy': best[0],
            'avg_improvement': round(best[1], 4) if best[1] else 0,
            'samples': best[2],
            'personalized': True,
        }

    return {'personalized': False, 'message': 'not enough personal data'}


def run_effectiveness_cycle(openid=None, run_boundary_audit=True):
    """完整有效性验证周期（供定时任务调用）

    增强 v2.0：验证后执行架构边界审计

    Args:
        openid: 可选，指定用户则执行个性化审计
        run_boundary_audit: 是否执行边界审计

    Returns:
        dict: 包含验证结果、报告、边界审计
    """
    n = verify_pending()
    report = get_effectiveness_report(openid=openid, check_narcosis=True)

    # ═══ 闭环：验证完成后，回写轨迹预测样本 ═══
    _sync_trajectory_samples()
    # ═══ 闭环：检查是否需要训练/重建 LightGBM ═══
    _maybe_build_trajectory_model()

    result = {
        'verified': n,
        'strategies_tracked': len(report),
        'model_info': _get_traj_model_info(),
    }

    # ═══ 边界审计 ═══
    if run_boundary_audit and _HAS_ARCH_BOUNDARY:
        engine = _get_arch_engine()
        if engine:
            try:
                # 构建简化审计数据
                audit_data = {}
                conn = _get_conn()
                if openid:
                    rows = conn.execute("""
                        SELECT openid FROM effectiveness_tracking
                        WHERE openid=?
                        GROUP BY openid
                    """, (openid,)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT openid FROM effectiveness_tracking
                        GROUP BY openid
                    """).fetchall()

                for (uid,) in rows:
                    recents = _get_recent_records(uid, 20)
                    tl = _build_timeline(uid)
                    audit_data[uid] = {
                        'recommendations': recents,
                        'effectiveness': {},
                        'interactions': [],
                        'timeline': tl,
                    }

                audit_result = engine.auditor.run_audit(audit_data)
                result['boundary_audit'] = {
                    'violations': audit_result['summary']['total_violations'],
                    'warnings': audit_result['summary']['total_warnings'],
                    'critical': audit_result['summary']['critical'],
                    'summary': audit_result['summary'],
                }
            except Exception as e:
                print(f'[Effectiveness][Boundary] Audit error: {e}')
                result['boundary_audit'] = {'error': str(e)}

        # ═══ 依赖强化循环检测 ═══
        if _HAS_META_META and MetaReinforcementDetector:
            try:
                _reinforce_detector = MetaReinforcementDetector()
                _reinforce_results = {}
                for (uid,) in (rows or conn.execute("SELECT openid FROM effectiveness_tracking GROUP BY openid").fetchall()):
                    recents = _get_recent_records(uid, 50)
                    if len(recents) < 10:
                        continue
                    # 构建权重历史
                    _weight_hist = []
                    for r in recents:
                        _weight_hist.append({
                            'strategy': r.get('strategy', ''),
                            'weight': r.get('weight', 0.5),
                            'date': r.get('date', ''),
                        })
                    _rr = _reinforce_detector.detect(uid, recents, _weight_hist)
                    if _rr.get('has_reinforcement'):
                        _reinforce_results[uid] = {
                            'score': _rr['reinforcement_score'],
                            'anchor_strategy': _rr['strongest_loop']['anchor_strategy'],
                        }
                if _reinforce_results:
                    result['dependency_reinforcement'] = _reinforce_results
                    print(f'[Effectiveness][Reinforcement] Detected {len(_reinforce_results)} users with reinforcement loops')
            except Exception as e:
                print(f'[Effectiveness][Reinforcement] Error: {e}')

    return result


def _sync_trajectory_samples():
    """把最新验证的 effectiveness 记录同步为轨迹预测样本
    
    逻辑：
    - 找到最近1小时内验证的记录
    - 对每条记录：提取当时的特征 → 计算实际距离变化 → record_sample
    - 用户 profile 从 load_profile 获取
    """
    try:
        conn = _get_conn()
        cutoff = time.time() - 3600  # 最近1小时
        rows = conn.execute("""
            SELECT id, openid, strategy, actual_score_before, actual_score_after
            FROM effectiveness_tracking
            WHERE verified_at IS NOT NULL AND verified_at > ?
              AND actual_score_before IS NOT NULL AND actual_score_after IS NOT NULL
        """, (cutoff,)).fetchall()
        
        if not rows:
            return
        
        from sqlite_db import load_profile
        from state_topology import _extract_trajectory_features
        
        synced = 0
        for _id, openid, strategy, before, after in rows:
            profile = load_profile(openid)
            if not profile or not isinstance(profile, dict):
                continue
            feats = _extract_trajectory_features(profile, strategy)
            if feats is None:
                continue
            # 实际距离变化 ≈ 反向评分变化（评分升=距离降）
            actual_delta = -(after - before) / 100.0
            if abs(actual_delta) < 0.001:
                continue
            from trajectory_model_db import record_sample
            record_sample(openid, strategy, feats, actual_delta)
            synced += 1
        
        if synced:
            print(f'[Effectiveness] Synced {synced} trajectory samples from verified records')
    except Exception as e:
        print(f'[Effectiveness] _sync_trajectory_samples error: {type(e).__name__}: {e}')


def _maybe_build_trajectory_model():
    """样本≥30时训练 LightGBM，样本不足时不操作"""
    try:
        from trajectory_model_db import count_samples, build_trajectory_model, get_model_info
        n = count_samples()
        if n >= 30:
            model = build_trajectory_model(force=False)
            if model:
                info = get_model_info()
                print(f'[Effectiveness] Trajectory model ready: {info["training_samples"]} samples')
            else:
                model = build_trajectory_model(force=True)
                if model:
                    info = get_model_info()
                    print(f'[Effectiveness] Trajectory model (re)built: {info["training_samples"]} samples')
    except Exception as e:
        print(f'[Effectiveness] _maybe_build_trajectory_model error: {e}')


def _get_traj_model_info():
    """返回轨迹模型状态（供 run_effectiveness_cycle 输出）"""
    try:
        from trajectory_model_db import get_model_info
        return get_model_info()
    except Exception:
        return {'total_samples': 0, 'model_ready': False}


# 自动初始化表
_ensure_table()

if __name__ == '__main__':
    print('=== 有效性闭循环验证层 ===')
    print(run_effectiveness_cycle())
    print(json.dumps(get_effectiveness_report(), indent=2, ensure_ascii=False))
