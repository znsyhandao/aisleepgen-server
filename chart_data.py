# chart_data.py v1.0 — 图表数据API
# 将后端数据转换为前端可直接渲染的图表结构
#
# 后端产出结构化数据：
#   1. 评分趋势线（14天）
#   2. 睡眠阶段饼图（深睡/浅睡/REM/清醒）
#   3. 每周对比柱状图
#   4. 睡眠热力图（一周7天x24小时）
#   5. 六维雷达数据（已有，增强为趋势对比）
#
# 前端用 canvas 或 CSS 绘制

import os, math
from datetime import datetime, timedelta
from collections import defaultdict

PROJECT_ROOT = r'D:\AISleepGen_Optimized'


def get_chart_data(openid: str) -> dict:
    """获取完整图表数据"""
    
    wm = None
    try:
        from working_memory import get_working_memory
        wm = get_working_memory()
    except Exception:
        pass

    # 1. 评分趋势线
    trend_line = _build_trend_line(openid, wm)
    
    # 2. 睡眠阶段分布
    stage_pie = _build_stage_pie(openid)
    
    # 3. 每周对比
    weekly_compare = _build_weekly_compare(openid, wm)
    
    # 4. 睡眠热力图
    heatmap = _build_heatmap(openid, wm)
    
    # 5. 六维雷达（增强版）
    radar = _build_radar(openid, wm)
    
    # 6. 核心指标摘要
    summary = _build_summary(trend_line, stage_pie)
    
    return {
        'openid': openid,
        'generated_at': datetime.now().isoformat(),
        'trend_line': trend_line,
        'stage_pie': stage_pie,
        'weekly_compare': weekly_compare,
        'heatmap': heatmap,
        'radar': radar,
        'summary': summary,
        'version': '1.0',
    }


def _get_scores(openid, wm, n_days=14) -> list:
    """获取评分时间序列"""
    scores = []
    if wm:
        try:
            recent = wm.recent(openid, n=n_days)
            for e in recent:
                s = e.get('score_obs')
                if s is not None and s > 0:
                    ts = e.get('timestamp', '')
                    scores.append({
                        'date': ts[:10] if ts else datetime.now().strftime('%Y-%m-%d'),
                        'score': round(s, 1),
                        'time': ts[11:16] if len(ts) >= 16 else '',
                    })
        except Exception:
            pass
    return scores


def _build_trend_line(openid, wm) -> dict:
    """建立评分趋势线数据"""
    scores = _get_scores(openid, wm, 14)
    
    # 按日期聚合（取当天最后一次）
    daily = {}
    for s in scores:
        daily[s['date']] = s['score']
    
    dates = sorted(daily.keys())
    values = [daily[d] for d in dates]
    
    if not values:
        return {'labels': [], 'values': [], 'min': 0, 'max': 0, 'avg': 0}
    
    avg = round(sum(values) / len(values), 1)
    trend = 'up' if len(values) >= 2 and values[-1] > values[-2] else ('down' if len(values) >= 2 and values[-1] < values[-2] else 'flat')
    
    # 标注变化
    annotations = []
    if len(values) >= 2:
        delta = round(values[-1] - values[-2], 1)
        if abs(delta) >= 5:
            annotations.append({
                'date': dates[-1],
                'label': f'{"+" if delta > 0 else ""}{delta}',
                'type': 'up' if delta > 0 else 'down',
            })
    
    return {
        'type': 'line',
        'labels': dates,
        'values': values,
        'min': int(min(values) * 0.9) if values else 0,
        'max': min(100, int(max(values) * 1.1)) if values else 100,
        'avg': avg,
        'trend': trend,
        'annotations': annotations,
    }


def _build_stage_pie(openid) -> dict:
    """建立睡眠阶段分布数据"""
    stages = [
        {'name': '深睡', 'key': 'deep_sleep_min', 'color': '#3b82f6', 'default': 0},
        {'name': '浅睡', 'key': 'light_sleep_min', 'color': '#60a5fa', 'default': 0},
        {'name': 'REM', 'key': 'rem_min', 'color': '#8b5cf6', 'default': 0},
        {'name': '清醒', 'key': 'awake_min', 'color': '#f59e0b', 'default': 0},
    ]
    
    try:
        from ring_ocr import get_ring_extractor
        ex = get_ring_extractor()
        known = ex.extract_known_values()
        if known:
            total = known.get('total_sleep_min', 1)
            data = []
            for s in stages:
                val = known.get(s['key'], s['default'])
                data.append({
                    'name': s['name'],
                    'value': round(val / total * 100, 1) if total > 0 else 0,
                    'minutes': val,
                    'color': s['color'],
                })
            return {
                'type': 'pie',
                'data': data,
                'total_minutes': total,
                'source': 'ring',
            }
    except Exception:
        pass
    
    return {'type': 'pie', 'data': [], 'total_minutes': 0, 'source': 'none'}


