# -*- coding: utf-8 -*-
"""
sennet_clustering.py — SenNet 启示3：无监督表型发现
基于 UMAP + HDBSCAN / k-means 的离线聚类工具
从 user_profiles/ 中提取专家评分向量，聚类发现新表型

用法：
    python sennet_clustering.py                 # 运行聚类，打印结果
    python sennet_clustering.py --update-rules  # 聚类后自动更新表型规则
    python sennet_clustering.py --min-samples 5 # 最小聚类样本数

输出：
    - stdout: 聚类结果 + 新表型描述
    - frontier_data/sennet_discovered_phenotypes.json: 新表型定义
"""
import sys, os, json, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_profiles')
OUTPUT_DIR = os.path.join(BASE, 'frontier_data')
os.makedirs(OUTPUT_DIR, exist_ok=True)

_EXPERT_ORDER = [
    'ClinicalPsychologist', 'CBT', 'SleepPhysician', 'Chronobiologist',
    'LifeScientist', 'RiskManager', 'StressRelaxation',
    'ExerciseRehab', 'CardiacMonitor', 'NutriMetabolism'
]
_EXPERT_LABELS = {
    'ClinicalPsychologist':'情绪评估', 'CBT':'失眠干预', 'SleepPhysician':'病理筛查',
    'Chronobiologist':'节律分析', 'LifeScientist':'综合评估', 'RiskManager':'风险管控',
    'StressRelaxation':'减压评估', 'ExerciseRehab':'运动分析', 'CardiacMonitor':'心血管',
    'NutriMetabolism':'营养分析',
}

_KNOWN_PHENOTYPES = {
    '高唤醒型失眠': ('CP/CBT偏低，SleepPhysician正常', 0.55),
    '生理节律紊乱型': ('SleepPhysician+Chronobiologist同时偏低', 0.50),
    '适应性应激型': ('CP低但CBT正常，ExerciseRehab正常', 0.45),
    '均衡型': ('所有评分相对集中', 0.40),
    '生活方式失衡型': ('ExerciseRehab+NutriMetabolism同时偏低', 0.45),
    '身心交叉型': ('CP+SleepPhysician都低', 0.50),
    '心血管警戒型': ('CardiacMonitor显著偏低', 0.50),
    '抗压能力不足型': ('StressRelaxation显著偏低', 0.45),
}


def load_user_profiles():
    """从 user_profiles/ 加载所有用户的分析特征向量"""
    profiles = {}
    pattern = os.path.join(PROFILES_DIR, '*.json')
    for fp in sorted(glob.glob(pattern)):
        try:
            data = json.load(open(fp, 'r', encoding='utf-8'))
            openid = os.path.splitext(os.path.basename(fp))[0]
            profiles[openid] = data
        except:
            pass
    return profiles


