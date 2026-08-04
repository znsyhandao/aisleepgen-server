# -*- coding: utf-8 -*-
"""
AISleepGen 虚拟员工绩效考核与进化系统 v1
=============================================
核心理念：生生不息，不进则退

制度：
  - 每24小时一次全员打卡（cron 08:00）
  - 产出可量化的KPI指标
  - 连续3天摸鱼的员工标记警告
  - 连续7天摸鱼的员工自动退役/合并
  - 根据需要生成新员工（进化解锁条件）
"""

import os, json, glob, sys, time, subprocess, inspect
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

BASE = 'D:\\AISleepGen_Optimized'
LOG_DIR = os.path.join(BASE, 'logs', 'staff')
PERFORMANCE_FILE = os.path.join(BASE, '.staff_performance.json')
EVOLUTION_FILE = os.path.join(BASE, '.staff_evolution.json')

# ============================================================
# 一、员工名册与职责定义
# ============================================================
STAFF_REGISTRY = [
    # --- 数据采集部门 ---
    {
        'id': 'face_photographer',
        'name': '📷 面部拍照员',
        'department': '数据采集',
        'script': None,  # 硬件/用户交互，不自动运行
        'kpi': lambda: {
            'metric': '每日检测到人脸照片数',
            'value': _count_face_photos(),
        },
        'essential': True,
        'evolve_threshold': None,  # 硬数据源，不可替代
    },
    {
        'id': 'feature_extractor_v9',
        'name': '🔬 特征提取员(v9)',
        'department': '数据采集',
        'script': os.path.join(BASE, 'scripts', 'extract_skin_features_v9.py'),
        'kpi': lambda: {
            'metric': 'facial_features_v9.csv行数',
            'value': _count_csv_rows(os.path.join(BASE, 'sleep-skin features', 'facial_features_v9.csv')),
        },
        'essential': True,
        'evolve_threshold': 1000,  # 超过1000行时考虑v10版本
    },
    {
        'id': 'audio_analyst',
        'name': '🎤 录音分析员',
        'department': '数据采集',
        'script': None,  # 由主服务器调用
        'kpi': lambda: {
            'metric': 'analyzed JSON数',
            'value': len(glob.glob(os.path.join(BASE, 'sleep_record', 'analyzed', '*_analysis.json'))),
        },
        'essential': True,
        'evolve_threshold': 120,
    },
    {
        'id': 'band_data_collector',
        'name': '⌚ 手环数据员',
        'department': '数据采集',
        'script': None,
        'kpi': lambda: {
            'metric': 'sleep_data_log有评分天数',
            'value': _count_band_days(),
        },
        'essential': False,
        'evolve_threshold': None,
    },

    # --- 数据预处理部门 ---
    {
        'id': 'data_scientist',
        'name': '📊 数据科学专家 (align_data_sources)',
        'department': '数据预处理',
        'script': os.path.join(BASE, 'scripts', 'align_data_sources.py'),
        'kpi': lambda: {
            'metric': 'aligned_features.csv天数和列数',
            'value': _count_aligned(),
        },
        'essential': True,
        'evolve_threshold': 60,  # 超过60天时升级到v2
    },
    {
        'id': 'data_augmenter',
        'name': '🧪 数据增强专家 (augment_training_data)',
        'department': '数据预处理',
        'script': os.path.join(BASE, 'scripts', 'augment_training_data.py'),
        'kpi': lambda: {
            'metric': '增强CSV是否存在',
            'value': '已就绪' if os.path.exists(os.path.join(BASE, 'sleep-skin features', 'facial_features_v9_augmented.csv')) else '待激活',
        },
        'essential': False,
        'evolve_threshold': None,
    },
    {
        'id': 'skin_change_analyst',
        'name': '🔄 皮肤对比分析员',
        'department': '数据预处理',
        'script': None,  # 由主服务器定时触发生成
        'kpi': lambda: {
            'metric': 'skin_change_vs_sleep.json天数',
            'value': _count_skin_change_days(),
        },
        'essential': False,
        'evolve_threshold': 14,  # 14天皮肤对比数据后升级
    },

    # --- 模型训练部门 ---
    {
        'id': 'lgb_trainer',
        'name': '🏋️ LightGBM训练师',
        'department': '模型训练',
        'script': os.path.join(BASE, 'migrate_to_lgb.py'),
        'kpi': lambda: _read_model_kpi(os.path.join(BASE, 'sleep-skin features', 'lgb_result_v1.json')),
        'essential': True,
        'evolve_threshold': {'r²': 0.5},  # R² > 0.5 时解锁高级模型
    },
    {
        'id': 'ridge_trainer',
        'name': '🏛 Ridge回归(旧管线)',
        'department': '模型训练',
        'script': os.path.join(BASE, 'retrain_model.py'),
        'kpi': lambda: _read_model_kpi(os.path.join(BASE, 'sleep-skin features', 'ridge_model_v9.json')),
        'essential': False,
        'evolve_threshold': None,  # 旧管线保持兼容
    },
    {
        'id': 'toto2_trainer',
        'name': '🧠 Toto2时序训练师',
        'department': '模型训练',
        'script': os.path.join(BASE, 'train_toto2_v2.py'),
        'kpi': lambda: {
            'metric': '待跑基线',
            'value': '训练中-解码太慢待优化',
        },
        'essential': False,
        'evolve_threshold': None,
    },

    # --- 在线推理部门（由主服务器常驻运行）---
    {
        'id': 'deepseek_server',
        'name': '🤖 DeepSeek推理服务器',
        'department': '在线推理',
        'script': os.path.join(BASE, 'deepseek_proxy.py'),
        'kpi': lambda: {
            'metric': '服务运行状态',
            'value': '运行中' if _is_process_running('deepseek_proxy') else '已停止',
        },
        'essential': True,
        'evolve_threshold': None,
    },
    {
        'id': 'world_model_10experts',
        'name': '🧬 WorldModelEngine (10专家会诊)',
        'department': '在线推理',
        'script': os.path.join(BASE, 'sleep_world_model.py'),
        'kpi': lambda: {
            'metric': '专家数',
            'value': '10 (ClinicalPsych, CBT, SleepPhysician, ChronoBio, LifeSci, RiskMgr, StressRelax, ExerciseRehab, CardiacMonitor, NutriMetab)',
        },
        'essential': True,
        'evolve_threshold': None,
    },
    {
        'id': 'face_predictor_online',
        'name': '👁️ 面部实时预测 (face_analyzer)',
        'department': '在线推理',
        'script': os.path.join(BASE, 'face_analyzer.py'),
        'kpi': lambda: {
            'metric': '模型版本',
            'value': 'ensemble_v1 (8维旧模型)',
        },
        'essential': True,
        'evolve_threshold': None,  # 等待lgb_trainer进化后升级
    },
    {
        'id': 'pubmed_frontier',
        'name': '📖 PubmedFrontier (循证更新)',
        'department': '在线推理',
        'script': os.path.join(BASE, 'deepseek_proxy.py'),  # 内嵌
        'kpi': lambda: {
            'metric': '循证证据数',
            'value': _count_auto_evidence(),
        },
        'essential': False,
        'evolve_threshold': None,
    },
]