def _build_weekly_compare(openid, wm) -> dict:
    """建立本周vs上周对比"""
    scores = _get_scores(openid, wm, 14)
    
    today = datetime.now()
    this_week = today.isocalendar()[1]
    last_week = this_week - 1
    this_year = today.year
    
    this_week_scores = []
    last_week_scores = []
    
    for s in scores:
        try:
            dt = datetime.fromisoformat(s['date'])
            iso = dt.isocalendar()
            if iso[0] == this_year and iso[1] == this_week:
                this_week_scores.append(s['score'])
            elif iso[0] == this_year and iso[1] == last_week:
                last_week_scores.append(s['score'])
        except Exception:
            pass
    
    this_avg = round(sum(this_week_scores) / len(this_week_scores), 1) if this_week_scores else 0
    last_avg = round(sum(last_week_scores) / len(last_week_scores), 1) if last_week_scores else 0
    change = round(this_avg - last_avg, 1)
    
    # 周维度数据（每日均值）
    day_names = ['一', '二', '三', '四', '五', '六', '日']
    
    return {
        'type': 'bar',
        'this_week_avg': this_avg,
        'last_week_avg': last_avg,
        'change': change,
        'change_type': 'up' if change > 3 else ('down' if change < -3 else 'flat'),
        'this_week': {
            'labels': day_names,
            'values': [0] * 7,  # 简版，真实需按天聚合
        },
        'last_week': {
            'labels': day_names,
            'values': [0] * 7,
        },
    }


def _build_heatmap(openid, wm) -> dict:
    """建立睡眠热力图（一周7天x24小时）"""
    scores = _get_scores(openid, wm, 7)
    
    if not scores:
        return {'type': 'heatmap', 'data': [], 'has_data': False}
    
    # 简版：最近7天每天评分，按评分区间着色
    daily = {}
    for s in scores:
        daily[s['date']] = s['score']
    
    heat_data = []
    for date, score in sorted(daily.items()):
        # 颜色区间
        if score >= 80:
            color = '#4CAF50'
        elif score >= 65:
            color = '#667eea'
        elif score >= 50:
            color = '#FF9800'
        else:
            color = '#F44336'
        
        heat_data.append({
            'date': date[-5:],  # MM-DD
            'score': score,
            'color': color,
            'intensity': round(score / 100, 2),
        })
    
    return {
        'type': 'heatmap',
        'data': heat_data,
        'has_data': True,
    }


def _build_radar(openid, wm) -> dict:
    """建立六维雷达数据（增强版）"""
    scores = _get_scores(openid, wm, 7)
    
    all_scores = [s['score'] for s in scores]
    avg = sum(all_scores) / len(all_scores) if all_scores else 50
    
    # 从 avg 分配六个维度（有真实数据时再替换）
    # 规律性、深度、效率、稳定性、恢复性、主观感受
    dims = {
        '规律性': min(100, avg + 5),
        '深度': min(100, avg - 3),
        '效率': min(100, avg + 8),
        '稳定性': min(100, avg - 5),
        '恢复性': min(100, avg + 2),
        '主观': min(100, avg - 2),
    }
    
    # 如果有手环数据，修正"深度"和"效率"
    try:
        from ring_ocr import get_ring_extractor
        ex = get_ring_extractor()
        known = ex.extract_known_values()
        if known:
            deep_pct = known.get('deep_sleep_min', 0) / max(known.get('total_sleep_min', 1), 1) * 100
            dims['深度'] = min(100, round(deep_pct * 1.5 + 30))
            eff = 100 - (known.get('awake_min', 0) / max(known.get('total_sleep_min', 1), 1) * 100)
            dims['效率'] = min(100, round(eff))
    except Exception:
        pass
    
    data = [{'label': k, 'value': round(v)} for k, v in dims.items()]
    
    return {
        'type': 'radar',
        'data': data,
        'avg_score': round(avg),
    }


def _build_summary(trend_line, stage_pie) -> dict:
    """核心指标摘要"""
    summary = {
        'avg_score': trend_line.get('avg', 0),
        'trend': trend_line.get('trend', 'flat'),
        'days_of_data': len(trend_line.get('values', [])),
    }
    
    if stage_pie.get('data'):
        for s in stage_pie['data']:
            summary[f'{s["name"]}_pct'] = s['value']
            summary[f'{s["name"]}_min'] = s['minutes']
    
    return summary
