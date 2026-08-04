# auto_diary.py v1.0 - 自动睡眠日记生成器
#
# 每天清晨自动生成：从多源数据融合 -> 自然语言日记 + 评分 + 分析
# 用户只需要点头/摇头确认偏差
#
# 数据源:
#   1. working_memory - 用户评分、情绪、干预记录
#   2. ring OCR - 手环量化数据（深睡/浅睡/REM/心率）
#   3. audio POMDP - 音频分析（鼾声/呼吸/体动/稳定性）
#   4. huawei health kit - 华为补充数据（如果有）
#   5. behavior_predictor - 趋势分析、异常检测
#
# 输出:
#   - 自然语言日记
#   - 核心指标
#   - 与历史对比
#   - 偏差标记（供用户确认）

import json, os, math
from datetime import datetime, timedelta
from collections import defaultdict

PROJECT_ROOT = r'D:\AISleepGen_Optimized'


class AutoDiary:
    """自动睡眠日记引擎"""

    def __init__(self):
        self._bp = None
        self._wm = None
        self._pomdp = None

    def _get_bp(self):
        if self._bp is None:
            from behavior_predictor import BehaviorPredictor
            self._bp = BehaviorPredictor()
        return self._bp

    def _get_wm(self):
        if self._wm is None:
            from working_memory import get_working_memory
            self._wm = get_working_memory()
        return self._wm

    def _get_pomdp(self):
        if self._pomdp is None:
            from pomdp_learner import POMDPEngine, get_engine as get_pomdp
            self._pomdp = get_pomdp()
        return self._pomdp

    def collect_sources(self, openid: str) -> dict:
        """收集所有数据源"""
        bp = self._get_bp()
        wm = self._get_wm()
        pomdp = self._get_pomdp()

        sources = {
            'working_memory': [],
            'ring': None,
            'audio': None,
            'pomdp_belief': None,
            'trend': None,
            'prediction': None,
            'diagnosis': None,
        }

        # 1. Working memory - 最近14天上下文
        if wm:
            try:
                recent = wm.recent(openid, n=14)
                sources['working_memory'] = recent or []
            except Exception:
                pass

        # 2. Ring OCR
        try:
            from ring_ocr import get_ring_extractor
            extractor = get_ring_extractor()
            ring = extractor.extract_known_values()
            if ring:
                sources['ring'] = ring
        except Exception:
            pass

        # 3. Audio POMDP
        try:
            from audio_pomdp_bridge import get_latest_audio_observation
            obs = get_latest_audio_observation(openid)
            if obs:
                sources['audio'] = obs
        except Exception:
            pass

        # 4. POMDP belief
        if pomdp:
            try:
                belief = pomdp.get_belief(openid)
                if belief:
                    sources['pomdp_belief'] = belief
            except Exception:
                pass

        # 5. Trend
        if bp:
            try:
                sources['trend'] = bp.predict_trend(openid)
                sources['prediction'] = bp.predict_tonight(openid)
            except Exception:
                pass

        return sources

    def generate_diary(self, openid: str) -> dict:
        """生成完整日记"""
        sources = self.collect_sources(openid)
        wm_entries = sources['working_memory']
        ring = sources['ring']
        audio = sources['audio']
        trend = sources['trend']
        pomdp = sources['pomdp_belief']

        # ============ 数据提取 ============

        # 从working_memory提取最近评分
        scores = []
        for e in wm_entries:
            s = e.get('score_obs')
            if s is not None and s > 0:
                ts = e.get('timestamp', '')
                scores.append({'score': s, 'date': ts[:10], 'text': e.get('text', '')})

        # 提取用户文本（非传感器消息）
        user_texts = [e.get('text', '') for e in wm_entries
                      if e.get('text', '') and '传感器' not in e.get('text', '')]

        # 提取干预记录
        interventions = [e.get('intervention', '') for e in wm_entries
                         if e.get('intervention', '') and e.get('intervention') != 'none']

        # 最新评分 & 历史均值
        last_3_scores = [s['score'] for s in scores[-3:]] if len(scores) >= 3 else [s['score'] for s in scores]
        avg_3 = sum(last_3_scores) / len(last_3_scores) if last_3_scores else 50

        # 近7天均值（不含今天）
        last_7 = [s['score'] for s in scores[-10:-3]] if len(scores) >= 10 else [s['score'] for s in scores[:-3]]
        avg_7 = sum(last_7) / len(last_7) if last_7 else 50

        # ============ 手环数据解析 ============

        ring_summary = {}
        if ring:
            ring_summary = {
                'bedtime': ring.get('bedtime', '?'),
                'waketime': ring.get('waketime', '?'),
                'total_sleep': ring.get('total_sleep_min', 0),
                'deep_sleep': ring.get('deep_sleep_min', 0),
                'light_sleep': ring.get('light_sleep_min', 0),
                'rem': ring.get('rem_min', 0),
                'awake': ring.get('awake_min', 0),
                'hr_avg': ring.get('heart_rate_avg', '?'),
                'sleep_score': ring.get('sleep_score', '?'),
            }

        # ============ 音频数据解析 ============

        audio_summary = {}
        if audio:
            raw = audio.get('_raw_audio_obs', {})
            audio_summary = {
                'duration': raw.get('duration_hours', '?'),
                'efficiency': raw.get('sleep_efficiency', '?'),
                'stability': raw.get('stability', '?'),
                'snore_pct': raw.get('snore_pct', 0),
                'movement_min': raw.get('movement_min', '?'),
                'breath_rate': raw.get('breath_rate', '?'),
            }

        # ============ 趋势分析 ============

        trend_summary = {}
        if trend:
            trend_summary = {
                'direction': trend.get('direction', 'stable'),
                'velocity': trend.get('velocity', 0),
                'acceleration': trend.get('acceleration', 0),
            }

        # ============ 评分计算 ============

        # 主评分：如果有手环评分就用手环（更客观），否则用用户评分
        primary_score = None
        score_source = 'user'

        if ring and ring.get('sleep_score') and ring['sleep_score'] > 0:
            primary_score = ring['sleep_score']
            score_source = 'ring'
        elif last_3_scores:
            primary_score = round(avg_3)
            score_source = 'average'

        # 综合评分（手环评分 + working_memory评分 加权平均）
        composite_score = 50
        if primary_score:
            composite_score = primary_score

        # ============ 数据完整度评估 ============

        completeness = 0
        total = 4
        if scores:
            completeness += 1
        if ring:
            completeness += 1
        if audio:
            completeness += 1
        if len(user_texts) > 0:
            completeness += 1
        completeness_pct = round(completeness / total * 100)

        # ============ 日记文本生成 ============

        date_str = datetime.now().strftime('%Y-%m-%d')

        # 评分描述
        if composite_score >= 80:
            score_desc = '很棒的睡眠！'
            emoji = '🌟'
        elif composite_score >= 65:
            score_desc = '不错的睡眠~'
            emoji = '😊'
        elif composite_score >= 50:
            score_desc = '睡眠一般，还有改善空间'
            emoji = '😐'
        elif composite_score >= 35:
            score_desc = '睡眠较差，需要重视'
            emoji = '😟'
        else:
            score_desc = '睡眠很差，请关注'
            emoji = '😰'

        # 睡眠时长描述
        sleep_hours_desc = ''
        if ring_summary:
            mins = ring_summary.get('total_sleep', 0)
            hours = mins / 60
            if hours >= 8:
                sleep_hours_desc = f'总睡眠{hours:.1f}小时，时长充足'
            elif hours >= 6:
                sleep_hours_desc = f'总睡眠{hours:.1f}小时，基本达标'
            else:
                sleep_hours_desc = f'总睡眠{hours:.1f}小时，偏少'

        # 深睡分析
        deep_desc = ''
        if ring_summary:
            deep_min = ring_summary.get('deep_sleep', 0)
            deep_pct = round(deep_min / ring_summary.get('total_sleep', 1) * 100, 1) if ring_summary.get('total_sleep', 0) > 0 else 0
            if deep_pct >= 30:
                deep_desc = f'深睡占比{deep_pct}%，比例理想'
            elif deep_pct >= 20:
                deep_desc = f'深睡{deep_min}分钟，占比{deep_pct}%'
            else:
                deep_desc = f'深睡仅{deep_min}分钟（{deep_pct}%），低于建议值'

        # REM分析
        rem_desc = ''
        if ring_summary:
            rem_min = ring_summary.get('rem', 0)
            if rem_min >= 60:
                rem_desc = f'REM睡眠{rem_min}分钟，正常'
            elif rem_min >= 30:
                rem_desc = f'REM{rem_min}分钟，偏短'
            else:
                rem_desc = f'REM仅{rem_min}分钟，可能未进入完整睡眠周期'

        # 心率
        hr_desc = ''
        if ring_summary and ring_summary.get('hr_avg') and ring_summary['hr_avg'] != '?':
            hr = ring_summary['hr_avg']
            if hr <= 60:
                hr_desc = f'平均心率{hr}bpm，静息状态良好'
            elif hr <= 70:
                hr_desc = f'平均心率{hr}bpm，稍偏高'
            else:
                hr_desc = f'平均心率{hr}bpm，偏高，可能压力较大'

        # 鼾声分析
        snore_desc = ''
        if audio_summary:
            snore_pct = audio_summary.get('snore_pct', 0)
            if snore_pct > 50:
                snore_desc = f'鼾声检测占比高({snore_pct:.0f}%)，可能与睡眠呼吸有关'

        # 趋势描述
        trend_desc = ''
        if trend_summary:
            d = trend_summary['direction']
            v = trend_summary['velocity']
            if d == 'improving':
                trend_desc = f'近期趋势向好（+{abs(v):.1f}分/天）'
            elif d == 'declining':
                trend_desc = f'近期趋势下降（{v:.1f}分/天），需关注'
            elif d == 'erratic':
                trend_desc = '波动较大，建议保持规律作息'
            else:
                trend_desc = '持续稳定'

        # 对比
        compare_desc = ''
        if avg_7 and scores:
            diff = round(composite_score - avg_7, 1)
            if diff > 10:
                compare_desc = f'比近7天均值({avg_7:.0f}分)高{diff:.0f}分，明显改善 🎉'
            elif diff > 3:
                compare_desc = f'比近7天均值({avg_7:.0f}分)高{diff:.0f}分'
            elif diff > -3:
                compare_desc = f'与近7天均值({avg_7:.0f}分)基本持平'
            else:
                compare_desc = f'比近7天均值({avg_7:.0f}分)低{abs(diff):.0f}分'

        # 用户反馈
        user_said = ''
        if user_texts:
            last_user = user_texts[-1] if user_texts else ''
            if '失眠' in last_user or '睡不着' in last_user or '焦虑' in last_user:
                user_said = f'用户反馈："{last_user[:40]}..."'
            elif last_user and len(last_user) < 200:
                user_said = f'用户说："{last_user[:40]}..."'

        # ============ 构建日记 ============

        diary_lines = [f'📔 {date_str} 睡眠日记']
        diary_lines.append('━' * 25)

        # 评分
        diary_lines.append(f'{emoji} {score_desc}')
        if score_source == 'ring':
            diary_lines.append(f'  评分来源：手环测量')
        elif score_source == 'average':
            diary_lines.append(f'  评分来源：历史平均')

        if composite_score:
            diary_lines.append(f'  综合评分: {composite_score}/100')

        # 时长 & 深睡 & REM
        if sleep_hours_desc:
            diary_lines.append(f'  ⏱ {sleep_hours_desc}')
        if deep_desc:
            diary_lines.append(f'  💤 {deep_desc}')
        if rem_desc:
            diary_lines.append(f'  💭 {rem_desc}')

        # 时间
        if ring_summary:
            bt = ring_summary.get('bedtime', '?')
            wt = ring_summary.get('waketime', '?')
            diary_lines.append(f'  🕐 睡眠: {bt} → {wt}')

        # 心率
        if hr_desc:
            diary_lines.append(f'  ❤ {hr_desc}')

        # 鼾声
        if snore_desc:
            diary_lines.append(f'  👃 {snore_desc}')

        # 对比
        if compare_desc:
            diary_lines.append(f'')
            diary_lines.append(f'📊 对比分析')
            diary_lines.append(f'  {compare_desc}')
            diary_lines.append(f'  {trend_desc}')
            
            # 火花趋势线
            spark_vals = [s['score'] for s in scores[-7:]] if len(scores) >= 7 else [s['score'] for s in scores]
            if spark_vals:
                spark = _sparkline(spark_vals)
                if spark:
                    diary_lines.append(f'  {spark}')
        
        # 用户反馈
        if user_said:
            diary_lines.append(f'')
            diary_lines.append(f'💬 用户笔记')
            diary_lines.append(f'  {user_said}')

        # 睡眠建议
        diary_lines.append(f'')
        diary_lines.append(f'💡 今日建议')

        if trend_summary.get('direction') == 'declining':
            diary_lines.append(f'  · 注意识别压力源，考虑增加放松时间')
        if audio_summary and audio_summary.get('snore_pct', 0) > 50:
            diary_lines.append(f'  · 鼾声偏高，建议侧卧姿势')
        if ring_summary and ring_summary.get('rem', 60) < 45:
            diary_lines.append(f'  · REM睡眠偏短，避免睡前饮酒')
        if ring_summary and ring_summary.get('total_sleep', 480) < 360:
            diary_lines.append(f'  · 睡眠时长不足，建议今晚提前上床')
        if ring_summary and ring_summary.get('deep_sleep', 60) < 60:
            diary_lines.append(f'  · 深睡不足，建议下午增加有氧运动')

        diary_lines.append('')

        diary_text = '\n'.join(diary_lines)

        # ============ 偏差标记 ============

        deviations = []
        # 用户评分vs手环评分偏差
        if scores and ring and ring.get('sleep_score'):
            user_recent = scores[-1]['score'] if scores else None
            ring_score = ring['sleep_score']
            if user_recent and abs(user_recent - ring_score) > 15:
                deviations.append({
                    'aspect': '评分偏差',
                    'user_value': user_recent,
                    'sensor_value': ring_score,
                    'detail': f'用户评分{user_recent}分 vs 手环评分{ring_score}分，偏差{abs(user_recent - ring_score)}分',
                })

        return {
            'openid': openid,
            'date': date_str,
            'generated_at': datetime.now().isoformat(),
            'composite_score': round(composite_score) if composite_score else None,
            'score_source': score_source,
            'completeness': completeness_pct,
            'sources': {
                'has_ring': ring is not None,
                'has_audio': audio is not None,
                'has_user_scores': len(scores) > 0,
                'has_user_text': len(user_texts) > 0,
            },

            'data': {
                'ring': ring_summary,
                'audio': audio_summary,
                'trend': trend_summary,
                'user_last_score': scores[-1]['score'] if scores else None,
                'user_last_text': user_texts[-1] if user_texts else None,
            },

            'diary_text': diary_text,
            'deviations': deviations,
            'version': '1.0',
        }