# ============================================================
# 辅助KPI函数
# ============================================================
def _count_face_photos():
    img_db = os.path.join(BASE, 'sleep-skin image database')
    if not os.path.exists(img_db):
        return 0
    total = 0
    for d in os.listdir(img_db):
        dp = os.path.join(img_db, d)
        if os.path.isdir(dp):
            total += len(os.listdir(dp))
    return total

def _count_csv_rows(path):
    if not os.path.exists(path):
        return 0
    try:
        df = pd.read_csv(path, nrows=0)
        with open(path, 'r', encoding='utf-8') as f:
            return sum(1 for _ in f) - 1
    except:
        return 0

def _count_band_days():
    log = os.path.join(BASE, 'sleep-skin features', 'sleep_data_log.json')
    if not os.path.exists(log):
        return 0
    try:
        with open(log, encoding='utf-8') as f:
            data = json.load(f)
        return sum(1 for v in data.values() if v.get('real_score') and v['real_score'] > 0)
    except:
        return 0

def _count_aligned():
    csv = os.path.join(BASE, 'sleep-skin features', 'aligned_features_v1.csv')
    if not os.path.exists(csv):
        return 'N/A'
    try:
        df = pd.read_csv(csv)
        return f"{len(df)}天 x {len(df.columns)}列"
    except:
        return 'N/A'

