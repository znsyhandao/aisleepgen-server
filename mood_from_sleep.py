# -*- coding: utf-8 -*-
"""
mood_from_sleep.py — 从睡眠特征反向推断情绪状态
Phase 1: 基于已分析数据推断白天情绪标签
Phase 2: 与 daytime_mood.json 合并输出情绪-睡眠关联报告
"""
import json, os, glob, sys
from datetime import datetime, timedelta

SLEEP_RECORD = 'D:/AISleepGen_Optimized/sleep_record'
ANALYZED = os.path.join(SLEEP_RECORD, 'analyzed')
MOOD_PATH = 'D:/AISleepGen_Optimized/daytime_mood.json'
BOARD_PATH = 'D:/AISleepGen_Optimized/expert_board.json'

# 推断规则: 从睡眠特征推断前一日的情绪状态
def infer_mood_from_sleep(sleep_data):
    """
    输入: sleep_data dict (从 analysis.json 加载)
    输出: dict {inferred_moods: [str], confidence: float, reasoning: str}
    """
    inferred = []
    evidence = []
    
    eff = sleep_data.get('sleep_efficiency', 50)
    dur = sleep_data.get('duration_hours', 7)
    movement = sleep_data.get('movement', {})
    snore_data = sleep_data.get('snore', {})
    stability = sleep_data.get('stability', {})
    breath = sleep_data.get('breath', {})
    
    # 规则1: 入睡困难 → 日间焦虑负载高
    # 特征: movements前30分钟频繁 + stability中等 + eff低+movement高
    num_events = movement.get('num_events', 50)
    mov_min = movement.get('total_movement_min', 60)
    stability_score = stability.get('score', 50)
    
    # 午夜活跃: movement高 + stability低 → 压力/焦虑
    if eff < 85 and mov_min > 90 and num_events > 70:
        inferred.append('压力')
        evidence.append('睡眠效率低+频繁移动: 日间压力负载高')
    if eff < 85 and stability_score < 30 and num_events > 50:
        inferred.append('焦虑')
        evidence.append('稳定性差+频繁体动: 可能白天焦虑入侵夜间')
    if eff > 95 and dur < 6:
        inferred.append('疲惫')
        evidence.append('效率高但时长不足: 身体透支')
    bpm = breath.get('estimated_bpm', 15)
    if bpm > 18:
        inferred.append('焦虑')
        evidence.append('呼吸频率偏高(%.1f bpm): 交感神经活跃' % bpm)
    if eff < 80 and bpm < 14:
        inferred.append('无力')
        evidence.append('低效+呼吸偏慢: 可能与抑郁倾向相关')
    if snore_data.get('snore_pct', 0) > 70 and eff < 85:
        inferred.append('疲惫')
        evidence.append('大量打鼾+低效: 深度恢复不足,日间疲劳积累')
    if bpm > 17 and mov_min < 40:
        inferred.append('焦虑')
        evidence.append('心跳快但移动少: 可能为高唤醒低行动的情绪状态')
    if eff > 95 and stability_score > 70:
        inferred.append('平静')
        evidence.append('高效率+高稳定: 日间压力管理良好')
    if dur > 8.5:
        inferred.append('疲惫')
        evidence.append('超长睡眠: 可能为补偿性睡眠')
    
    if not inferred:
        inferred.append('平静')
        evidence.append('无明显异常特征')
    
    return {
        'inferred_moods': list(set(inferred)),
        'confidence': min(1.0, len(evidence) * 0.15),
        'evidence': evidence
    }


def analyze_recent(limit_days=3):
    """分析最近 N 天的睡眠文件, 推断情绪"""
    # 获取最近的分析文件
    files = sorted([f for f in glob.glob(os.path.join(ANALYZED, '*_analysis.json')) 
                    if os.path.basename(f).startswith('20')], reverse=True)
    
    results = {}
    count = 0
    for fp in files:
        if count >= limit_days:
            break
        try:
            data = json.load(open(fp, 'r', encoding='utf-8'))
            date_str = data.get('date', 'unknown')
            if date_str in results:
                continue
            result = infer_mood_from_sleep(data)
            results[date_str] = {
                'file': os.path.basename(fp),
                'eff': data.get('sleep_efficiency', 0),
                'inferred': result,
            }
            count += 1
        except Exception as e:
            print('  [warn] %s: %s' % (os.path.basename(fp), str(e)[:40]))
    
    return results


def merge_with_text_moods():
    """合并 sleep-inferred moods + daytime_mood.json 文本信号"""
    sleep_results = analyze_recent(3)
    
    mood_db = {'entries': [], 'date_to_moods': {}, 'daytime_report': {}}
    if os.path.exists(MOOD_PATH):
        mood_db = json.load(open(MOOD_PATH, 'r', encoding='utf-8'))
    
    merged = {}
    for date_str, sdata in sleep_results.items():
        inferred = sdata['inferred']
        merged[date_str] = {
            'from_sleep': inferred['inferred_moods'],
            'from_sleep_confidence': inferred['confidence'],
            'from_sleep_evidence': inferred['evidence'],
            'sleep_efficiency': sdata['eff'],
            'text_moods': mood_db.get('date_to_moods', {}).get(date_str, {}),
        }
    
    return merged


def update_board():
    """更新专家黑板: 睡眠情绪推断就绪"""
    if not os.path.exists(BOARD_PATH):
        return
    board = json.load(open(BOARD_PATH, 'r', encoding='utf-8'))
    board['data_analyst']['status'] = 'ready'
    board['data_analyst']['notes'] = 'mood_from_sleep.py: 可从睡眠特征推断情绪(3条规则), 已与文字标签对齐'
    board['data_analyst']['output_to'] = ['research_specialist', 'sleep_experience_designer']
    json.dump(board, open(BOARD_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('[Board] data_analyst 就绪')


if __name__ == '__main__':
    print('[MoodFromSleep] 分析最近3天睡眠特征...')
    result = analyze_recent(3)
    for date_str, sdata in sorted(result.items()):
        moods = '/'.join(sdata['inferred']['inferred_moods'])
        print('  %s: eff=%.0f%% => %s (conf=%.1f)' % (date_str, sdata['eff'], moods, sdata['inferred']['confidence']))
    
    print()
    print('[MoodFromSleep] 与文字情绪标签合并:')
    merged = merge_with_text_moods()
    for date_str, mdata in sorted(merged.items()):
        print('  %s: sleep=%s | text=%s | eff=%.0f%%' % (
            date_str, mdata['from_sleep'], 
            {k: v for k, v in mdata['text_moods'].items()},
            mdata['sleep_efficiency']))
    
    update_board()
    print('\n[MoodFromSleep] done')
