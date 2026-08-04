"""
ecosystem_core.py - 生态系统核心
三级反射弧 + PBT第二步(选择→借参数→变异) + Causal Transfer

PBT (Population Based Training): DeepMind 2017
  https://deepmind.google/discover/blog/population-based-training-of-neural-networks/
Causal Transfer: Pearl学派 2023 (结构因果模型跨领域复用)

核心流程：
  daily:
    1. quality_writer  ← 每个AI写评分
    2. comparator      ← 排名
    3. pbt_step        ← 好的AI的算法→差的AI的候选方案
    4. climate_reporter ← 生成环境报告
    5. cross_domain_check ← 发现可移植的范式
"""

import json, os, glob, math
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Tuple

ENV_ROOT = r'D:\shared_environment'
SPECIES_DIR = os.path.join(ENV_ROOT, 'species')
QUALITY_DIR = os.path.join(ENV_ROOT, 'quality')
CLIMATE_DIR = os.path.join(ENV_ROOT, 'climate')
DNA_DIR = os.path.join(ENV_ROOT, 'dna')


# ═══════════════════════════════════════════════════════
# 反射弧1: quality_writer — 每个AI写入评分
# ═══════════════════════════════════════════════════════

@dataclass
class QualityRecord:
    species_id: str
    score: float          # 0-1
    score_type: str       # 'self_eval' / 'accuracy' / 'user_feedback' / 'system_health'
    detail: str = ""
    timestamp: str = ""
    n_samples: int = 0    # 该评分基于多少样本

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


def write_quality(species_id: str, score: float, score_type: str = 'self_eval',
                  detail: str = '', n_samples: int = 0):
    """写入质量评分"""
    record = QualityRecord(
        species_id=species_id,
        score=max(0.0, min(1.0, score)),
        score_type=score_type,
        detail=detail,
        timestamp=datetime.now().isoformat(),
        n_samples=n_samples,
    )
    
    today = date.today().isoformat()
    day_dir = os.path.join(QUALITY_DIR, today)
    os.makedirs(day_dir, exist_ok=True)
    
    path = os.path.join(day_dir, f'{species_id}.jsonl')
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(asdict(record), ensure_ascii=False) + '\n')
    
    # 同时更新最新记录（方便快速读取）
    latest_dir = os.path.join(QUALITY_DIR, 'latest')
    os.makedirs(latest_dir, exist_ok=True)
    with open(os.path.join(latest_dir, f'{species_id}.json'), 'w', encoding='utf-8') as f:
        json.dump(asdict(record), f, ensure_ascii=False, indent=2)
    
    return record


# ═══════════════════════════════════════════════════════
# 反射弧2: comparator — 每天比较所有AI的评分
# ═══════════════════════════════════════════════════════

