# sleep_diagnosis.py v1.0 — 睡眠诊断书生成器
# 把POMDP信念 + 趋势 + 相关性 + 多源数据 → 一份可阅读的"诊断报告"
#
# 输入：openid
# 输出：dict（可直接转微信卡片）
#
# 集成点：
#   - pomdp_learner.get_belief()         — 当前信念
#   - behavior_predictor.predict_trend() — 趋势分析
#   - working_memory.recent()            — 原始数据
#   - sleep_audio_analyzer               — 音频数据（如果有）
#   - ring_ocr                           — 手环数据（如果有）

import json, os, math
from datetime import datetime, timedelta
from collections import Counter

PROJECT_ROOT = r'D:\AISleepGen_Optimized'


class SleepDiagnosis:
    """睡眠诊断书"""

    def __init__(self):
        self._bp = None
        self._wm = None

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

    def generate(self, openid: str) -> dict:
        """生成完整诊断书"""
        bp = self._get_bp()
        wm = self._get_wm()

        # 1. 基础数据
        recent = []
        if wm:
            try:
                recent = wm.recent(openid, n=14)
            except Exception:
                pass

        trend = bp.predict_trend(openid)
        baseline = bp.predict_tonight(openid)
        anomaly = bp.anomaly_score(openid)
        patterns = bp.detect_patterns(openid)

        # 2. 提取分数序列
        scores = []
        sleep_times = []
        for e in recent:
            s = e.get('score_obs')
            if s is not None:
                ts = e.get('timestamp', '')
                scores.append((ts[:10], s))
                sleep_times.append(e.get('bedtime', ''))

        # 3. 计算关键指标
        n_days = len(scores)
        if scores:
            recent_scores = [s for _, s in scores[-3:]]
            all_scores = [s for _, s in scores]
            recent_avg = sum(recent_scores) / len(recent_scores) if recent_scores else 50
            overall_avg = sum(all_scores) / len(all_scores) if all_scores else 50
            score_std = self._std(all_scores) if len(all_scores) >= 2 else 0
            min_score = min(all_scores) if all_scores else 0
            max_score = max(all_scores) if all_scores else 100
        else:
            recent_avg = overall_avg = 50
            score_std = min_score = max_score = 0

        # 4. 睡眠规律性
        bedtime_consistency = 'unknown'
        if len(sleep_times) >= 3:
            valid = [t for t in sleep_times if t]
            if len(valid) >= 3:
                # 将时间转换为分钟
                minutes = []
                for t in valid:
                    try:
                        h, m = t.split(':')
                        minutes.append(int(h) * 60 + int(m))
                    except Exception:
                        pass
                if len(minutes) >= 3:
                    self._std_times = self._std(minutes)
                    if self._std_times <= 30:
                        bedtime_consistency = 'excellent'
                    elif self._std_times <= 60:
                        bedtime_consistency = 'good'
                    elif self._std_times <= 90:
                        bedtime_consistency = 'fair'
                    else:
                        bedtime_consistency = 'poor'

        # 5. 趋势评估
        velocity = trend.get('velocity', 0)
        acceleration = trend.get('acceleration', 0)
        direction = trend.get('direction', 'stable')

        # 6. 综合评分（1-100）
        # 基础分 = 近3天均值
        base = recent_avg

        # 调整项
        bonus = 0
        # 规律性加分
        if bedtime_consistency == 'excellent':
            bonus += 8
        elif bedtime_consistency == 'good':
            bonus += 4
        elif bedtime_consistency == 'poor':
            bonus -= 5

        # 趋势加分
        if direction == 'improving':
            bonus += 6
        elif direction == 'declining':
            bonus -= 8

        # 稳定性加分
        if score_std < 8:
            bonus += 5  # 稳定好
        elif score_std > 20:
            bonus -= 5  # 波动大不好

        # 异常扣分
        if anomaly > 0.7:
            bonus -= 10

        composite = max(10, min(100, base + bonus))

        # 7. 生成诊断标签
        if composite >= 75:
            grade = 'A'
            grade_label = '优秀 🏆'
        elif composite >= 60:
            grade = 'B'
            grade_label = '良好 👍'
        elif composite >= 45:
            grade = 'C'
            grade_label = '一般 ⚠️'
        elif composite >= 30:
            grade = 'D'
            grade_label = '较差 🔴'
        else:
            grade = 'F'
            grade_label = '很差 ⛔'

        # 8. 建议
        advice = []

        if bedtime_consistency == 'poor':
            advice.append({
                'priority': 'high',
                'aspect': '作息规律',
                'detail': f'睡眠时间不规律（标准差{self._std_times:.0f}分钟），建议固定就寝时间',
            })

        if direction == 'declining':
            advice.append({
                'priority': 'high',
                'aspect': '下降趋势',
                'detail': f'睡眠质量持续下降（速度{velocity:.1f}分/天），注意识别压力源',
            })

        if patterns.get('has_monday_anxiety'):
            advice.append({
                'priority': 'medium',
                'aspect': '周一焦虑',
                'detail': '周日晚/周一早睡眠明显较差，建议周日晚提前做放松训练',
            })

        if patterns.get('has_weekend_late'):
            advice.append({
                'priority': 'medium',
                'aspect': '周末熬夜',
                'detail': '周末就寝时间偏晚，影响周一恢复',
            })

        if score_std > 15:
            advice.append({
                'priority': 'medium',
                'aspect': '波动大',
                'detail': f'睡眠评分波动较大（标准差{score_std:.1f}），建议记录每日睡前状态',
            })

        if overall_avg < 55 and n_days >= 5:
            advice.append({
                'priority': 'high',
                'aspect': '持续低分',
                'detail': f'{n_days}天平均{overall_avg:.0f}分，持续偏低，建议就医咨询或使用正念课程',
            })

        # 9. 诊断书输出
        result = {
            'openid': openid,
            'generated_at': datetime.now().isoformat(),
            'date_range': f'最近{n_days}天' if n_days else '数据不足',

            'composite_score': round(composite, 1),
            'grade': grade,
            'grade_label': grade_label,

            'metrics': {
                'recent_average': round(recent_avg, 1),
                'overall_average': round(overall_avg, 1),
                'score_std': round(score_std, 1),
                'range': f'{min_score:.0f}-{max_score:.0f}',
                'direction': direction,
                'velocity': velocity,
                'acceleration': acceleration,
                'anomaly_index': anomaly,
                'bedtime_consistency': bedtime_consistency,
                'n_days': n_days,
                'monday_anxiety': patterns.get('has_monday_anxiety', False),
                'weekend_late': patterns.get('has_weekend_late', False),
                'weekly_periodicity': patterns.get('weekly_periodicity', 0),
            },

            'advice': advice,
            'score_timeline': scores[-7:] if len(scores) >= 7 else scores,
        }

        return result

    def _std(self, values):
        if len(values) < 2:
            return 0
        avg = sum(values) / len(values)
        return math.sqrt(sum((v - avg) ** 2 for v in values) / len(values))


