#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paper_digestion_pipeline.py — 论文消化链 v1

职责：前沿扫描的论文不浪费。
工作原理：
  1. 从 scanned_papers_db.json 读取未消化的论文
  2. 关键词匹配 → 系统参数维度映射
  3. 匹配到维度 → 生成实验建议（写入实验平台bridge格式）
  4. 记录已消化状态，不重复

就像读了很多书，然后真的用上书里的东西。
"""

import json, os, time, re, sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\AISleepGen_Optimized'
FRONTIER = r'D:\super_frontier_radar'
SCANNED_DB = os.path.join(FRONTIER, 'frontier_data', 'scanned_papers_db.json')
DIGEST_DB = os.path.join(FRONTIER, 'frontier_data', 'digested_papers.json')
BRIDGE_FILE = os.path.join(FRONTIER, 'frontier_data', '_for_xiaotiantian_bridge.json')
EFFECTS_DIR = os.path.join(BASE, 'data', 'experiments')
CAL_FILE = os.path.join(EFFECTS_DIR, 'calibration.json')

# ═══ 论文概念 → 系统参数维度的映射表 ═══
# 关键词 → (参数路径, 建议, 置信度)
CONCEPT_MAP = [
    # 记忆/Agent
    (r'(?i)(memory|agent|long.?term|persistent)', 
     'calibration._memory_config', 
     '论文提示记忆层可提升Agent成功率至82%，考虑增加轨迹模型记忆持久化', 
     0.7),
    
    # 不确定性
    (r'(?i)(uncertainty|confidence|calibration|quantif)',
     'calibration._uncertainty_config',
     '论文关于不确定性量化方法，可对比当前ensemble方法的校准效果',
     0.6),
    
    # 睡眠阶段/分类
    (r'(?i)(sleep.?stage|sleep.?classif|hypnogram|EEG.?sleep)',
     'calibration._sleep_stage_config',
     '新睡眠阶段分类方法报道，考虑对比当前规则引擎',
     0.5),
    
    # 循环/节律
    (r'(?i)(circadian|rhythm|cycle|periodic|oscillat)',
     'calibration._circadian_config',
     '节律模型新发现，当前昼夜节律相位模型是否需要更新参数',
     0.6),
    
    # 预测/推理
    (r'(?i)(predict|forecast|trajectory|anticipat)',
     'calibration._prediction_config',
     '论文提出新预测方法，当前轨迹模型参数是否需要调整',
     0.5),
    
    # 强化学习/策略
    (r'(?i)(reinforcement|policy|RL|GRPO|PPO|reward)',
     'calibration._rl_config',
     '新强化学习方法报道，当前meta-rl策略可考虑注入',
     0.6),
    
    # 时间序列
    (r'(?i)(time.?series|temporal|sequence|LSTM|transformer)',
     'calibration._temporal_config',
     '新时间序列模型报道，当前时序分析架构可对比',
     0.4),
    
    # 音频/语音
    (r'(?i)(audio|speech|ASR|voice|whisper)',
     'calibration._audio_config',
     '新音频处理方法报道，当前语音分析模块可对比',
     0.5),
    
    # 扩散模型
    (r'(?i)(diffusion|generative|video.?gen|scene.?gen)',
     'calibration._generative_config',
     '扩散模型新进展，是否可用于睡眠音频生成',
     0.3),
    
    # 世界模型
    (r'(?i)(world.?model|embodied|manipulation|robot)',
     'calibration._world_model_config',
     '世界模型新架构报道，可对比当前世界模型的表示学习',
     0.4),
]


def _log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] [Digestion] {msg}')


def _load_db():
    """加载未消化的论文库"""
    if not os.path.exists(SCANNED_DB):
        return []
    try:
        with open(SCANNED_DB, 'r', encoding='utf-8') as f:
            db = json.load(f)
    except:
        return []
    papers = db.get('scanned_papers', [])
    
    # 加载已消化列表
    digested_ids = set()
    if os.path.exists(DIGEST_DB):
        try:
            with open(DIGEST_DB, 'r', encoding='utf-8') as f:
                digested = json.load(f)
            digested_ids = set(digested.get('digested_ids', []))
        except:
            pass
    
    # 过滤出未消化
    undigested = [p for p in papers if p.get('id') not in digested_ids]
    return undigested, digested_ids


def _save_digested(digested_ids):
    os.makedirs(os.path.dirname(DIGEST_DB), exist_ok=True)
    with open(DIGEST_DB, 'w', encoding='utf-8') as f:
        json.dump({'digested_ids': list(digested_ids), 'updated_at': time.time()}, 
                  f, ensure_ascii=False, indent=2)


def _load_calibration():
    """加载当前校准参数"""
    if not os.path.exists(CAL_FILE):
        return {}
    try:
        with open(CAL_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}


def _match_paper(paper):
    """单篇论文概念匹配"""
    title = paper.get('title', '')
    summary = paper.get('summary', '')
    combined = title + ' ' + summary
    
    matches = []
    for pattern, param_path, suggestion, confidence in CONCEPT_MAP:
        if re.search(pattern, combined):
            matches.append({
                'param_path': param_path,
                'suggestion': suggestion,
                'confidence': confidence,
                'matched_pattern': pattern,
            })
    
    return matches


def _generate_experiment_proposal(paper, primary_match):
    """为匹配到参数的论文生成实验提案"""
    experiment_id = f'paper_digest_{abs(hash(paper.get("id","")) % 100000):06d}'
    
    # 尝试读取当前参数值
    cal = _load_calibration()
    param_path = primary_match['param_path']
    current_value = cal.get(param_path, None)
    
    proposal = {
        'source': 'paper_digestion',
        'experiment_id': experiment_id,
        'paper_title': paper.get('title', ''),
        'paper_id': paper.get('id', ''),
        'knob_key': param_path,
        'current_value': current_value,
        'suggestion': primary_match['suggestion'],
        'confidence': primary_match['confidence'],
        'proposed_change': f'论文启发: {primary_match["suggestion"][:80]}',
        'digested_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }
    return proposal


def digest():
    """
    主消化入口：读取未消化论文 → 概念匹配 → 生成实验建议
    
    返回: 新产生的实验提案列表
    """
    undigested, digested_ids = _load_db()
    if not undigested:
        _log('无新论文需要消化')
        return []
    
    _log(f'检查 {len(undigested)} 篇未消化论文')
    proposals = []
    
    for paper in undigested:
        matches = _match_paper(paper)
        if matches:
            # 取最高置信度匹配
            best = max(matches, key=lambda m: m['confidence'])
            proposal = _generate_experiment_proposal(paper, best)
            proposals.append(proposal)
            _log(f'消化: {paper.get("title","")[:50]}... → {best["param_path"]}')
        
        # 不管有没有匹配都标记已消化（不重复处理）
        digested_ids.add(paper.get('id'))
    
    _save_digested(digested_ids)
    
    # 写入bridge文件，供实验平台使用
    if proposals:
        bridge = {
            'source': 'paper_digestion',
            'timestamp': time.time(),
            'proposals': proposals,
        }
        os.makedirs(os.path.dirname(BRIDGE_FILE), exist_ok=True)
        with open(BRIDGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(bridge, f, ensure_ascii=False, indent=2)
        _log(f'提案写入: {BRIDGE_FILE} ({len(proposals)}条)')
    
    return proposals


if __name__ == '__main__':
    print('论文消化链 v1')
    print('=' * 40)
    props = digest()
    print(f'\n消化结果: {len(props)} 个实验提案')
    if props:
        for p in props:
            print(f'  → [{p["confidence"]:.1f}] {p["paper_title"][:50]}')
            print(f'     knob={p["knob_key"]}')
            print(f'     建议: {p["suggestion"][:60]}')
    else:
        print('  (所有论文已消化或没有匹配概念)')
