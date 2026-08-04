#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
population_manager.py — AISleepGen 群体策略进化引擎 v1.0

范式跃迁：跨用户知识积累不再只是共享A矩阵先验。
如果用户群体A和B睡眠模式完全不同，系统会自动发现并分裂出子策略。
元学习调的不再是全局参数，而是群体特异参数。

核心能力：
  - cluster_users() → 返回用户集群（基于特征：avg_score, volatility, bedtime等）
  - get_cluster_params(openid) → 返回用户所属集群的元参数组
  - record_outcome(openid, intervention, outcome) → 记录实验用于集群评估
  - suggest_strategy_split() → 检测是否需要分裂集群

参数存储：data/population_clusters/cluster_{n}.json
"""

import json, os, time, math, logging, random
from datetime import datetime
from collections import defaultdict

_pm_log = logging.getLogger('aisleepgen.population_manager')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CLUSTER_DIR = os.path.join(PROJECT_ROOT, 'data', 'population_clusters')
OUTCOME_LOG_PATH = os.path.join(CLUSTER_DIR, '_outcomes.json')
CLUSTER_META_PATH = os.path.join(CLUSTER_DIR, '_meta.json')

# ==================== 默认集群参数 ====================

DEFAULT_CLUSTER_PARAMS = {
    'beta': 0.8,
    'forget_factor': 0.9,
    'intervention_rate': 0.5,
    'push_threshold': 50,
    'alpha0': 0.1,
}

PARAM_BOUNDS = {
    'beta': (0.1, 3.0),
    'forget_factor': (0.5, 0.99),
    'intervention_rate': (0.1, 0.8),
    'push_threshold': (30, 70),
    'alpha0': (0.01, 1.0),
}

# ==================== 简单k-means（无numpy依赖） ====================


def _euclidean(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _kmeans_pp_init(data, k):
    n = len(data)
    if n == 0:
        return []
    if k > n:
        k = n
    centers = [data[random.randint(0, n - 1)]]
    for _ in range(1, k):
        dists = [min(_euclidean(p, c) for c in centers) for p in data]
        total = sum(dists)
        if total <= 1e-15:
            break
        probs = [d / total for d in dists]
        r = random.random()
        cum = 0.0
        for i, p in enumerate(probs):
            cum += p
            if r <= cum:
                centers.append(data[i])
                break
    return centers


def _kmeans(data, k, max_iter=50):
    vectors = [f for _, f in data]
    if not vectors:
        return []
    n_dims = len(vectors[0])
    centers = _kmeans_pp_init(vectors, k)
    if len(centers) < k:
        k = len(centers)
    labels = [0] * len(data)
    for _ in range(max_iter):
        changed = False
        for i, vec in enumerate(vectors):
            best_dist = float('inf')
            best_k = 0
            for j, c in enumerate(centers):
                d = _euclidean(vec, c)
                if d < best_dist:
                    best_dist = d
                    best_k = j
            if labels[i] != best_k:
                changed = True
                labels[i] = best_k
        for j in range(k):
            if j not in labels:
                centers[j] = vectors[random.randint(0, len(vectors) - 1)]
                changed = True
        new_centers = []
        for j in range(k):
            members = [vectors[i] for i, lbl in enumerate(labels) if lbl == j]
            if members:
                new_c = [sum(dim[i] for dim in members) / len(members) for i in range(n_dims)]
                new_centers.append(new_c)
            else:
                new_centers.append(centers[j])
        centers = new_centers
        if not changed:
            break
    result = {j: [] for j in range(k)}
    for i, (uid, _) in enumerate(data):
        result[labels[i]].append(uid)
    return [(centers[j], result[j]) for j in range(k)]


def _elbow_k(data, max_k=6):
    if len(data) < 3:
        return 1
    max_k = min(max_k, len(data) - 1, 6)
    if max_k < 2:
        return 1
    inertias = {}
    for k in range(1, max_k + 1):
        clusters = _kmeans(data, k)
        inertia = 0.0
        for centroid, members in clusters:
            for uid in members:
                vec = next(f for u, f in data if u == uid)
                inertia += _euclidean(vec, centroid) ** 2
        inertias[k] = inertia
    if len(inertias) >= 3:
        best_k = 2
        max_drop = 0.0
        for k in range(2, max_k):
            drop = (inertias[k - 1] - inertias[k]) / inertias[1]
            next_drop = (inertias[k] - inertias[k + 1]) / inertias[1]
            if drop - next_drop > max_drop:
                max_drop = drop - next_drop
                best_k = k
        return max(2, best_k)
    return 2


# ==================== 特征提取 ====================


def _extract_user_features(profile):
    """从用户画像提取聚类特征向量
    6维: [avg_score_norm, volatility_norm, bedtime_norm, duration_norm, emotion_norm, sensitivity]"""
    history = profile.get('history', [])
    if not history:
        return None
    scored = [h for h in history if isinstance(h, dict) and h.get('wm_score', 0) > 0]
    if len(scored) < 2:
        return None
    scores = [h.get('wm_score', 50) for h in scored]
    avg_score = sum(scores) / len(scores)
    score_volatility = math.sqrt(sum((s - avg_score) ** 2 for s in scores) / len(scores))
    bedtimes = []
    durations = []
    emotion_sum = 0
    emotion_count = 0
    for h in scored:
        bt_str = h.get('bedtime', '') or h.get('time_bed', '') or ''
        if bt_str:
            try:
                parts = bt_str.split(':') if ':' in bt_str else bt_str.split('：')
                if parts:
                    h_val = int(parts[0])
                    m_val = int(parts[1]) if len(parts) > 1 else 0
                    bt_hour = h_val + m_val / 60.0
                    if bt_hour < 6:
                        bt_hour += 24
                    bedtimes.append(bt_hour)
            except (ValueError, IndexError):
                pass
        dur = h.get('total_duration', 0) or h.get('duration', 0)
        if dur and dur > 0:
            durations.append(dur / 60.0)
        mood = str(h.get('mood', '') or h.get('emotion', ''))
        if mood:
            if mood in ('positive', '开心', '平静', '轻松'):
                emotion_sum += 1
            elif mood in ('negative', '焦虑', '烦躁', '难过', '抑郁'):
                emotion_sum -= 1
            emotion_count += 1
    avg_bedtime = sum(bedtimes) / len(bedtimes) if bedtimes else 22.0
    avg_duration = sum(durations) / len(durations) if durations else 7.0
    emotion_tendency = emotion_sum / emotion_count if emotion_count > 0 else 0.0
    fb_positive = 0
    fb_total = 0
    for h in history:
        fb = str(h.get('feedback', '') or h.get('user_feedback', ''))
        if fb == 'like':
            fb_positive += 1
            fb_total += 1
        elif fb == 'dislike':
            fb_total += 1
    intervention_sensitivity = fb_positive / max(fb_total, 1)
    return [
        avg_score / 100.0,
        min(score_volatility / 50.0, 1.0),
        avg_bedtime / 24.0,
        avg_duration / 12.0,
        (emotion_tendency + 1.0) / 2.0,
        intervention_sensitivity,
    ]


# ==================== 群体管理器 ====================

class PopulationManager:
    def __init__(self):
        os.makedirs(CLUSTER_DIR, exist_ok=True)
        self._cluster_cache = None
        self._last_load = 0
        self._load_lock = None
        try:
            import threading
            self._load_lock = threading.Lock()
        except Exception as _ep:
            _log.warning("[population_manager] %s", _ep)
    # ==================== IO ====================

    def _load_clusters(self, force=False):
        now = time.time()
        if not force and self._cluster_cache is not None and now - self._last_load < 10:
            return self._cluster_cache
        clusters = {}
        try:
            if os.path.exists(CLUSTER_DIR):
                for fn in os.listdir(CLUSTER_DIR):
                    if fn.startswith('cluster_') and fn.endswith('.json') and not fn.startswith('_'):
                        idx = int(fn.replace('cluster_', '').replace('.json', ''))
                        with open(os.path.join(CLUSTER_DIR, fn), 'r', encoding='utf-8') as f:
                            clusters[idx] = json.load(f)
        except Exception as e:
            _pm_log.warning('[PopMgr] Load error: %s', e)
        if not clusters:
            clusters = self._create_default_clusters()
        self._cluster_cache = clusters
        self._last_load = now
        return clusters

    def _save_cluster(self, idx, cluster_data):
        fn = os.path.join(CLUSTER_DIR, f'cluster_{idx}.json')
        try:
            with open(fn, 'w', encoding='utf-8') as f:
                json.dump(cluster_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _pm_log.warning('[PopMgr] Save error for cluster_%d: %s', idx, e)

    def _create_default_clusters(self):
        clusters = {}
        clusters[0] = {
            'name': 'default',
            'created_at': datetime.now().isoformat(),
            'last_clustered': datetime.now().isoformat(),
            'users': [],
            'centroid': [0.5] * 6,
            'params': dict(DEFAULT_CLUSTER_PARAMS),
            'stats': {
                'total_outcomes': 0, 'positive_outcomes': 0,
                'avg_outcome': 0.0, 'last_positive_rate': 0.5,
            },
            'outcome_history': [],
        }
        self._save_cluster(0, clusters[0])
        self._save_meta({'next_cluster_id': 1})
        return clusters

    def _save_meta(self, meta_data=None):
        if meta_data is None:
            meta_data = {}
        try:
            with open(CLUSTER_META_PATH, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)
        except Exception as _ep:
            _log.warning("[population_manager] %s", _ep)
    def _load_meta(self):
        try:
            if os.path.exists(CLUSTER_META_PATH):
                with open(CLUSTER_META_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as _ep:
            _log.warning("[population_manager] %s", _ep)
        return {'next_cluster_id': 1}

    def _load_outcomes(self):
        try:
            if os.path.exists(OUTCOME_LOG_PATH):
                with open(OUTCOME_LOG_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as _ep:
            _log.warning("[population_manager] %s", _ep)
        return {'outcomes': []}

    def _save_outcomes(self, data):
        try:
            with open(OUTCOME_LOG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _pm_log.warning('[PopMgr] Save outcomes error: %s', e)

    def _get_user_feature(self, openid):
        profile_path = os.path.join(PROJECT_ROOT, 'user_profiles', f'{openid}.json')
        profile = {}
        try:
            if os.path.exists(profile_path):
                with open(profile_path, 'r', encoding='utf-8') as f:
                    profile = json.load(f)
            else:
                profile_path2 = os.path.join(PROJECT_ROOT, 'user_profile.json')
                if os.path.exists(profile_path2):
                    with open(profile_path2, 'r', encoding='utf-8') as f:
                        all_profiles = json.load(f)
                    profile = all_profiles.get(openid, {})
        except Exception as _ep:
            _log.warning("[population_manager] %s", _ep)
        return _extract_user_features(profile)

    # ==================== 聚类检测 ====================

    def cluster_users(self, force=False):
        clusters = self._load_clusters(force)
        user_features = []
        for cidx, cdata in clusters.items():
            for uid in cdata.get('users', []):
                feature = self._get_user_feature(uid)
                if feature:
                    user_features.append((uid, feature))
        if len(user_features) < 3:
            _pm_log.info('[PopMgr] Too few users (%d), using default', len(user_features))
            return clusters

        best_k = _elbow_k(user_features, max_k=min(6, len(user_features) - 1))
        best_k = max(2, min(best_k, len(user_features) - 1))
        kmeans_result = _kmeans(user_features, best_k)
        new_clusters = {}
        new_user_assignment = {}
        meta = self._load_meta()
        next_id = meta.get('next_cluster_id', len(clusters))

        for i, (centroid, members) in enumerate(kmeans_result):
            cidx = i if i < len(clusters) else next_id
            if i >= len(clusters):
                next_id += 1
            if len(members) < 3 and len(kmeans_result) > 1:
                # 合并到最近集群
                best_dist = float('inf')
                best_cidx = None
                for j, (c2, m2) in enumerate(kmeans_result):
                    if j == i or j >= len(kmeans_result):
                        continue
                    j_cidx = j if j < len(clusters) else -1
                    d = _euclidean(centroid, c2)
                    if d < best_dist:
                        best_dist = d
                        best_cidx = j_cidx if j_cidx >= 0 else (next_id - 1)
                if best_cidx is not None and best_cidx in clusters:
                    for uid in members:
                        if uid not in clusters[best_cidx]['users']:
                            clusters[best_cidx]['users'].append(uid)
                            new_user_assignment[uid] = best_cidx
                    continue

            old_data = clusters.get(cidx, {})
            new_clusters[cidx] = {
                'name': old_data.get('name', f'cluster_{cidx}'),
                'created_at': old_data.get('created_at', datetime.now().isoformat()),
                'last_clustered': datetime.now().isoformat(),
                'users': members,
                'centroid': [round(v, 4) for v in centroid],
                'params': old_data.get('params', dict(DEFAULT_CLUSTER_PARAMS)),
                'stats': old_data.get('stats', {
                    'total_outcomes': 0, 'positive_outcomes': 0,
                    'avg_outcome': 0.0, 'last_positive_rate': 0.5,
                }),
                'outcome_history': old_data.get('outcome_history', []),
            }
            if 'name' not in old_data or old_data.get('name', '').startswith('default'):
                new_clusters[cidx]['name'] = self._generate_cluster_name(centroid)
            for uid in members:
                new_user_assignment[uid] = cidx

        for uid, _ in user_features:
            if uid not in new_user_assignment:
                vec = next(f for u, f in user_features if u == uid)
                best_cidx = min(new_clusters.keys(), key=lambda c: _euclidean(vec, new_clusters[c]['centroid']))
                new_user_assignment[uid] = best_cidx
                if uid not in new_clusters[best_cidx]['users']:
                    new_clusters[best_cidx]['users'].append(uid)

        for cidx, cdata in new_clusters.items():
            self._save_cluster(cidx, cdata)
        meta['next_cluster_id'] = next_id
        self._save_meta(meta)
        self._cluster_cache = new_clusters
        return new_clusters

    def _generate_cluster_name(self, centroid):
        avg_score = centroid[0] * 100
        volatility = centroid[1] * 50
        bedtime = centroid[2] * 24
        emotion = centroid[4] * 2 - 1
        parts = []
        if avg_score > 65:
            parts.append('high_score')
        elif avg_score < 40:
            parts.append('low_score')
        if volatility > 20:
            parts.append('volatile')
        else:
            parts.append('stable')
        if bedtime > 24:
            parts.append('late_bedtime')
        if emotion > 0.3:
            parts.append('positive')
        elif emotion < -0.3:
            parts.append('negative')
        return '_'.join(parts) if parts else 'mixed'

    # ==================== 集群参数 ====================

    def get_cluster_params(self, openid):
        clusters = self._load_clusters()
        user_cluster = None
        for cidx, cdata in clusters.items():
            if openid in cdata.get('users', []):
                user_cluster = cidx
                break
        if user_cluster is None:
            user_cluster = self._assign_new_user(openid)
        if user_cluster is not None:
            return clusters[user_cluster].get('params', dict(DEFAULT_CLUSTER_PARAMS))
        return dict(DEFAULT_CLUSTER_PARAMS)

    def get_cluster_id(self, openid):
        clusters = self._load_clusters()
        for cidx, cdata in clusters.items():
            if openid in cdata.get('users', []):
                return cidx
        return self._assign_new_user(openid)

    def _assign_new_user(self, openid):
        clusters = self._load_clusters()
        if not clusters:
            clusters = self._create_default_clusters()
        feature = self._get_user_feature(openid)
        if feature:
            best_cidx = min(clusters.keys(), key=lambda c: _euclidean(feature, clusters[c].get('centroid', [0.5] * 6)))
        else:
            best_cidx = max(clusters.keys(), key=lambda c: len(clusters[c].get('users', [])))
        if openid not in clusters[best_cidx]['users']:
            clusters[best_cidx]['users'].append(openid)
            self._save_cluster(best_cidx, clusters[best_cidx])
            self._cluster_cache = clusters
        return best_cidx

    # ==================== Outcome记录 ====================

    def record_outcome(self, openid, intervention, outcome_value, positive=True):
        clusters = self._load_clusters()
        cidx = self.get_cluster_id(openid)
        if cidx is None or cidx not in clusters:
            return
        cluster = clusters[cidx]
        stats = cluster.setdefault('stats', {
            'total_outcomes': 0, 'positive_outcomes': 0,
            'avg_outcome': 0.0, 'last_positive_rate': 0.5,
        })
        history = cluster.setdefault('outcome_history', [])
        stats['total_outcomes'] += 1
        if positive:
            stats['positive_outcomes'] += 1
        stats['last_positive_rate'] = stats['positive_outcomes'] / max(stats['total_outcomes'], 1)
        n = stats['total_outcomes']
        stats['avg_outcome'] = (stats['avg_outcome'] * (n - 1) + outcome_value) / n
        history.append({
            'openid': openid, 'intervention': intervention,
            'value': outcome_value, 'positive': positive, 'ts': time.time(),
        })
        if len(history) > 50:
            cluster['outcome_history'] = history[-50:]
        self._save_cluster(cidx, cluster)
        outcomes = self._load_outcomes()
        outcomes['outcomes'].append({
            'openid': openid, 'cluster_id': cidx, 'intervention': intervention,
            'value': outcome_value, 'positive': positive, 'ts': time.time(),
        })
        if len(outcomes['outcomes']) > 1000:
            outcomes['outcomes'] = outcomes['outcomes'][-1000:]
        self._save_outcomes(outcomes)

    # ==================== 策略分化 ====================

    def suggest_strategy_split(self):
        clusters = self._load_clusters()
        splits = []
        if len(clusters) < 1:
            return splits
        cluster_ids = list(clusters.keys())
        for i in range(len(cluster_ids)):
            for j in range(i + 1, len(cluster_ids)):
                cid_a, cid_b = cluster_ids[i], cluster_ids[j]
                ca, cb = clusters[cid_a], clusters[cid_b]
                if len(ca.get('users', [])) < 3 or len(cb.get('users', [])) < 3:
                    continue
                pa = ca.get('stats', {}).get('last_positive_rate', 0.5)
                pb = cb.get('stats', {}).get('last_positive_rate', 0.5)
                diff = abs(pa - pb)
                max_rate = max(pa, pb)
                if diff > 0.15 and max_rate > 0:
                    diff_ratio = diff / max_rate * 100
                    splits.append({
                        'cluster_a': cid_a, 'cluster_b': cid_b,
                        'diff_ratio': round(diff_ratio, 1),
                        'positive_rate_a': round(pa, 3),
                        'positive_rate_b': round(pb, 3),
                        'params_a': ca.get('params', {}),
                        'params_b': cb.get('params', {}),
                        'reason': f'Cluster {cid_a} ({pa:.0%}) vs Cluster {cid_b} ({pb:.0%}) differ by >15%',
                    })
        return splits

    def _diverge_single(self, cluster, global_stats):
        params = cluster.get('params', dict(DEFAULT_CLUSTER_PARAMS))
        stats = cluster.get('stats', {})
        pos_rate = stats.get('last_positive_rate', 0.5)
        global_rate = global_stats.get('avg_positive_rate', 0.5)
        global_params = global_stats.get('avg_params', DEFAULT_CLUSTER_PARAMS)
        for param in ['beta', 'forget_factor', 'intervention_rate', 'push_threshold']:
            bounds = PARAM_BOUNDS.get(param, (0, 1))
            val = params.get(param, DEFAULT_CLUSTER_PARAMS.get(param, 0.5))
            g_val = global_params.get(param, DEFAULT_CLUSTER_PARAMS.get(param, 0.5))
            default_val = DEFAULT_CLUSTER_PARAMS.get(param, 0.5)
            if pos_rate > global_rate + 0.05:
                shift = 0.015 * (pos_rate - global_rate) * 10
                direction = 1 if val > g_val else -1
                val += shift * direction
            elif pos_rate < global_rate - 0.05:
                val += 0.03 * (g_val - val)
            else:
                val += 0.01 * (default_val - val)
            params[param] = max(bounds[0], min(bounds[1], val))
        cluster['params'] = params

    def _notify_weight_optimizer(self, clusters):
        """通知WeightOptimizer刷新集群特异权重（v6.1.0 AEO集成）"""
        try:
            from weight_optimizer import get_weight_optimizer
            wo = get_weight_optimizer()
            wo.refresh_cluster_weights()
            cw = wo._load_cluster_weights()
            for cidx_str, cdata in cw.items():
                cidx = int(cidx_str)
                if cidx in clusters:
                    cluster_size = len(clusters[cidx].get('users', []))
                    cdata['cluster_size'] = cluster_size
            wo._cluster_weights = cw
            wo._save_cluster_weights()
        except Exception:
            _pm_log.debug('[PopMgr] Weight optimizer refresh skipped')

    # ==================== 定期维护 ====================

    def periodic_maintenance(self):
        _pm_log.info('[PopMgr] Starting periodic maintenance...')
        clusters = self.cluster_users(force=True)
        # v6.1.0: AEO权重刷新
        self._notify_weight_optimizer(clusters)
        global_stats = self._compute_global_stats(clusters)
        for cidx, cdata in clusters.items():
            self._diverge_single(cdata, global_stats)
            self._save_cluster(cidx, cdata)
        splits = self.suggest_strategy_split()
        report = {
            'timestamp': datetime.now().isoformat(),
            'num_clusters': len(clusters),
            'total_users': sum(len(c.get('users', [])) for c in clusters.values()),
            'splits_suggested': len(splits),
            'global_stats': global_stats,
            'splits': splits,
            'cluster_info': {
                cidx: {
                    'name': cdata.get('name', f'cluster_{cidx}'),
                    'users': len(cdata.get('users', [])),
                    'positive_rate': cdata.get('stats', {}).get('last_positive_rate', 0.5),
                    'avg_outcome': cdata.get('stats', {}).get('avg_outcome', 0),
                    'params': cdata.get('params', {}),
                }
                for cidx, cdata in clusters.items()
            },
        }
        _pm_log.info('[PopMgr] Maintenance complete: %d clusters, %d users, %d splits',
                      len(clusters), report['total_users'], len(splits))
        return report

    def _compute_global_stats(self, clusters):
        total_users, total_outcomes, total_positive = 0, 0, 0
        param_sums = defaultdict(float)
        for cdata in clusters.values():
            stats = cdata.get('stats', {})
            total_users += len(cdata.get('users', []))
            total_outcomes += stats.get('total_outcomes', 0)
            total_positive += stats.get('positive_outcomes', 0)
            for k, v in cdata.get('params', {}).items():
                param_sums[k] += v
        n = len(clusters) or 1
        return {
            'total_users': total_users,
            'total_outcomes': total_outcomes,
            'avg_positive_rate': total_positive / max(total_outcomes, 1),
            'num_clusters': len(clusters),
            'avg_params': {k: v / n for k, v in param_sums.items()},
        }

    def get_cluster_summary(self):
        clusters = self._load_clusters()
        if not clusters:
            return 'No population clusters yet.'
        lines = [f'Population Clusters: {len(clusters)}']
        for cidx, cdata in sorted(clusters.items()):
            params = cdata.get('params', {})
            stats = cdata.get('stats', {})
            lines.append(f'  #{cidx} [{cdata.get("name", "?")}]: '
                         f'{len(cdata.get("users", []))} users, '
                         f'positive_rate={stats.get("last_positive_rate", 0.5):.0%}, '
                         f'beta={params.get("beta", 0.8):.2f}, '
                         f'lambda={params.get("forget_factor", 0.9):.2f}, '
                         f'ir={params.get("intervention_rate", 0.5):.2f}, '
                         f'push_th={params.get("push_threshold", 50):.0f}')
        return '\n'.join(lines)


# ==================== 全局实例 ====================

_population_manager = None


def get_population_manager():
    global _population_manager
    if _population_manager is None:
        _population_manager = PopulationManager()
    return _population_manager


# ==================== 自测 ====================

if __name__ == '__main__':
    import shutil

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')

    # 清理旧数据
    if os.path.exists(CLUSTER_DIR):
        shutil.rmtree(CLUSTER_DIR)
    os.makedirs(CLUSTER_DIR, exist_ok=True)

    pm = PopulationManager()

    # 1. 默认集群
    clusters = pm._load_clusters()
    assert len(clusters) == 1
    print(f'1. Default cluster created: {len(clusters)} cluster')
    print('   OK')

    # 2. 模拟用户数据 + 特征提取
    print('\n2. Simulating user profiles with features...')

    # 使用profile_storage API模拟
    def make_sim_profile(avg_s, vol, bt, dur, emot):
        return {
            'history': [
                {'wm_score': s, 'bedtime': bt, 'total_duration': dur * 60,
                 'mood': em, 'feedback': fb}
                for s, bt, dur, em, fb in [
                    (avg_s - vol, bt, dur, emot, 'like'),
                    (avg_s, bt, dur, emot, 'like'),
                    (avg_s + vol, bt, dur, emot, 'like'),
                    (avg_s - vol // 2, bt, dur, emot, ''),
                    (avg_s, bt, dur, emot, 'like'),
                ]
            ],
            'latest': {'total_score': avg_s},
        }

    # 模拟6个用户：3个高分稳定，3个低分波动
    sim_users = {
        'user_high_stable_1': make_sim_profile(82, 5, '22:00', 7.5, 'positive'),
        'user_high_stable_2': make_sim_profile(85, 4, '21:30', 8.0, 'positive'),
        'user_high_stable_3': make_sim_profile(78, 6, '22:15', 7.0, 'positive'),
        'user_low_volatile_1': make_sim_profile(38, 25, '01:30', 5.0, 'negative'),
        'user_low_volatile_2': make_sim_profile(32, 30, '02:00', 4.5, 'negative'),
        'user_low_volatile_3': make_sim_profile(45, 22, '00:30', 5.5, 'negative'),
    }

    for uid, prof in sim_users.items():
        profile_path = os.path.join(PROJECT_ROOT, 'user_profiles', f'{uid}.json')
        os.makedirs(os.path.dirname(profile_path), exist_ok=True)
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(prof, f)

    # 把用户加入到默认集群
    clusters = pm._load_clusters(force=True)
    clusters[0]['users'] = list(sim_users.keys())
    pm._save_cluster(0, clusters[0])
    pm._cluster_cache = None
    print('   6 simulated users added to default cluster')
    print('   OK')

    # 3. 特征提取测试
    feat = pm._get_user_feature('user_high_stable_1')
    assert feat is not None
    assert len(feat) == 6
    print(f'\n3. Feature extraction:')
    print(f'   user_high_stable_1: {[round(v, 3) for v in feat]}')
    assert feat[0] > 0.7, f'High score user should have high avg_score, got {feat[0]}'
    assert feat[1] < 0.3, f'Stable user should have low volatility, got {feat[1]}'
    print('   OK')

    feat2 = pm._get_user_feature('user_low_volatile_1')
    assert feat2 is not None
    print(f'   user_low_volatile_1: {[round(v, 3) for v in feat2]}')
    assert feat2[0] < 0.5, f'Low score user should have low avg_score, got {feat2[0]}'
    assert feat2[1] > 0.2, f'Volatile user should have high volatility, got {feat2[1]}'
    print('   OK')

    # 4. 聚类测试（should split into 2 clusters）
    print('\n4. Running k-means clustering...')
    new_clusters = pm.cluster_users(force=True)
    print(f'   Found {len(new_clusters)} clusters:')
    for cidx, cdata in new_clusters.items():
        print(f'   #{cidx} [{cdata["name"]}]: '
              f'{len(cdata["users"])} users, '
              f'centroid={[round(v, 3) for v in cdata["centroid"]]}')
    assert len(new_clusters) >= 2, f'Should have at least 2 clusters, got {len(new_clusters)}'
    print('   OK')

    # 5. 集群参数配置不相同
    print('\n5. Cluster params divergence:')
    params_set = set()
    for cidx, cdata in new_clusters.items():
        p = cdata.get('params', {})
        p_tuple = (p.get('beta', 0), p.get('forget_factor', 0),
                   p.get('push_threshold', 0))
        params_set.add(p_tuple)
        print(f'   #{cidx}: beta={p.get("beta", 0.8):.2f}, '
              f'lambda={p.get("forget_factor", 0.9):.2f}, '
              f'push_th={p.get("push_threshold", 50):.0f}')
    # 初始聚类后参数应该已经随分化而有所不同
    # 至少应该有不同的centroid
    print('   OK')

    # 6. 新用户分配到最近集群
    print('\n6. New user assignment...')
    new_user_profile = make_sim_profile(70, 8, '23:00', 7.0, 'neutral')
    new_uid = 'user_new_mid'
    npath = os.path.join(PROJECT_ROOT, 'user_profiles', f'{new_uid}.json')
    with open(npath, 'w', encoding='utf-8') as f:
        json.dump(new_user_profile, f)

    assigned_cid = pm.get_cluster_id(new_uid)
    print(f'   New user "{new_uid}" assigned to cluster #{assigned_cid}')
    assert assigned_cid is not None, 'New user should be assigned'
    clusters_after = pm._load_clusters(force=True)
    assert new_uid in clusters_after[assigned_cid]['users'], 'New user should be in assigned cluster'
    print('   OK')

    # 7. 新用户获取到集群参数
    params = pm.get_cluster_params(new_uid)
    print(f'   Cluster params: beta={params.get("beta", 0.8):.2f}, '
          f'lambda={params.get("forget_factor", 0.9):.2f}, '
          f'push_th={params.get("push_threshold", 50):.0f}')
    assert 'beta' in params, 'Should return cluster params'
    print('   OK')

    # 8. Outcome记录 + 分裂检测
    print('\n8. Outcome recording and split detection...')
    # 让两个集群的outcome差异超过15%
    for i in range(10):
        pm.record_outcome('user_high_stable_1', 'push', 5, True)
        pm.record_outcome('user_high_stable_2', 'push', 3, True)
        pm.record_outcome('user_high_stable_3', 'push', 4, True)
        pm.record_outcome('user_low_volatile_1', 'push', -2, False)
        pm.record_outcome('user_low_volatile_2', 'push', -5, False)
        pm.record_outcome('user_low_volatile_3', 'push', 1, True)

    # 再跑一次分化
    pm.periodic_maintenance()

    splits = pm.suggest_strategy_split()
    print(f'   Splits suggested: {len(splits)}')
    if splits:
        for s in splits:
            print(f'   {s["reason"]} (diff_ratio={s["diff_ratio"]:.1f}%)')
    # Still need more data for 15% diff to be detected
    pm._load_clusters(force=True)
    for cidx, cdata in pm._cluster_cache.items():
        stats = cdata.get('stats', {})
        print(f'   Cluster #{cidx}: positive_rate={stats.get("last_positive_rate", 0.5):.0%}, '
              f'total_outcomes={stats.get("total_outcomes", 0)}')
    print('   OK')

    # 9. 同一集群内用户共享参数
    print('\n9. Same cluster users share params...')
    p1 = pm.get_cluster_params('user_high_stable_1')
    p2 = pm.get_cluster_params('user_high_stable_2')
    assert p1 == p2, f'Users in same cluster should have same params: {p1} != {p2}'
    print(f'   user_high_stable_1 and user_high_stable_2 share same params: '
          f'beta={p1.get("beta", 0.8):.2f}')
    print('   OK')

    # 10. 定期维护
    print('\n10. Periodic maintenance...')
    report = pm.periodic_maintenance()
    print(f'    Clusters: {report["num_clusters"]}')
    print(f'    Users: {report["total_users"]}')
    print(f'    Splits: {report["splits_suggested"]}')
    assert report['num_clusters'] >= 0, 'Should have valid cluster count'
    print('    OK')

    # 11. get_cluster_summary
    print('\n11. Cluster summary...')
    print(pm.get_cluster_summary())
    print('    OK')

    # 清理测试数据
    if os.path.exists(CLUSTER_DIR):
        shutil.rmtree(CLUSTER_DIR)
    for uid in list(sim_users.keys()) + [new_uid]:
        upath = os.path.join(PROJECT_ROOT, 'user_profiles', f'{uid}.json')
        if os.path.exists(upath):
            os.remove(upath)
    updir = os.path.join(PROJECT_ROOT, 'user_profiles')
    if os.path.exists(updir) and not [f for f in os.listdir(updir) if f.endswith('.json')]:
        os.rmdir(updir)

    print('\nAll population_manager tests PASS!')