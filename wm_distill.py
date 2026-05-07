#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wm_distill.py — 世界模型每日蒸馏器 v1.0

职责：从 wm_experience.jsonl 经验池中学习，自动优化世界模型参数。

工作流程：
1. 读取指定日期范围的经验数据
2. 调用 DeepSeek 总结当天的睡眠模式模式
3. 基于模式调整世界模型的惩罚系数（酒精/疼痛/消化不适等）
4. 更新 world_model_config.json 持久化

用法：
  python wm_distill.py                  # 蒸馏今天的数据
  python wm_distill.py --days=7          # 蒸馏最近7天
  python wm_distill.py --date=2026-05-06 # 蒸馏指定日期
"""

import os
import json
import sys
import time
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
EXP_PATH = os.path.join(PROJECT_ROOT, 'data', 'wm_experience.jsonl')
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'data', 'world_model_config.json')

# 默认配置（蒸馏时动态调整）
DEFAULT_CONFIG = {
    'penalties': {
        'alcohol': 0.06,
        'alcohol_with_awake': 0.10,
        'digestive_discomfort': 0.04,
        'digestive_with_frequent_awake': 0.09,
        'pain_base': 0.08,
    },
    'confidence_boost': {
        'neural_fields_available': 0.05,
        'deepseek_wm_available': 0.15,
    },
    'scoring': {
        'deepseek_weight': 0.6,
        'rule_engine_weight': 0.4,
    },
    'last_distill_date': '',
}


def load_experience(days=1):
    """加载最近 N 天的经验数据"""
    if not os.path.exists(EXP_PATH):
        return []
    
    cutoff = time.time() - days * 86400
    entries = []
    with open(EXP_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get('ts', 0) >= cutoff:
                    entries.append(entry)
            except json.JSONDecodeError:
                continue
    return entries


def load_config():
    """加载当前配置"""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return dict(DEFAULT_CONFIG)


def save_config(config):
    """保存配置"""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def distill(entries, days=1):
    """蒸馏经验数据，返回配置更新建议"""
    if not entries:
        print(f'[Distill] 无经验数据，跳过蒸馏')
        return None

    print(f'[Distill] 分析 {len(entries)} 条经验记录...')

    # 统计模式
    patterns = {
        'alcohol_mentions': 0,
        'pain_mentions': 0,
        'digestive_mentions': 0,
        'awake_mentions': 0,
        'total': len(entries),
    }

    for entry in entries:
        msg = (entry.get('message', '') or '').lower()
        fields = entry.get('extracted_fields', {})
        
        if fields.get('drink') == 'alcohol' or '红酒' in msg or '喝酒' in msg or '酒精' in msg:
            patterns['alcohol_mentions'] += 1
        if fields.get('has_pain') or '痛' in msg or '不舒服' in msg:
            patterns['pain_mentions'] += 1
        if fields.get('awake_cause') in ('消化不适', 'stomach') or '肚子' in msg or '胃' in msg:
            patterns['digestive_mentions'] += 1
        if fields.get('awake_times', 0) and int(fields.get('awake_times', 0)) >= 2:
            patterns['awake_mentions'] += 1

    print(f'[Distill] 模式统计: {patterns}')

    # 生成配置更新
    config = load_config()
    config['last_distill_date'] = datetime.now().strftime('%Y-%m-%d')
    config['distill_stats'] = patterns
    config['distill_at'] = time.time()

    # 如果某个模式出现频率 > 30%，适当提高对应惩罚系数（自动学习）
    if patterns['total'] > 5:
        p = config['penalties']
        if patterns['alcohol_mentions'] / patterns['total'] > 0.3:
            old = p.get('alcohol', 0.06)
            new_val = round(min(old * 1.15, 0.12), 3)
            p['alcohol'] = new_val
            print(f'[Distill] 酒精频率 {patterns["alcohol_mentions"]}/{patterns["total"]} > 30%，惩罚系数 {old} → {new_val}')
        if patterns['digestive_mentions'] / patterns['total'] > 0.3:
            old = p.get('digestive_discomfort', 0.04)
            new_val = round(min(old * 1.15, 0.10), 3)
            p['digestive_discomfort'] = new_val
            print(f'[Distill] 消化不适频率 {patterns["digestive_mentions"]}/{patterns["total"]} > 30%，惩罚系数 {old} → {new_val}')
        if patterns['pain_mentions'] / patterns['total'] > 0.4:
            old = p.get('pain_base', 0.08)
            new_val = round(min(old * 1.1, 0.15), 3)
            p['pain_base'] = new_val
            print(f'[Distill] 疼痛频率 {patterns["pain_mentions"]}/{patterns["total"]} > 40%，惩罚系数 {old} → {new_val}')

    save_config(config)
    return config


def main():
    import argparse
    parser = argparse.ArgumentParser(description='世界模型每日蒸馏')
    parser.add_argument('--days', type=int, default=1, help='蒸馏最近N天')
    parser.add_argument('--date', type=str, default='', help='蒸馏指定日期 (YYYY-MM-DD)')
    args = parser.parse_args()

    entries = load_experience(days=args.days)
    result = distill(entries, days=args.days)
    
    if result:
        print(f'[Distill] OK, config updated')
        print(f'[Distill] Alcohol penalty: {result["penalties"]["alcohol"]}')
        print(f'[Distill] Digestive penalty: {result["penalties"]["digestive_discomfort"]}')
        print(f'[Distill] Pain penalty: {result["penalties"]["pain_base"]}')
    else:
        print(f'[Distill] Skip (no data)')


if __name__ == '__main__':
    main()