def format_diary_short(diary: dict) -> str:
    """简短版日记（微信推送用）"""
    openid = diary['openid']
    score = diary.get('composite_score')

    lines = []
    lines.append('📔 睡眠日记')

    if score:
        if score >= 80:
            emoji = '🌟'
        elif score >= 65:
            emoji = '😊'
        elif score >= 50:
            emoji = '😐'
        elif score >= 35:
            emoji = '😟'
        else:
            emoji = '😰'
        lines.append(f'{emoji} 评分: {score}/100')

    ring = diary.get('data', {}).get('ring', {})
    if ring:
        bt = ring.get('bedtime', '')
        wt = ring.get('waketime', '')
        total = ring.get('total_sleep', 0)
        deep = ring.get('deep_sleep', 0)
        lines.append(f'  🕐 {bt}→{wt} | 💤 {deep}min深睡 | 总{total}min')

        if ring.get('sleep_score'):
            lines.append(f'  ⌚ 手环评分{ring["sleep_score"]}')

    completeness = diary.get('completeness', 0)
    if completeness < 50:
        lines.append(f'  📡 数据完整度{completeness}%，部分数据缺失')

    if diary.get('deviations'):
        for d in diary['deviations'][:1]:
            lines.append(f'  ⚠️ {d["detail"]}')

    lines.append(f'  🆔 {openid}')
    return '\n'.join(lines)


BLOCKS = [' ', '\u2581', '\u2582', '\u2583', '\u2584', '\u2585', '\u2586', '\u2587', '\u2588']


def _sparkline(values, width=7):
    """生成紧凑火花线图（用于微信推送文本）"""
    if not values:
        return ''
    
    n = len(values)
    if n < width:
        values = values + [values[-1]] * (width - n)
    elif n > width:
        step = n / width
        values = [values[int(i * step)] for i in range(width)]
    
    mn = min(values)
    mx = max(values)
    if mx == mn:
        return '\u2585' * width + f' {values[0]:.0f}'
    
    line = ''
    for v in values:
        idx = int((v - mn) / (mx - mn) * 7)
        line += BLOCKS[min(idx, 7)]
    
    prev = values[-2] if len(values) >= 2 else values[-1]
    last = values[-1]
    direction = '+' if last > prev else ('-' if last < prev else '=')
    
    return f'{line} {last:.0f}{direction}'
