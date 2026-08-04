#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
free_energy_tracker.py — AISleepGen 自由能最小化系统

第一性原理（Friston, 2010）：
任何智能系统的核心行为是"最小化预测误差（自由能）"。
系统不是"存储经验"，而是持续对齐预测模型与实际观测——使不确定性最小化。

功能：
1. 在 prediction_engine.record_prediction_discrepancy 之后调用
2. 维护用户级和全局级预测误差分布
3. 当误差持续偏大时，生成"预测模型校准建议"
4. 校准建议可被马尔可夫转移矩阵和反事实基线消费

数据不足时(<5条分歧记录)自动跳过。
"""
import json
import os
from datetime import datetime, timedelta

FRE_ENERGY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'feedback_loop', 'free_energy.json')


def track_discrepancy(profile, actual_score, prediction):
    """自由能追踪：记录预测误差并检查是否需要校准
    
    数据前提：prediction 中必须有 predicted_score 和 confidence
    
    算法：
    - 计算标准化误差：(实际-预测) / 预测
    - 滑动窗口维护最近10次误差
    - 如果误差均值 > 阈值 → 标记需要校准
    - 如果误差方向持续偏（5次连续同号）→ 生成主动校准指令
    
    返回: dict {
        'needs_calibration': bool,
        'free_energy': float,        # 0-1, 越大越需要校准
        'direction': str,            # 'over_predict' | 'under_predict' | 'accurate'
        'action': str,               # 建议的行动
    }
    """
    predicted = prediction.get('predicted_score', 60)
    confidence = prediction.get('confidence', 'low')
    if predicted <= 0 or actual_score <= 0:
        return {'needs_calibration': False, 'free_energy': 0,
                'direction': 'accurate', 'action': ''}

    # 标准化误差（避免评分绝对值影响）
    error = (actual_score - predicted) / max(predicted, 1)
    
    # 读取或初始化自由能记录
    fe = profile.setdefault('_free_energy', {})
    history = fe.setdefault('error_history', [])
    
    history.append({
        'ts': datetime.now().isoformat(),
        'predicted': predicted,
        'actual': actual_score,
        'error': round(error, 3),
        'confidence': confidence,
    })
    
    # 只保留最近20条
    if len(history) > 20:
        history[:] = history[-20:]
    
    # 数据不足
    if len(history) < 5:
        return {'needs_calibration': False, 'free_energy': 0.0,
                'direction': 'accurate', 'action': '数据不足'}
    
    # 计算滑动窗口误差统计
    recent = history[-10:]
    errors = [e['error'] for e in recent]
    mean_error = sum(errors) / len(errors)
    
    # 同号性检测：最近5条是否同一方向
    sign = lambda x: 1 if x > 0 else (-1 if x < 0 else 0)
    recent_signs = [sign(e) for e in errors[-5:]]
    all_positive = all(s >= 0 for s in recent_signs)
    all_negative = all(s <= 0 for s in recent_signs)
    consistent_direction = all_positive or all_negative
    
    # 绝对误差均值
    abs_errors = [abs(e) for e in errors]
    mean_abs_error = sum(abs_errors) / len(abs_errors)
    
    # 自由能 = 不确定性 + 误差幅度
    # 置信度反向映射：high=0.2, medium=0.5, low=0.8
    conf_uncertainty = {'high': 0.2, 'medium': 0.5, 'low': 0.8}.get(confidence, 0.5)
    free_energy = min(1.0, mean_abs_error * 2 + conf_uncertainty * 0.3)
    
    # 方向
    if mean_error > 0.1:
        direction = 'under_predict'  # 实际比预测好
    elif mean_error < -0.1:
        direction = 'over_predict'   # 实际比预测差
    else:
        direction = 'accurate'
    
    # 决策是否需要校准
    needs_calibration = False
    action = ''
    
    if consistent_direction and abs(mean_error) > 0.15:
        needs_calibration = True
        if all_positive:
            action = '预测偏保守：用户实际表现持续好于预测，建议上调预测基础值+5分'
        else:
            action = '预测偏乐观：用户实际表现持续差于预测，建议下调预测基础值-5分'
    elif mean_abs_error > 0.25:
        needs_calibration = True
        action = '预测波动过大：误差幅度超25%，建议增加马尔可夫转移矩阵学习权重'
    
    # 写入全局追踪文件（用于跨用户分析）
    _try_write_global(error, predicted, actual_score)
    
    fe['free_energy'] = round(free_energy, 2)
    fe['direction'] = direction
    fe['needs_calibration'] = needs_calibration
    fe['last_action'] = action
    fe['last_updated'] = datetime.now().isoformat()
    
    return {
        'needs_calibration': needs_calibration,
        'free_energy': round(free_energy, 2),
        'direction': direction,
        'action': action,
    }


def _try_write_global(error, predicted, actual):
    """写入全局自由能日志（不需要频繁写入，10条错误才写一次）"""
    try:
        d = os.path.dirname(FRE_ENERGY_FILE)
        os.makedirs(d, exist_ok=True)
        entries = []
        if os.path.exists(FRE_ENERGY_FILE):
            with open(FRE_ENERGY_FILE, 'r', encoding='utf-8') as f:
                entries = json.load(f)
        entries.append({
            'ts': datetime.now().isoformat(),
            'predicted': predicted,
            'actual': actual,
            'error': round(error, 3),
        })
        # 只保留最近1000条
        if len(entries) > 1000:
            entries[:] = entries[-1000:]
        # 每10条才写一次文件（减少IO）
        if len(entries) % 10 == 0:
            with open(FRE_ENERGY_FILE, 'w', encoding='utf-8') as f:
                json.dump(entries, f, ensure_ascii=False)
    except:
        pass


def get_global_free_energy_summary():
    """获取全局自由能概览（用于审计面板）"""
    try:
        if os.path.exists(FRE_ENERGY_FILE):
            with open(FRE_ENERGY_FILE, 'r', encoding='utf-8') as f:
                entries = json.load(f)
            if not entries:
                return {}
            errors = [e['error'] for e in entries[-50:]]
            mean_err = sum(errors) / len(errors)
            over_count = sum(1 for e in errors if e < -0.1)
            under_count = sum(1 for e in errors if e > 0.1)
            return {
                'total_entries': len(entries),
                'recent_50_mean_error': round(mean_err, 3),
                'over_predict_pct': round(over_count / len(errors) * 100, 1),
                'under_predict_pct': round(under_count / len(errors) * 100, 1),
            }
    except:
        pass
    return {}


# ===== 快速测试 =====
if __name__ == '__main__':
    test_profile = {}
    # 模拟5次持续预测偏高
    for i in range(5):
        track_discrepancy(test_profile, actual_score=55, prediction={'predicted_score': 65, 'confidence': 'medium'})
    
    fe = test_profile.get('_free_energy', {})
    print(f'自由能: {fe.get("free_energy")}')
    print(f'方向: {fe.get("direction")}')
    print(f'需要校准: {fe.get("needs_calibration")}')
    print(f'建议: {fe.get("last_action")}')