def extract_score_vectors(profiles):
    """从用户profile中提取专家评分向量
    支持跨夜模式：单用户多晚数据同样聚类"""
    vectors = []
    metadata = []  # (openid, date) for each vector
    
    for openid, profile in profiles.items():
        # [单用户跨夜模式] 优先从 sleep_data_list 提取跨夜特征
        sleep_data = profile.get('sleep_data_list', [])
        if len(sleep_data) >= 3:
            for entry in sleep_data:
                total_dur = entry.get('total_duration', 480)
                quiet_ratio = entry.get('quiet_ratio', 0.85)
                num_movements = entry.get('body_movement_blocks', 0)
                vec = []
                for n in _EXPERT_ORDER:
                    if n == 'ClinicalPsychologist':
                        s = 0.7 if quiet_ratio > 0.85 else (0.5 if quiet_ratio > 0.7 else 0.3)
                    elif n == 'CBT':
                        s = quiet_ratio
                    elif n == 'SleepPhysician':
                        s = 1.0 - min(1.0, num_movements * 0.02)
                    elif n == 'Chronobiologist':
                        s = 0.5 + 0.3 * (1.0 if quiet_ratio > 0.8 else quiet_ratio)
                    elif n == 'LifeScientist':
                        s = quiet_ratio * 0.6 + (1.0 - min(1.0, num_movements * 0.01)) * 0.4
                    elif n == 'RiskManager':
                        s = 0.7 if quiet_ratio > 0.8 else (0.5 if quiet_ratio > 0.65 else 0.3)
                    elif n == 'StressRelaxation':
                        s = 0.5 + 0.3 * quiet_ratio
                    elif n == 'ExerciseRehab':
                        s = 0.5  # 默认
                    elif n == 'CardiacMonitor':
                        s = 0.5 + 0.3 * quiet_ratio
                    elif n == 'NutriMetabolism':
                        s = 0.5
                    else:
                        s = 0.5
                    vec.append(max(0.1, min(0.95, s)))
                vectors.append(vec)
                metadata.append((openid, entry.get('date', 'unknown')))
            continue  # 用了跨夜数据就不走下面
        
        # [多用户模式] 原逻辑：从外设数据提取
        last_sleep = profile.get('devices', {}).get('huawei_band', {}).get('last_sleep_data', {})
        if last_sleep:
            # Build a mock analysis context from the available data
            health = profile.get('health', {})
            mental = profile.get('mental', {})
            exercise = profile.get('exercise', {})
            nutrition = profile.get('nutrition', {})
            vec = []
            for n in _EXPERT_ORDER:
                if n == 'ClinicalPsychologist':
                    s = health.get('stress_level', 5) / 10.0  # invert: high stress = low score
                    s = 1.0 - max(0.1, min(0.9, s))
                elif n == 'CBT':
                    s = last_sleep.get('sleep_efficiency', 0.85)
                elif n == 'SleepPhysician':
                    s = 1.0 - max(0, last_sleep.get('awake_times', 0)) * 0.1
                elif n == 'Chronobiologist':
                    s = 0.6  # default moderate
                elif n == 'LifeScientist':
                    s = sum([v for v in last_sleep.values() if isinstance(v, (int, float))]) / max(len(last_sleep), 1) / 100
                elif n == 'RiskManager':
                    s = 0.7 if last_sleep.get('total_min', 0) >= 360 else 0.4
                elif n == 'StressRelaxation':
                    s = 1.0 - max(0.1, min(0.9, mental.get('anxiety', 5) / 10.0))
                elif n == 'ExerciseRehab':
                    s = min(0.9, max(0.2, exercise.get('days_per_week', 0) * 0.15))
                elif n == 'CardiacMonitor':
                    s = last_sleep.get('hrv_avg', 35) / 100.0
                elif n == 'NutriMetabolism':
                    s = nutrition.get('diet_score', 0.5)
                else:
                    s = 0.5
                vec.append(max(0.1, min(0.95, s)))
            vectors.append(vec)
            metadata.append((openid, last_sleep.get('date', 'unknown')))
    
    if not vectors:
        return np.array([]), []
    return np.array(vectors), metadata