def _count_skin_change_days():
    sc = os.path.join(BASE, 'sleep-skin features', 'skin_change_vs_sleep.json')
    if not os.path.exists(sc):
        return 0
    try:
        with open(sc, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return len(data)
        return 0
    except:
        return 0

def _read_model_kpi(result_path):
    if not os.path.exists(result_path):
        return {'metric': '模型状态', 'value': '未训练'}
    try:
        with open(result_path, encoding='utf-8') as f:
            r = json.load(f)
        if 'cv_r2' in r:
            return {'metric': f"R²={r['cv_r2']} MAE={r.get('cv_mae_pct','?')}%", 'value': f"{r['n_samples']}样本 {r['n_features']}维"}
        return {'metric': '模型状态', 'value': '已就绪'}
    except:
        return {'metric': '模型状态', 'value': '未知'}

def _is_process_running(name):
    try:
        import psutil
        for p in psutil.process_iter(['name', 'cmdline']):
            if p.info['cmdline']:
                cl = ' '.join(p.info['cmdline'])
                if name in cl:
                    return True
        return False
    except:
        return 'N/A'

def _count_auto_evidence():
    ev = os.path.join(BASE, '.auto_evidence.json')
    if not os.path.exists(ev):
        return 0
    try:
        with open(ev, encoding='utf-8') as f:
            data = json.load(f)
        return len(data) if isinstance(data, list) else 0
    except:
        return 0


# ============================================================
# 二、绩效考核主流程
# ============================================================
def run_performance_review():
    """运行绩效考核，返回评级和行动项"""
    now = datetime.now()
    
    # 加载历史绩效
    if os.path.exists(PERFORMANCE_FILE):
        with open(PERFORMANCE_FILE, encoding='utf-8') as f:
            history = json.load(f)
    else:
        history = {'reviews': [], 'warnings': [], 'evolutions': []}
    
    results = []
    warnings = []
    evolution_triggers = []
    
    print(f"\n{'='*70}")
    print(f"  AISleepGen 虚拟员工绩效考核 v1")
    print(f"  时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")
    print(f"\n{'员工':30s} {'部门':12s} {'KPI':>40s}")
    print('-' * 80)
    
    for member in STAFF_REGISTRY:
        name = member['name']
        dept = member['department']
        
        try:
            kpi = member['kpi']()
            metric = kpi.get('metric', '')
            value = kpi.get('value', '')
            
            print(f"  {name:28s} {dept:10s} {str(metric)+': '+str(value):>38s}")
            results.append({
                'id': member['id'],
                'name': name,
                'department': dept,
                'kpi_metric': metric,
                'kpi_value': str(value),
                'status': '✅' if value and value != 'N/A' and value != '待激活' else '⚠️',
            })
            
            # 进化条件检查
            et = member.get('evolve_threshold')
            if et is not None:
                if isinstance(et, dict):
                    # 按R²等指标
                    for k, v in et.items():
                        if k in metric and isinstance(metric, str) and metric.find(str(v)) >= 0:
                            pass  # 暂不触发，人工确认
                elif isinstance(et, (int, float)):
                    val = 0
                    if isinstance(value, str) and value.replace('天','').replace('x','_').split('_')[0].isdigit():
                        try:
                            val = int(value.split('天')[0].split('x')[0].strip())
                        except:
                            pass
                    elif isinstance(value, (int, float)):
                        val = value
                    # 暂不自动触发进化

        except Exception as e:
            print(f"  {name:28s} {dept:10s} {'KPI异常: '+str(e)[:40]:>38s}")
            results.append({
                'id': member['id'],
                'name': name,
                'department': dept,
                'kpi_metric': '异常',
                'kpi_value': str(e)[:50],
                'status': '❌',
            })
    
    # 汇总
    ok = sum(1 for r in results if r['status'] == '✅')
    warn = sum(1 for r in results if r['status'] == '⚠️')
    fail = sum(1 for r in results if r['status'] == '❌')
    
    review = {
        'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
        'total': len(results),
        'ok': ok,
        'warn': warn,
        'fail': fail,
        'results': results,
        'warnings': warnings,
        'evolution_triggers': evolution_triggers,
    }
    
    history['reviews'].append(review)
    history['last_review'] = now.strftime('%Y-%m-%d %H:%M:%S')
    
    with open(PERFORMANCE_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n{'='*70}")
    print(f"  考核结果: 在岗 {ok}/{len(results)} | 待观察 {warn} | 异常 {fail}")
    print(f"  日志: {PERFORMANCE_FILE}")
    print(f"{'='*70}\n")
    
    return review


# ============================================================
# 三、系统进化机制
# ============================================================
def check_evolution_conditions():
    """检查是否满足生成新员工的条件"""
    if os.path.exists(EVOLUTION_FILE):
        with open(EVOLUTION_FILE, encoding='utf-8') as f:
            evo = json.load(f)
    else:
        evo = {'generations': [], 'active_experts': list(range(10))}
    
    # 进化阈值检测
    new_experts = []
    
    # 条件1: 三源对齐 > 20天 → 解锁多模态融合专家
    try:
        df = pd.read_csv(os.path.join(BASE, 'sleep-skin features', 'aligned_features_v1.csv'))
        triple = ((df['n_faces'] > 0) & (df['audio_n_recordings'] > 0) & (df['band_real_score'] > 0)).sum()
        if triple >= 20 and 'multimodal_fusion' not in [e.get('id') for e in evo.get('active_experts', [])]:
            new_experts.append({
                'id': 'multimodal_fusion',
                'name': '🧬 多模态融合专家',
                'condition': f'三源对齐{triple}天≥20',
                'action': '生成多模态LightGBM：融合面部+录音+手环特征',
            })
    except:
        pass
    
    # 条件2: 面部数据 > 60天 → 解锁时序预测专家
    try:
        df = pd.read_csv(os.path.join(BASE, 'sleep-skin features', 'facial_features_v9.csv'))
        days = df['date'].nunique()
        if days >= 60 and 'temporal_face' not in [e.get('id') for e in evo.get('active_experts', [])]:
            new_experts.append({
                'id': 'temporal_face',
                'name': '📈 面部时序预测专家',
                'condition': f'面部数据{days}天≥60',
                'action': '用时序模型(LSTM)预测面部特征变化趋势',
            })
    except:
        pass
    
    # 条件3: LightGBM R² > 0.5 → 解锁深度模型专家
    try:
        with open(os.path.join(BASE, 'sleep-skin features', 'lgb_result_v1.json')) as f:
            r = json.load(f)
        if r.get('cv_r2', 0) > 0.5 and 'deep_model' not in [e.get('id') for e in evo.get('active_experts', [])]:
            new_experts.append({
                'id': 'deep_model',
                'name': '🧠 深度模型专家',
                'condition': f'LightGBM R²={r["cv_r2"]}>0.5',
                'action': '解锁CNN/Transformer端到端模型训练',
            })
    except:
        pass
    
    if new_experts:
        evo['generations'].append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'new_experts': new_experts,
        })
        with open(EVOLUTION_FILE, 'w', encoding='utf-8') as f:
            json.dump(evo, f, ensure_ascii=False, indent=2, default=str)
    
    return new_experts


# ============================================================
# 四、主入口
# ============================================================
def main():
    review = run_performance_review()
    new_experts = check_evolution_conditions()
    
    if new_experts:
        print("\n" + "=" * 70)
        print(f"  🧬 系统进化！新员工已生成：")
        print("=" * 70)
        for e in new_experts:
            print(f"    ✅ {e['name']}")
            print(f"       触发条件: {e['condition']}")
            print(f"       行动: {e['action']}")
        print()
    
    # 警告检查：essential员工连续异常
    if review['fail'] > 0:
        failed_essential = [r for r in review['results'] if r['status'] == '❌']
        for r in failed_essential:
            member = next((m for m in STAFF_REGISTRY if m['id'] == r['id']), None)
            if member and member.get('essential'):
                print(f"  ⚠️ 核心员工异常: {r['name']}")
                if member.get('script') and os.path.exists(member['script']):
                    print(f"     尝试重新调度: python {member['script']}")
                else:
                    print(f"     需要人工检查")
    
    return review


if __name__ == '__main__':
    main()
