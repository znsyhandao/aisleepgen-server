"""
sleep_face_api.py — 睡眠面容分析增强版
====================================
增强现有 face_analyzer v4 的功能，新增：
1. 疲劳指数 → 干预策略映射
2. 睡前/醒后双模式
3. 和 audio_recommender 管线打通

路由注册在 dp_router.py: /api/sleep-face-analyze
"""
import os, sys, json

# ── 疲劳 → 干预策略映射表 ──
FATIGUE_PROFILES = [
    {
        'range': (0, 2),
        'level': '精力充沛',
        'emoji': '⚡',
        'color': '#00d163',
        'suggestions': [
            {'title': '轻松冥想', 'content': '精神状态好，适合5分钟正念冥想，提升入睡质量', 'type': 'meditation', 'duration': 5},
            {'title': '呼吸训练', 'content': '478呼吸法（吸气4s→屏息7s→呼气8s），让身体进入放松状态', 'type': 'breathing', 'rounds': 5},
        ]
    },
    {
        'range': (2, 4.5),
        'level': '轻度疲劳',
        'emoji': '😊',
        'color': '#4caf50',
        'suggestions': [
            {'title': 'α波白噪音', 'content': '轻度疲劳是入睡的最佳状态，推荐α波背景音（8-12Hz）', 'type': 'audio', 'audio_key': 'alpha_wave', 'duration': 30},
            {'title': '渐进式放松', 'content': '从脚趾到头顶逐渐放松全身肌肉', 'type': 'meditation', 'duration': 10},
        ]
    },
    {
        'range': (4.5, 7),
        'level': '中度疲劳',
        'emoji': '😴',
        'color': '#ff9800',
        'suggestions': [
            {'title': 'θ波助眠音乐', 'content': 'θ波音乐（4-8Hz）帮助引导到浅睡状态', 'type': 'audio', 'audio_key': 'theta_wave', 'duration': 45},
            {'title': '深呼吸引导', 'content': '鼻吸口呼，吸气4秒→呼气8秒，拉长呼气激活副交感神经', 'type': 'breathing', 'rounds': 10},
        ]
    },
    {
        'range': (7, 10),
        'level': '重度疲劳',
        'emoji': '😵',
        'color': '#e53935',
        'suggestions': [
            {'title': 'δ波深睡引导', 'content': 'δ波音乐（0.5-4Hz）加速进入深睡', 'type': 'audio', 'audio_key': 'delta_wave', 'duration': 60},
            {'title': '即刻休息', 'content': '疲劳指数过高⚠️ 建议立即准备睡觉', 'type': 'alert', 'severity': 'high'},
        ]
    }
]

# ── 醒来模式（醒后自拍） ──
WAKE_PROFILES = [
    {
        'range': (0, 3),
        'level': '恢复极佳',
        'emoji': '🌟',
        'color': '#00d163',
        'suggestions': [
            {'title': '醒来评分', 'content': '恢复度极佳！昨晚的睡眠质量很高', 'type': 'insight'},
            {'title': '记录成功习惯', 'content': '建议记录昨晚睡前做了什么，保持好习惯', 'type': 'journal'},
        ]
    },
    {
        'range': (3, 5.5),
        'level': '正常恢复',
        'emoji': '😊',
        'color': '#4caf50',
        'suggestions': [
            {'title': '睡前回顾', 'content': '恢复度正常，建议查看昨晚的睡眠录音分析', 'type': 'insight'},
        ]
    },
    {
        'range': (5.5, 7),
        'level': '欠佳',
        'emoji': '😟',
        'color': '#ff9800',
        'suggestions': [
            {'title': '休息不足', 'content': '画面显示仍有疲劳迹象，注意午间小憩', 'type': 'alert', 'severity': 'low'},
        ]
    },
    {
        'range': (7, 10),
        'level': '严重不足',
        'emoji': '🤒',
        'color': '#e53935',
        'suggestions': [
            {'title': '隐患警告', 'content': '面部疲劳指标高，建议今晚早睡', 'type': 'alert', 'severity': 'high'},
        ]
    }
]


def _map_fatigue_to_profile(fatigue_index, mode='bedtime'):
    """疲劳指数 → 干预策略"""
    profiles = WAKE_PROFILES if mode == 'wakeup' else FATIGUE_PROFILES
    for profile in profiles:
        lo, hi = profile['range']
        if lo <= fatigue_index < hi:
            return profile
    return profiles[-1]


def analyze_and_enrich(image_b64, mode='bedtime', openid='default'):
    """
    组合：face_analyzer 预测 + 干预策略映射
    返回增强版结果
    """
    try:
        from face_analyzer import analyze as _face_analyze
    except ImportError:
        return {'error': 'face_analyzer 模块未加载', 'face_detected': False}

    # 1. 让 face_analyzer 做预测
    base_result = _face_analyze(image_b64)
    if not base_result.get('face_detected'):
        return base_result

    # 2. 获取评分为疲劳指数
    score = base_result.get('predicted_score', 5.0)

    # 3. 映射到干预策略
    profile = _map_fatigue_to_profile(score, mode)

    # 4. 联调 audio_recommender 管线
    try:
        from audio_recommender import recommend_audio
        # 疲劳指数 → 疗法ID映射
        if score < 2:
            therapy_ids = ['body_scan_meditation', 'relaxation_training']
        elif score < 4.5:
            therapy_ids = ['relaxation_training', 'sleep_hygiene']
        elif score < 7:
            therapy_ids = ['sleep_restriction', 'stimulus_control']
        else:
            therapy_ids = ['stimulus_control', 'paradoxical_intention']

        audio_results = recommend_audio(therapy_ids, openid=openid, top_k=2)
        if audio_results:
            for ar in audio_results:
                profile['suggestions'].insert(0, {
                    'title': f'推荐 {ar.get("title", "助眠音频")}',
                    'content': ar.get('description', ar.get('title', '')),
                    'type': 'audio',
                    'audio_key': ar.get('key', ''),
                    'source': 'audio_recommender',
                })
    except Exception as e:
        pass  # audio_recommender 不可用时静默降级

    # 5. 组装结果
    vitality = round(max(0, min(100, (10 - score) * 10)))
    return {
        'fatigue_index': score,
        'vitality': vitality,
        'level': profile['level'],
        'emoji': profile['emoji'],
        'color': profile['color'],
        'suggestions': profile['suggestions'],
        'mode': mode,
        'face_detected': True,
        'bbox': base_result.get('bbox'),
        'details': {k: v for k, v in base_result.items() if k not in ('face_detected', 'predicted_score', 'bbox')},
    }