def scan_today_quality() -> dict:
    """扫描今天的质量评分，返回汇总"""
    today = date.today().isoformat()
    day_dir = os.path.join(QUALITY_DIR, today)
    if not os.path.exists(day_dir):
        return {}
    
    results = {}
    for fpath in glob.glob(os.path.join(day_dir, '*.jsonl')):
        species_id = os.path.basename(fpath).replace('.jsonl', '')
        scores = []
        with open(fpath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        r = json.loads(line)
                        scores.append(r['score'])
                    except:
                        pass
        if scores:
            results[species_id] = {
                'mean': sum(scores) / len(scores),
                'min': min(scores),
                'max': max(scores),
                'count': len(scores),
                'last': scores[-1],
            }
    return results


def compare_species() -> dict:
    """比较所有物种，找出最好和最差"""
    today_scores = scan_today_quality()
    
    if not today_scores:
        return {'status': 'no_data', 'message': '今天还没有质量数据'}
    
    sorted_species = sorted(today_scores.items(), key=lambda x: x[1]['mean'], reverse=True)
    
    best = sorted_species[0]
    worst = sorted_species[-1]
    
    # 加载物种名称
    species_names = {}
    for sid in today_scores:
        spath = os.path.join(SPECIES_DIR, f'{sid}.json')
        if os.path.exists(spath):
            with open(spath, 'r', encoding='utf-8') as f:
                s = json.load(f)
                species_names[sid] = s.get('name', sid)
        else:
            species_names[sid] = sid
    
    return {
        'date': date.today().isoformat(),
        'total_species': len(today_scores),
        'best': {
            'id': best[0],
            'name': species_names.get(best[0], best[0]),
            'mean_score': round(best[1]['mean'], 3),
            'count': best[1]['count'],
        },
        'worst': {
            'id': worst[0],
            'name': species_names.get(worst[0], worst[0]),
            'mean_score': round(worst[1]['mean'], 3),
            'count': worst[1]['count'],
        },
        'ranking': [
            {'id': sid, 'name': species_names.get(sid, sid),
             'mean_score': round(s['mean'], 3)}
            for sid, s in sorted_species
        ],
    }


# ═══════════════════════════════════════════════════════
# 反射弧3: climate_reporter — 环境报告 + 范式漂移检测
# ═══════════════════════════════════════════════════════

def get_algorithm_dna() -> dict:
    """读取所有AI的算法DNA"""
    dna = {}
    for fpath in glob.glob(os.path.join(DNA_DIR, '*.json')):
        sid = os.path.basename(fpath).replace('.json', '')
        with open(fpath, 'r', encoding='utf-8') as f:
            try:
                dna[sid] = json.load(f)
            except:
                dna[sid] = {'error': 'parse_failed'}
    return dna


def detect_paradigm_drift() -> list:
    """检测范式漂移：哪个算法在哪个物种表现好"""
    today_scores = scan_today_quality()
    dna = get_algorithm_dna()
    
    findings = []
    
    # 对有质量评分 + 有DNA记录的物种，分析算法效果
    for sid, score_info in today_scores.items():
        if sid not in dna:
            continue
        species_dna = dna[sid]
        algos = species_dna.get('algorithms', [])
        algo_eff = species_dna.get('effectiveness', {})
        
        for algo, eff in algo_eff.items():
            findings.append({
                'species': sid,
                'algorithm': algo,
                'effectiveness': eff,
                'overall_score': score_info['mean'],
            })
    
    # 按效果排序
    findings.sort(key=lambda x: x['effectiveness'], reverse=True)
    return findings


def generate_climate_report() -> dict:
    """生成环境报告（熔炉核心输出）"""
    species_names = {}
    for fpath in glob.glob(os.path.join(SPECIES_DIR, '*.json')):
        sid = os.path.basename(fpath).replace('.json', '')
        if sid.startswith('_'):
            continue
        with open(fpath, 'r', encoding='utf-8') as f:
            s = json.load(f)
            species_names[sid] = s.get('name', sid)
    
    comparison = compare_species()
    drift = detect_paradigm_drift()
    
    # 构建环境报告
    report = {
        'report_id': f'climate_{datetime.now():%Y%m%d_%H%M}',
        'generated_at': datetime.now().isoformat(),
        'date': date.today().isoformat(),
        'species_alive': len(species_names),
        'species_with_quality_data': comparison.get('total_species', 0) if isinstance(comparison, dict) else 0,
        
        'quality_landscape': comparison if isinstance(comparison, dict) else {'status': 'no_data'},
        
        'paradigm_drift': drift[:10] if drift else [],
        
        'findings': [],
    }
    
    # 发现：表现最好的物种用了什么算法？
    if isinstance(comparison, dict) and 'best' in comparison:
        best_id = comparison['best']['id']
        best_name = comparison['best']['name']
        best_dna = get_algorithm_dna().get(best_id, {})
        best_algorithms = best_dna.get('algorithms', [])
        if best_algorithms:
            report['findings'].append(
                f"最佳物种 [{best_name}] 使用的算法: {', '.join(best_algorithms)}"
            )
    
    # 插入PBT方案（供仪表盘决策面板用）
    try:
        from pbt_executor import load_pbt_plans
        pbt_plans = load_pbt_plans()
        report['pbt_plans'] = pbt_plans
    except:
        report['pbt_plans'] = []
    
    # 保存
    os.makedirs(CLIMATE_DIR, exist_ok=True)
    report_path = os.path.join(CLIMATE_DIR, f'{date.today().isoformat()}.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    return report


# ═══════════════════════════════════════════════════════
# PBT第2步: 选择 → 借参数 → 变异
# ═══════════════════════════════════════════════════════

# 因果骨架映射（Causal Transfer的核心）
# 定义哪些物种的"因果骨架"相似——骨架相同的可以互借鉴
# 骨架 = 输入类型 + 推理结构 + 输出类型
CAUSAL_SKELETONS = {
    # 骨架A: 状态→预测→干预（sleep/skin/meditation 共享）
    'state_predict_intervene': {
        'name': '状态诊断→预测→干预建议',
        'members': ['sleep', 'skin', 'meditation'],
        'structure': 'sensor → belief → prediction → intervention → feedback',
        'hallmark': '都有"用户状态"(隐变量)+"建议"(行动)',
    },
    # 骨架B: 信号→因果链→判断（stock/frontier 共享）
    'signal_cause_judge': {
        'name': '多发信号→因果推理→判断结论',
        'members': ['stock', 'frontier'],
        'structure': 'multi_signal → causal_chain → confidence_judgment',
        'hallmark': '都有"多探针信号"+"链式因果推理"',
    },
    # 骨架C: 自我检查→修复（healer/meta_audit 共享）
    'self_check_heal': {
        'name': '自我检查→异常检测→自动修复',
        'members': ['healer', 'meta_audit'],
        'structure': 'self_check → anomaly_detect → auto_fix → verify',
        'hallmark': '都检测自己或系统的异常状态',
    },
}


@dataclass
class PBTMutationPlan:
    """PBT变异方案（供人工审核）"""
    target_species: str          # 要改进的AI
    source_species: str          # 借鉴的AI
    skeleton_id: str             # 共享的因果骨架
    algorithm_name: str          # 借什么算法
    params: dict                 # 核心参数
    expected_improvement: float  # 预期提升
    risk_level: str              # 'low' / 'medium' / 'high'
    reason: str                  # 为什么这个方案可行
    generated_at: str = ""


@dataclass
class CausalSkeletonBridge:
    """因果骨架桥接——说明骨架A的算法怎么迁移到骨架B"""
    skeleton_id: str
    this_species: str
    target_species: str
    is_compatible: bool
    reason: str = ""
    compatibility_score: float = 0.0  # 0-1


def get_causal_skeleton(species_id: str) -> Optional[str]:
    """查找某个物种属于哪个因果骨架"""
    for skid, skeleton in CAUSAL_SKELETONS.items():
        if species_id in skeleton['members']:
            return skid
    return None


def find_best_in_skeleton(skeleton_id: str) -> Tuple[Optional[str], float]:
    """在同一个因果骨架内，找出表现最好的物种"""
    skeleton = CAUSAL_SKELETONS.get(skeleton_id)
    if not skeleton:
        return None, 0.0
    
    today_scores = scan_today_quality()
    members = skeleton['members']
    
    best_species = None
    best_score = 0.0
    
    for sid in members:
        if sid in today_scores:
            score = today_scores[sid]['mean']
            if score > best_score:
                best_score = score
                best_species = sid
    
    return best_species, best_score


def calculate_compatibility(from_species: str, to_species: str) -> CausalSkeletonBridge:
    """计算两个物种的兼容性（是否属于同一因果骨架）"""
    from_sk = get_causal_skeleton(from_species)
    to_sk = get_causal_skeleton(to_species)
    
    if from_sk and to_sk and from_sk == to_sk:
        sk = CAUSAL_SKELETONS[from_sk]
        return CausalSkeletonBridge(
            skeleton_id=from_sk,
            this_species=from_species,
            target_species=to_species,
            is_compatible=True,
            reason=f"共享因果骨架'{sk['name']}'：{sk['hallmark']}",
            compatibility_score=0.85,
        )
    elif from_sk and to_sk:
        # 不同骨架——兼容性低但仍然有可能
        return CausalSkeletonBridge(
            skeleton_id=from_sk,
            this_species=from_species,
            target_species=to_species,
            is_compatible=False,
            reason=f"不同因果骨架：{from_sk} vs {to_sk}",
            compatibility_score=0.3,
        )
    else:
        return CausalSkeletonBridge(
            skeleton_id='unknown',
            this_species=from_species,
            target_species=to_species,
            is_compatible=False,
            reason="一个或两个物种无因果骨架定义",
            compatibility_score=0.1,
        )


def pbt_step() -> List[PBTMutationPlan]:
    """PBT核心：选择→借参数→变异
    
    流程：
      1. 扫描今天所有质量分
      2. 按因果骨架分组
      3. 每组内：找最好的，找最差的
      4. 生成变异方案：差的借鉴好的参数
      5. 返回方案列表（不执行，等人审核）
    """
    today_scores = scan_today_quality()
    if len(today_scores) < 2:
        return []
    
    dna = get_algorithm_dna()
    plans = []
    
    # 按因果骨架分析
    for skid, skeleton in CAUSAL_SKELETONS.items():
        members = [m for m in skeleton['members'] if m in today_scores]
        if len(members) < 2:
            continue  # 组内不足2个物种，无法比较
        
        # 组内排名
        ranked = sorted(members, key=lambda m: today_scores[m]['mean'], reverse=True)
        best_sid = ranked[0]
        worst_sid = ranked[-1]
        best_score = today_scores[best_sid]['mean']
        worst_score = today_scores[worst_sid]['mean']
        
        # 分差太小则跳过（已经差不多）
        score_gap = best_score - worst_score
        if score_gap < 0.05:
            continue
        
        # 从best的DNA中提取可借用的算法
        best_dna = dna.get(best_sid, {})
        best_algos = best_dna.get('effectiveness', {})
        
        if not best_algos:
            # 没DNA数据——提示用户先给best注册算法
            plans.append(PBTMutationPlan(
                target_species=worst_sid,
                source_species=best_sid,
                skeleton_id=skid,
                algorithm_name=f"{best_sid}的算法组合",
                params={'需要先注册算法DNA才能精确提取参数'},
                expected_improvement=score_gap,
                risk_level='medium',
                reason=f"在同一骨架'{skeleton['name']}'中，"
                       f"[{best_sid}]({best_score:.2f})比[{worst_sid}]({worst_score:.2f})高{score_gap:.2f}分。"
                       f"但{best_sid}未注册算法DNA，无法提取具体参数。"
                       f"建议先给{best_sid}注册算法DNA。",
                generated_at=datetime.now().isoformat(),
            ))
            continue
        
        # 找出best效果最好的算法（且worst还没有）
        worst_dna = dna.get(worst_sid, {})
        worst_algos = worst_dna.get('algorithms', [])
        
        for algo_name, algo_eff in sorted(best_algos.items(), key=lambda x: -x[1]):
            if algo_eff < 0.5:
                continue  # 低于0.5的效果不值得借
            
            if algo_name not in worst_algos:
                # 算一下预期提升
                # 预期提升 = 0.5 * (best的算法效果 - worst当前分) * 兼容折扣
                expected = max(0.03, 0.5 * (algo_eff - worst_score))
                
                # 风险等级
                if algo_eff > 0.8:
                    risk = 'low'
                elif algo_eff > 0.6:
                    risk = 'medium'
                else:
                    risk = 'high'
                
                # 参数提取（从best_dna里拿）
                params = {}
                if 'params' in best_dna and isinstance(best_dna['params'], dict):
                    params = best_dna['params'].get(algo_name, {'未注册参数': '请手动确认'})
                else:
                    params = {'未注册参数': '请参考源物种代码确认核心参数'}
                
                plans.append(PBTMutationPlan(
                    target_species=worst_sid,
                    source_species=best_sid,
                    skeleton_id=skid,
                    algorithm_name=algo_name,
                    params=params,
                    expected_improvement=round(expected, 3),
                    risk_level=risk,
                    reason=f"同一骨架'{skeleton['name']}'中"
                           f"[{best_sid}]的{algo_name}(效果{algo_eff:.1%})"
                           f"比[{worst_sid}]({worst_score:.2f})高{score_gap:.2f}分。"
                           f"建议移植算法'{algo_name}'到[{worst_sid}]",
                    generated_at=datetime.now().isoformat(),
                ))
                break  # 每组只推荐一个算法（一次只做一个）
    
    return plans


# ═══════════════════════════════════════════════════════
# Cross-Domain Check: 发现不同骨架间的算法可移植性
# ═══════════════════════════════════════════════════════

def cross_domain_check() -> List[dict]:
    """跨骨架检查——虽然骨架不同，但某些算法可能仍然可移植
    
    比如：
      sleep的'稳态动力学'（原生在骨架A）可以用在stock的预测建模（骨架B）
      因为两者都是"状态序列预测"
    """
    today_scores = scan_today_quality()
    dna = get_algorithm_dna()
    findings = []
    
    # 跨骨架算法映射（预定义的已知可移植模式）
    CROSS_MAP = [
        {'paradigm': '稳态动力学', 'from_skeleton': 'state_predict_intervene',
         'to_species': ['stock'], 'reason': '市场状态也是非线性动力学系统'},
        {'paradigm': '自由能最小化', 'from_skeleton': 'state_predict_intervene',
         'to_species': ['stock'], 'reason': '预测误差+复杂度惩罚适用于任何预测系统'},
        {'paradigm': '因果链+多假设', 'from_skeleton': 'signal_cause_judge',
         'to_species': ['sleep', 'skin'], 'reason': '今日已验证——睡眠分析已成功移植'},
        {'paradigm': '置信度+校准', 'from_skeleton': 'signal_cause_judge',
         'to_species': ['skin', 'meditation'], 'reason': '推荐效果也需要预测→验证→校准'},
        {'paradigm': '元学习自审', 'from_skeleton': 'state_predict_intervene',
         'to_species': ['stock', 'frontier'], 'reason': '每日自我审查可以驱动参数自适应'},
    ]
    
    for mapping in CROSS_MAP:
        # 获取源物种的实际效果
        source_found = False
        source_eff = 0.0
        for sid, s_dna in dna.items():
            algo_effs = s_dna.get('effectiveness', {})
            if mapping['paradigm'] in algo_effs:
                source_eff = algo_effs[mapping['paradigm']]
                source_found = True
                break
            elif mapping['paradigm'] in s_dna.get('algorithms', []):
                source_found = True
                source_eff = 0.5  # 有算法但无线果数据
        
        for to_sid in mapping['to_species']:
            if to_sid in today_scores:
                target_dna = dna.get(to_sid, {})
                has_it = mapping['paradigm'] in target_dna.get('algorithms', [])
                
                findings.append({
                    'paradigm': mapping['paradigm'],
                    'source_skeleton': mapping['from_skeleton'],
                    'target_species': to_sid,
                    'source_effectiveness': round(source_eff, 3) if source_found else None,
                    'target_has_it': has_it,
                    'reason': mapping['reason'],
                    'recommend': source_found and not has_it and source_eff > 0.5,
                })
    
    return findings


def generate_cross_domain_report() -> dict:
    """生成跨域分析报告（包含PBT方案+跨骨架发现）"""
    # 1. PBT方案
    plans = pbt_step()
    
    # 2. 跨骨架发现
    cross_findings = cross_domain_check()
    
    # 3. 同一骨架内兼容性视图
    skeleton_view = {}
    for skid, skeleton in CAUSAL_SKELETONS.items():
        members = skeleton['members']
        skeleton_view[skid] = {
            'name': skeleton['name'],
            'members': members,
            'structure': skeleton['structure'],
        }
        for m in members:
            spath = os.path.join(SPECIES_DIR, f'{m}.json')
            if os.path.exists(spath):
                with open(spath, 'r', encoding='utf-8') as f:
                    s = json.load(f)
                    skeleton_view[skid].setdefault('member_names', {})[m] = s.get('name', m)
    
    report = {
        'generated_at': datetime.now().isoformat(),
        'pbt_mutation_plans': [
            {
                'target': p.target_species,
                'source': p.source_species,
                'algorithm': p.algorithm_name,
                'expected_improvement': p.expected_improvement,
                'risk': p.risk_level,
                'params': p.params,
                'reason': p.reason,
            } for p in plans
        ],
        'cross_skeleton_findings': cross_findings,
        'skeleton_view': skeleton_view,
    }
    
    # 保存到环境报告目录
    os.makedirs(CLIMATE_DIR, exist_ok=True)
    report_path = os.path.join(CLIMATE_DIR, 'cross_domain_latest.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    return report


# ═══════════════════════════════════════════════════════
# PBT第三步: 自动生成代码移植方案
# ═══════════════════════════════════════════════════════

ALGORITHM_IMPLANT_TEMPLATES = {
    '跨学科合成+自审': {
        'pattern': 'quality_audit',
        'desc': '在每次输出后对自身质量做自评，记录到日志',
        'source_file': r'D:\super_frontier_radar\generate_strategic_insider.py',
        'key_classes': [],
        'key_functions': ['_self_review', '_audit_quality'],
        'implant_code': '''
    def _self_review(self, output: dict) -> dict:
        score = 0.5
        if output.get('detail') and len(output['detail']) > 20:
            score += 0.1
        if output.get('confidence') is not None:
            score += 0.1
        if output.get('alternatives') or output.get('alternative_hypotheses'):
            score += 0.15
        score = min(1.0, score)
        if score < 0.5:
            output['warning'] = 'quality_low({:.2f})'.format(score)
        output['_quality'] = round(score, 3)
        return output
''',
        'insert_after': 'def generate',
        'risk': 'low',
        'n_lines': 15,
        'depends_on': [],
    },
    '因果链+多假设': {
        'pattern': 'causal_chain',
        'desc': '因果链+多假设跟踪+冲突检测',
        'source_file': r'D:\super_frontier_radar\brain_wallstreet\causality\chain_builder.py',
        'key_classes': ['CausalChain', 'CausalLink'],
        'key_functions': ['build', 'detect_conflicts'],
        'implant_code': '''
    @dataclass
    class CausalLink:
        event: str; dimension: str; time: str
        source: str; value: float = 0.0; confidence: float = 0.5
    @dataclass
    class CausalChain:
        chain_id: str; root_cause: str; primary_dimension: str
        links: list = None; confidence: float = 0.5
        alternative_hypotheses: list = None
    def build_causal_chains(self, data: list) -> list:
        if not data or len(data) < 3: return []
        chains = []
        return chains
    def detect_conflicts(self, chains: list) -> list:
        conflicts = []
        for i, c1 in enumerate(chains):
            for c2 in chains[i+1:]:
                if c1.confidence > 0.4 and c2.confidence > 0.4:
                    conflicts.append({
                        'dim_a': c1.primary_dimension,
                        'dim_b': c2.primary_dimension,
                        'type': 'divergent',
                        'confidence': (c1.confidence + c2.confidence) / 2,
                    })
        return conflicts
''',
        'insert_after': 'def analyze',
        'risk': 'medium',
        'n_lines': 30,
        'depends_on': ['dataclasses'],
    },
}

DOMAIN_TO_FILE = {
    'sleep': {
        'path': r'D:\AISleepGen_Optimized\sleep_diagnosis.py',
        'analysis_method': 'generate',
        'algorithms_already': ['因果链', '置信度校准'],
        'imports': ['from datetime import datetime', 'from dataclasses import dataclass'],
        'class_context': 'class SleepDiagnosis:',
    },
    'skin': {
        'path': r'D:\AISleepGen_Optimized\face_analyzer.py',
        'analysis_method': 'analyze',
        'algorithms_already': ['规则映射'],
        'imports': ['from datetime import datetime'],
        'class_context': 'class FaceAnalyzer:',
    },
    'stock': {
        'path': r'D:\super_frontier_radar\brain_wallstreet\core\signal.py',
        'analysis_method': 'process',
        'algorithms_already': ['因果链+多假设', '置信度量化+校准'],
        'imports': ['from datetime import datetime'],
        'class_context': 'class SignalAnalysis:',
    },
    'frontier': {
        'path': r'D:\super_frontier_radar\generate_strategic_insider.py',
        'analysis_method': 'generate',
        'algorithms_already': ['跨学科合成+自审'],
        'imports': ['from datetime import datetime'],
        'class_context': 'class StrategicInsider:',
    },
    'companion': {
        'path': r'D:\AISleepGen_Optimized\companion_mode.py',
        'analysis_method': 'respond',
        'algorithms_already': ['对话管理'],
        'imports': ['from datetime import datetime'],
        'class_context': 'class CompanionMode:',
    },
}


def generate_implant_plan(target_species: str, algorithm_name: str,
                          source_species: str = None,
                          source_params: dict = None) -> dict:
    """生成代码移植方案"""
    template = ALGORITHM_IMPLANT_TEMPLATES.get(algorithm_name)
    domain_info = DOMAIN_TO_FILE.get(target_species)
    if not template or not domain_info:
        return {'feasible': False, 'reason': f'无{algorithm_name}或{target_species}模板'}
    if algorithm_name in domain_info.get('algorithms_already', []):
        return {'feasible': False, 'reason': f'{target_species}已有该算法'}
    deps_ok = True
    missing_deps = []
    for dep in template.get('depends_on', []):
        if dep not in str(domain_info.get('imports', '')):
            missing_deps.append(dep)
    code_to_insert = template['implant_code']
    if source_params:
        hint = '\n        # params from ' + (source_species or 'source') + '\n'
        for k, v in source_params.items():
            hint += f'        {k} = {v if isinstance(v,(int,float)) else repr(v)}\n'
        code_to_insert = hint + code_to_insert
    return {
        'feasible': True,
        'algorithm': algorithm_name,
        'target_species': target_species,
        'target_file': domain_info['path'],
        'n_lines': template['n_lines'],
        'risk': template['risk'],
        'file_exists': os.path.exists(domain_info['path']),
        'depends_ok': deps_ok,
        'missing_deps': missing_deps,
        'insert_after': template['insert_after'],
        'code_to_insert': code_to_insert,
        'generated_at': datetime.now().isoformat(),
    }


def generate_all_implant_plans() -> list:
    """生成所有可执行移植方案"""
    plans = []
    pbt_plans = pbt_step()
    for p in pbt_plans:
        plan = generate_implant_plan(
            target_species=p.target_species,
            algorithm_name=p.algorithm_name,
            source_species=p.source_species,
            source_params=p.params if isinstance(p.params, dict) else {},
        )
        plan['trigger_from'] = 'pbt'
        plan['pbt_expected'] = p.expected_improvement
        if plan.get('feasible'):
            plans.append(plan)
    cross = cross_domain_check()
    for c in cross:
        if c.get('recommend') and not c.get('target_has_it'):
            plan = generate_implant_plan(
                target_species=c['target_species'],
                algorithm_name=c['paradigm'])
            plan['trigger_from'] = 'cross_domain'
            if plan.get('feasible'):
                plans.append(plan)
    seen = set()
    unique = []
    for p in plans:
        key = (p.get('target_species', ''), p.get('algorithm', ''))
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def save_implant_plans():
    """保存移植方案"""
    plans = generate_all_implant_plans()
    for plan in plans:
        plan['generated_at'] = datetime.now().isoformat()
    os.makedirs(CLIMATE_DIR, exist_ok=True)
    path = os.path.join(CLIMATE_DIR, 'implant_plans.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(plans, f, ensure_ascii=False, indent=2)
    return plans
    """更新某物种的算法DNA（含PBT参数）"""
    record = {
        'species_id': species_id,
        'updated_at': datetime.now().isoformat(),
        'algorithms': algorithms,
        'effectiveness': {k: round(v, 3) for k, v in effectiveness.items()},
        'params': params or {},
    }
    os.makedirs(DNA_DIR, exist_ok=True)
    with open(os.path.join(DNA_DIR, f'{species_id}.json'), 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def get_recent_quality(days: int = 7) -> dict:
    """获取最近N天的质量趋势"""
    trends = {}
    today = date.today()
    for i in range(days):
        d = today.isoformat() if i == 0 else (datetime.strptime(today.isoformat(), '%Y-%m-%d') - __import__('datetime').timedelta(days=i)).strftime('%Y-%m-%d')
        day_dir = os.path.join(QUALITY_DIR, d)
        if not os.path.exists(day_dir):
            continue
        for fpath in glob.glob(os.path.join(day_dir, '*.jsonl')):
            sid = os.path.basename(fpath).replace('.jsonl', '')
            scores = []
            with open(fpath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            scores.append(json.loads(line)['score'])
                        except:
                            pass
            if scores:
                if sid not in trends:
                    trends[sid] = {}
                trends[sid][d] = round(sum(scores) / len(scores), 3)
    return trends




def update_algo_dna(species_id: str, algorithms: list, effectiveness: dict,
                    params: dict = None):
    """更新某物种的算法DNA"""
    record = {
        'species_id': species_id,
        'updated_at': datetime.now().isoformat(),
        'algorithms': algorithms,
        'effectiveness': {k: round(v, 3) for k, v in effectiveness.items()},
        'params': params or {},
    }
    os.makedirs(DNA_DIR, exist_ok=True)
    with open(os.path.join(DNA_DIR, f'{species_id}.json'), 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def get_recent_quality(days: int = 7) -> dict:
    """获取最近N天的质量趋势"""
    trends = {}
    today = date.today()
    for i in range(days):
        d = today.isoformat() if i == 0 else (
            (datetime.strptime(today.isoformat(), '%Y-%m-%d')
             - __import__('datetime').timedelta(days=i)).strftime('%Y-%m-%d'))
        day_dir = os.path.join(QUALITY_DIR, d)
        if not os.path.exists(day_dir):
            continue
        for fpath in glob.glob(os.path.join(day_dir, '*.jsonl')):
            sid = os.path.basename(fpath).replace('.jsonl', '')
            scores = []
            with open(fpath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            scores.append(json.loads(line)['score'])
                        except:
                            pass
            if scores:
                if sid not in trends:
                    trends[sid] = {}
                trends[sid][d] = round(sum(scores) / len(scores), 3)
    return trends


if __name__ == '__main__':
    print('=== Ecosystem Core ===')
    
    # 测试写入评分
    write_quality('sleep', 0.85, 'self_eval', '今天诊断准确率85%', n_samples=12)
    write_quality('stock', 0.92, 'accuracy', '信号QC准确率92%', n_samples=48)
    write_quality('frontier', 0.78, 'self_eval', '内参质量评分78%', n_samples=3)
    
    # 测试comparator
    comp = compare_species()
    print(f'\ncomparator: {comp.get("total_species", 0)}个物种有数据')
    if 'ranking' in comp:
        for r in comp['ranking']:
            print(f'  {r["name"]:<12s} {r["mean_score"]:.3f}')
    
    # 测试算法DNA
    update_algo_dna('sleep', ['POMDP', '因果链', '置信度校准', '稳态动力学'],
                    {'POMDP': 0.82, '因果链': 0.79, '置信度校准': 0.85, '稳态动力学': 0.74})
    update_algo_dna('stock', ['因果链+多假设', '置信度量化+校准', '信号冲突检测'],
                    {'因果链+多假设': 0.90, '置信度量化+校准': 0.88, '信号冲突检测': 0.82})
    
    # 测试环境报告
    report = generate_climate_report()
    print(f'\n环境报告生成: {report["date"]}')
    if report['findings']:
        for f in report['findings']:
            print(f'  发现: {f}')
    if report['paradigm_drift']:
        print(f'  范式漂移: {len(report["paradigm_drift"])}条')
        for p in report['paradigm_drift'][:3]:
            print(f'    {p["species"]}.{p["algorithm"]} = {p["effectiveness"]}')
    
    print(f'\n=== OK ===')
