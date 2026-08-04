#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
biofeedback.py — 生物反馈异步处理（从 deepseek_proxy.py 拆出）
包含：AI 回复生成主流程、场景感知、偏好引擎
"""
import os, json, sys, time, traceback
from datetime import datetime

# 父目录（deepseek_proxy.py 所在目录）
BASE = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 场景感知
# ============================================================
SCENE_CLASSIFIERS = {
    'night_waking': ['夜醒', '夜里醒', '半夜', '醒了睡不着', '3点', '4点', '凌晨'],
    'morning': ['早上', '醒了', '起床', '昨晚睡得'],
    'pain': ['头痛', '背痛', '腰痛', '肩颈', '酸痛', '疼痛'],
    'snore': ['打鼾', '打呼', '呼吸暂停', '憋醒'],
    'stress': ['压力', '焦虑', '考试', '工作多', '加班', '睡不着'],
    'feedback': ['建议', '不好', '不满意', '差', '改进'],
    'greeting': ['你好', '嗨', 'hello', 'hi', '在吗', '在不在'],
}

def classify_scene(message: str) -> dict:
    """对用户输入做场景分类"""
    for scene, keywords in SCENE_CLASSIFIERS.items():
        for kw in keywords:
            if kw in message:
                return {'scene': scene, 'desc': scene, 'confidence': max(0.3, 1.0 - 0.1 * (len(message) / 100))}
    return {'scene': 'general', 'desc': '日常咨询', 'confidence': 0.5}


# ============================================================
# 纵向对比
# ============================================================
def vertical_comparison(profile: dict) -> dict:
    """对用户历史数据做纵向对比"""
    history = profile.get('history', [])
    scored = [h for h in history if h.get('wm_score', 0) > 0]
    if not scored:
        return {}
    scored.sort(key=lambda x: x.get('date', ''), reverse=True)
    today_score = scored[0].get('wm_score', 0) if scored else 0
    yesterday_score = scored[1].get('wm_score', 0) if len(scored) > 1 else 0
    week_scores = scored[:min(7, len(scored))]
    week_avg = round(sum(s.get('wm_score', 0) for s in week_scores) / len(week_scores), 1) if week_scores else 0
    trend = 'improving' if today_score > week_avg else ('declining' if today_score < week_avg else 'stable')
    return {'today_score': today_score, 'yesterday_score': yesterday_score, 'week_avg': week_avg, 'trend': trend}


# ============================================================
# 偏好引擎 API
# ============================================================
def _pref_api_call(method: str, endpoint: str, data: dict = None) -> dict:
    """调用偏好引擎的API（内部，不暴露到路由）"""
    # 偏好引擎不依赖外部API，直接返回空结果
    return {'success': False, 'error': '偏好引擎未启用'}
