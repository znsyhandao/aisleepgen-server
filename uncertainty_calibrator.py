#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
uncertainty_calibrator.py — 不确定性校准 + UA-ChatDev注入点
"""
import pickle, os, time
import math
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))

# --- 种子恢复（Kalman ensemble bootstrap）---
_kalman_history = []  # [(pred, R², timestamp)]
_ensemble_votes = []

def seed_recovery(predictions, r2_scores, timestamps=None):
    """
    从生成型推理中提取不确定性信号
    predictions: list[float] — 模型输出的预测值
    r2_scores:   list[float] — 对应R² (可来自轨道层轨道)
    """
    global _kalman_history
    if timestamps is None:
        timestamps = [time.time()] * len(predictions)
    for p, r2, t in zip(predictions, r2_scores, timestamps):
        if r2 is None:
            noise = 0.1
        else:
            noise = max(0.01, 0.25 - r2 * 0.2)
        _kalman_history.append({
            'pred': p, 'r2': r2 if r2 else 0.0,
            'noise': noise, 'ts': t
        })
    return len(_kalman_history)


def estimate_uncertainty(current_pred):
    """
    返回校准后不确定性 （std + 置信区间）
    用于UA-ChatDev注入的信号
    """
    global _kalman_history
    if not _kalman_history:
        return {'std': 0.15, 'lo': current_pred - 0.3, 'hi': current_pred + 0.3, 'label': 'low_confidence'}
    
    recent = [h for h in _kalman_history if time.time() - h['ts'] < 3600]
    if not recent:
        recent = _kalman_history[-10:]
    
    if not recent:
        return {'std': 0.15, 'lo': current_pred - 0.3, 'hi': current_pred + 0.3, 'label': 'low_confidence'}
    
    weights = np.array([1.0 / max(0.01, h['noise']) for h in recent])
    w_preds = np.array([h['pred'] for h in recent])
    
    weighted_std = np.sqrt(np.average((w_preds - np.average(w_preds, weights=weights))**2, weights=weights))
    weighted_std = float(np.clip(weighted_std, 0.01, 0.5))
    
    lo = current_pred - 1.96 * weighted_std
    hi = current_pred + 1.96 * weighted_std
    
    if weighted_std < 0.05:
        label = 'high_confidence'
    elif weighted_std < 0.12:
        label = 'medium_confidence'
    else:
        label = 'low_confidence'
    
    return {'std': weighted_std, 'lo': float(lo), 'hi': float(hi), 'label': label}


def ensemble_uncertainty(ensemble_preds):
    """
    集成预测的不确定性估计
    ensemble_preds: list[float] — 多个模型/head的输出
    """
    if len(ensemble_preds) < 2:
        return {'mean': ensemble_preds[0] if ensemble_preds else 0, 'std': 0.5, 'spread': 0}
    arr = np.array(ensemble_preds)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1))
    # 跨核心差异度
    spread = std / max(0.1, abs(mean))
    return {'mean': mean, 'std': std, 'spread': spread}


def inject_ua_calibration(chat_prompt_block):
    """
    UA-ChatDev注入：给prompt追加不确定性意识
    chat_prompt_block: str — 原始prompt
    返回: str — 带校准信号的prompt
    """
    cal = estimate_uncertainty(0)  # 0是占位，实际由调用方更新
    low = cal['lo']
    hi = cal['hi']
    label = cal['label']
    
    if label == 'high_confidence':
        ua_text = '\n[不确定性校准] 当前证据充足（std<0.05），可提供较确信的建议。'
    elif label == 'medium_confidence':
        ua_text = f'\n[不确定性校准] 不确定性中等，建议说明范围 [{low:.1f}–{hi:.1f}]，并补充保守选项。'
    else:
        ua_text = f'\n[不确定性校准] 不确定性较高，建议大幅调低置信度，标注为初步推测({low:.1f}–{hi:.1f})。'
    return chat_prompt_block + ua_text


# --- 跟 state_topology 的桥接接口 ---
def calibrate_timestep(topology_state, model_pred):
    """
    逐步校准调用（供生产用）
    topology_state: dict — 来自 state_topology.py 的拓扑状态
    model_pred: float — 当前R²预测
    """
    # 从拓扑状态提取R²
    pred_r2 = topology_state.get('current_r2', None) if isinstance(topology_state, dict) else None
    if pred_r2 is None:
        pred_r2 = model_pred
    
    seed_recovery([model_pred], [pred_r2])
    cal = estimate_uncertainty(model_pred)
    return cal


if __name__ == '__main__':
    # 自测
    print('⏱ 不确定性校准自测...')
    np.random.seed(42)
    for _ in range(50):
        seed_recovery([np.random.rand()], [np.random.rand() * 0.3])
    test_pred = 0.7
    result = estimate_uncertainty(test_pred)
    print(f'  预测={test_pred}, std={result["std"]:.4f}, 区间=[{result["lo"]:.3f},{result["hi"]:.3f}], {result["label"]}')
    
    ensemble_result = ensemble_uncertainty([0.6, 0.65, 0.72, 0.58])
    print(f'  集成预测: mean={ensemble_result["mean"]:.3f}, std={ensemble_result["std"]:.4f}, spread={ensemble_result["spread"]:.3f}')
    
    prompt = inject_ua_calibration('你的建议：')
    print(f'  UA注入: {prompt}')
    print('✅ 不确定性校准模块就绪')