def format_diagnosis_card(diagnosis: dict) -> str:
    """格式化为微信卡片文本"""
    m = diagnosis['metrics']
    lines = [
        f'📋 睡眠诊断书',
        f'━━━━━━━━━━━━━━━',
        f'等级: {diagnosis["grade_label"]}  |  综合评分: {diagnosis["composite_score"]}/100',
        f'数据: {diagnosis["date_range"]}',
        f'',
        f'📊 核心指标',
        f'  近3天均值: {m["recent_average"]}分',
        f'  总体均值: {m["overall_average"]}分',
        f'  波动范围: {m["range"]}  (σ={m["score_std"]})',
        f'  趋势: {m["direction"]} (速度{m["velocity"]}分/天)',
    ]
    if m['bedtime_consistency'] != 'unknown':
        lines.append(f'  作息规律性: {m["bedtime_consistency"]}')
    if m['weekly_periodicity'] > 0.5:
        lines.append(f'  周周期节律: 存在 ({m["weekly_periodicity"]:.0%})')

    if diagnosis['advice']:
        lines.append(f'')
        lines.append(f'💡 改善建议')
        for a in diagnosis['advice']:
            icon = '❗' if a['priority'] == 'high' else '·'
            lines.append(f'  {icon} {a["detail"]}')

    if diagnosis['score_timeline']:
        lines.append(f'')
        lines.append(f'📈 近7天趋势')
        vs = [s for _, s in diagnosis['score_timeline']]
        spark = _sparkline(vs)
        if spark:
            lines.append(f'  {spark}')
        for date, s in diagnosis['score_timeline']:
            bar = '█' * max(1, int(s / 5))
            lines.append(f'  {date[-5:]} {s:5.0f} {bar}')

    lines.append(f'━━━━━━━━━━━━━━━')
    return '\n'.join(lines)


BLOCKS = [' ', '\u2581', '\u2582', '\u2583', '\u2584', '\u2585', '\u2586', '\u2587', '\u2588']


def _sparkline(values, width=7):
    """生成紧凑火花线图"""
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