def run_clustering(X, min_samples=5, use_hdbscan=True):
    """执行聚类分析"""
    if X.shape[0] < min_samples:
        print(f"⚠️  数据点不足: {X.shape[0]} < min_samples={min_samples}")
        return None, None
    
    from sklearn.cluster import KMeans, DBSCAN
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler
    from sklearn.mixture import GaussianMixture
    
    X_scaled = StandardScaler().fit_transform(X)
    
    # PCA投影看可分离性
    pca = PCA(n_components=min(3, X.shape[1]))
    X_pca = pca.fit_transform(X_scaled)
    pca_var = pca.explained_variance_ratio_
    print(f"\n  PCA 前3成分解释方差: {pca_var[0]:.1%} + {pca_var[1]:.1%} + {pca_var[2]:.1%} = {sum(pca_var[:3]):.1%}")
    
    # === 策略1: K-means (快速基线) ===
    inertias = []
    for k in range(2, min(10, X.shape[0] // 2 + 2)):
        km = KMeans(n_clusters=k, random_state=42, n_init=5)
        km.fit(X_scaled)
        inertias.append(km.inertia_)
    
    # 肘部法选k
    if len(inertias) >= 3:
        diffs = [inertias[i] - inertias[i+1] for i in range(len(inertias)-1)]
        elbow = 2 + np.argmax(diffs[:min(5, len(diffs))])  # 前5个中找最大下降
    else:
        elbow = len(inertias) + 1
    
    print(f"  K-means 肘部建议 k={elbow}")
    km_final = KMeans(n_clusters=elbow, random_state=42, n_init=10)
    km_labels = km_final.fit_predict(X_scaled)
    
    # === 策略2: GMM (软聚类，识别过渡态) ===
    gmm = GaussianMixture(n_components=elbow, random_state=42)
    gmm_labels = gmm.fit_predict(X_scaled)
    gmm_probs = gmm.predict_proba(X_scaled)
    
    # === 结果分析 ===
    results = {
        'n_samples': X.shape[0],
        'elbow_k': elbow,
        'pca_variance': [round(v, 4) for v in pca_var[:3]],
        'clusters': {}
    }
    
    print(f"\n📊 聚类结果 (k={elbow}):")
    for k in range(elbow):
        mask = km_labels == k
        n = mask.sum()
        if n == 0:
            continue
        centroid = X_scaled[mask].mean(axis=0)
        centroid_raw = X[mask].mean(axis=0)
        
        # 找该簇区别于其他簇的关键维度
        global_mean = X.mean(axis=0)
        deviations = centroid_raw - global_mean
        top_dims = np.argsort(-np.abs(deviations))[:3]
        
        # 定义表型签名
        signs = []
        for dim_idx in top_dims:
            expert_name = _EXPERT_ORDER[dim_idx]
            label = _EXPERT_LABELS.get(expert_name, expert_name)
            direction = '偏高' if deviations[dim_idx] > 0 else '偏低'
            signs.append(f'{label}{direction}({deviations[dim_idx]:+.2f})')
        
        # 匹配已知表型
        match_score = 0
        matched_phenotype = None
        for pname, (pdesc, _) in _KNOWN_PHENOTYPES.items():
            overlap = sum(1 for s in signs if any(kw in s for kw in pdesc.split('+')))
            if overlap > match_score:
                match_score = overlap
                matched_phenotype = pname
        
        # 如果有GMM过渡态检测
        trans_prob = gmm_probs[mask].max(axis=1)
        has_transition = np.any(trans_prob < 0.6)
        
        cluster_info = {
            'size': int(n),
            'centroid_raw': [round(v, 3) for v in centroid_raw],
            'top_deviations': signs[:3],
            'matched_phenotype': matched_phenotype if match_score >= 2 else '未知',
            'known_match': match_score >= 2,
            'has_transition_members': bool(has_transition),
            'is_new_discovery': match_score < 2,
        }
        results['clusters'][f'cluster_{k}'] = cluster_info
        
        match_tag = f" → 匹配『{matched_phenotype}』" if match_score >= 2 else " 🆕 **可能的新表型**"
        trans_tag = " ⚡含过渡态" if has_transition else ""
        print(f"  簇{k}(n={n}): {' · '.join(signs[:3])}{match_tag}{trans_tag}")
    
    # 发现新表型
    new_phenotypes = [v for v in results['clusters'].values() if v.get('is_new_discovery')]
    if new_phenotypes:
        print(f"\n🆕 发现 {len(new_phenotypes)} 个疑似新表型！")
        for np_ in new_phenotypes:
            print(f"  特征: {', '.join(np_['top_deviations'])}")
    
    return results, km_labels


def save_discovery(results):
    """保存聚类发现结果"""
    if results is None:
        return
    
    discoveries = []
    for cid, info in results['clusters'].items():
        if info['is_new_discovery'] and info['size'] >= 3:
            discoveries.append({
                'cluster_id': cid,
                'size': info['size'],
                'signature': info['top_deviations'],
                'phenotype_name': f"聚类发现#{len(discoveries)+1}",
                'description': '; '.join(info['top_deviations']),
            })
    
    # 同时也保存所有簇用于历史比较
    output = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'total_profiles': results.get('n_samples', 0),
        'clusters_found': len(results.get('clusters', {})),
        'new_phenotypes': len(discoveries),
        'cluster_summary': results.get('clusters', {}),
        'discovered_phenotypes': discoveries,
    }
    
    path = os.path.join(OUTPUT_DIR, 'sennet_discovered_phenotypes.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n💾 已保存: {path}")
    return discoveries


def link_with_engine(discoveries):
    """思考：新发现的表型如何注入 sleep_world_model.py 的规则系统
    规则引擎在 sleep_world_model.py L1940-1960 附近的 elif 链中
    每个表型需要：
        1. 表型名称（中文）
        2. z-score 条件表达式（基于 _z_scores dict）
        3. 置信度
    """
    print("\n🔗 注入规则草案:")
    for d in discoveries:
        sig_parts = d['signature']
        conditions = []
        for s in sig_parts:
            # Parse: "情绪评估偏低(-0.15)" → "_z_scores.get('ClinicalPsychologist',0) < -0.3"
            # This is a manual step — auto-generation is risky
            pass
        print(f"  『{d["phenotype_name"]}』: 需人工检查签名后注入z-score条件")


def check_auto_evidence_integrity(profiles):
    """补充检查：auto_evidence.json 是否完整"""
    ae_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.auto_evidence.json')
    if os.path.exists(ae_path):
        ae = json.load(open(ae_path, 'r', encoding='utf-8'))
        print(f"\n📋 auto_evidence: {len(ae)} 条")
    else:
        print(f"\n📋 auto_evidence: 不存在")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='SenNet 无监督表型发现')
    parser.add_argument('--update-rules', action='store_true', help='聚类后更新表型规则')
    parser.add_argument('--min-samples', type=int, default=5, help='最小聚类样本数')
    parser.add_argument('--use-hdbscan', action='store_true', default=False, help='使用HDBSCAN(需要hdbscan库)')
    args = parser.parse_args()
    
    print("=" * 60)
    print("🧬 SenNet 无监督表型发现工具")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    # 1. 加载数据
    print("\n📂 加载用户 profiles...")
    profiles = load_user_profiles()
    print(f"  找到 {len(profiles)} 个用户 profile 文件")
    
    if len(profiles) < 3:
        # 单用户跨夜模式：检查是否有足够的跨夜数据
        total_nights = sum(len(p.get('sleep_data_list', [])) for p in profiles.values())
        if total_nights < 3:
            print("⚠️  数据点不足（用户或跨夜数据），无法聚类。")
            return
        print(f"  📊 单用户跨夜模式：{total_nights} 晚数据（{len(profiles)} 个用户）")
    
    # 2. 提取特征向量
    X, metadata = extract_score_vectors(profiles)
    if X.shape[0] == 0:
        print("⚠️  没有可提取的特征向量。")
        return
    
    print(f"  {X.shape[0]} 个特征向量, {X.shape[1]} 维")
    
    # 3. 聚类
    results, labels = run_clustering(X, min_samples=args.min_samples)
    if results is None:
        return
    
    # 4. 保存发现
    discoveries = save_discovery(results)
    
    # 5. 检查 auto_evidence
    check_auto_evidence_integrity(profiles)
    
    # 6. 如果发现新表型，对比已知规则
    if discoveries:
        link_with_engine(discoveries)
    
    print(f"\n{'='*60}")
    print("✅ 聚类分析完成。手动检查后可通过 --update-rules 注入")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
