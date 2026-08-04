# -*- coding: utf-8 -*-
"""
标注团队 v1 — 从录音分析结果中提取标签（无监督+有监督二合一）

突变动力学安全设计：
  1. 不修改任何原始数据文件（录音、CSV、JSON）
  2. 只创建 .label 文件到 labeling/
  3. 标注文件不参与主管线，需要手动 merge

产出：
  - labeling/ 目录下的 .label 文件
  - labeling_summary.json — 当前标注进度

依赖：
  - sleep_record/analyzed/*.json (只读)
  - data/user_profile.json (只读，取反馈)
"""

import os, json, re
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
ANALYZED_DIR = os.path.join(BASE, 'sleep_record', 'analyzed')
LABEL_DIR = os.path.join(BASE, 'labeling')
USER_PROFILE = os.path.join(BASE, 'user_profile.json')

LABEL_TEMPLATE = {
    'version': 'v1-label',
    'source': 'auto_labeled',
    'label': {
        'subjective_eff': None,        # 用户主观评分 0-100
        'sleep_quality_bin': None,     # high / medium / low
        'mood_tags': [],               # 情绪标签 ['calm', 'anxious', ...]
        'interruption_count': None,    # 打断次数估计
    },
    'confidence': None,                # 0.0-1.0
}

def auto_label(audio_analysis: dict) -> dict:
    """从录音分析结果自动生成标签"""
    features = audio_analysis.get('features', {})
    label = {
        'subjective_eff': None,
        'sleep_quality_bin': None,
        'mood_tags': [],
        'interruption_count': None,
    }

    # 从 features 取 eff (如果有)
    eff = features.get('eff', None)
    if eff is not None:
        label['subjective_eff'] = round(eff, 1)

        # 质量分级
        if eff >= 97:
            label['sleep_quality_bin'] = 'high'
        elif eff >= 90:
            label['sleep_quality_bin'] = 'medium'
        else:
            label['sleep_quality_bin'] = 'low'

    # 根据打断事件推断打断次数
    events = audio_analysis.get('events', [])
    interruptions = [e for e in events if e.get('type') in ('interruption', 'movement', 'noise')]
    label['interruption_count'] = len(interruptions)

    # 情绪推断
    pct = features.get('sleep_efficiency', eff)
    if pct is not None:
        if pct >= 98:
            label['mood_tags'].append('deep_sleep')
        if pct >= 95:
            label['mood_tags'].append('restorative')
        if len(interruptions) > 5:
            label['mood_tags'].append('restless')

    return label

def merge_user_feedback(user_profile: dict) -> dict:
    """从用户反馈中提取标签"""
    feedbacks = user_profile.get('feedbacks', [])
    if isinstance(feedbacks, dict):
        feedbacks = list(feedbacks.values())
    if not isinstance(feedbacks, list):
        feedbacks = []

    # 按日期索引
    date_labels = {}
    for fb in feedbacks:
        date = fb.get('date', fb.get('timestamp', ''))[:10]
        score = fb.get('score', fb.get('eff', fb.get('rating', None)))
        if date and score is not None:
            if date not in date_labels:
                date_labels[date] = []
            date_labels[date].append(float(score))

    # 聚合
    for date, scores in date_labels.items():
        avg = sum(scores) / len(scores)
        date_labels[date] = {
            'subjective_eff': round(avg, 1),
            'source': 'user_feedback',
        }

    return date_labels


def process():
    """全量标注流水线"""
    start = datetime.now()

    # 收集所有已分析的录音
    if not os.path.exists(ANALYZED_DIR):
        print(f'[Labeler] 分析目录不存在: {ANALYZED_DIR}')
        return

    audio_files = [f for f in os.listdir(ANALYZED_DIR) if f.endswith('.json')]
    print(f'[Labeler] 找到 {len(audio_files)} 条分析记录')

    os.makedirs(LABEL_DIR, exist_ok=True)

    user_labels = {}
    if os.path.exists(USER_PROFILE):
        try:
            profile = json.load(open(USER_PROFILE, 'r', encoding='utf-8'))
            user_labels = merge_user_feedback(profile)
            print(f'[Labeler] 用户反馈标签: {len(user_labels)} 天')
        except Exception as e:
            print(f'[Labeler] 用户反馈读取失败: {e}')

    auto_count = 0
    merged_count = 0
    skipped = []

    for af in sorted(audio_files):
        try:
            with open(os.path.join(ANALYZED_DIR, af), 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            skipped.append(f'{af}: JSON解析失败')
            continue

        # 提取日期
        date_match = re.match(r'(\d{8})', af)
        date = date_match.group(1) if date_match else af[:8]

        analysis_meta = data.get('analysis', data)
        auto = auto_label(analysis_meta)

        # 如果有用户反馈，合并
        if date in user_labels:
            for k, v in user_labels[date].items():
                if v is not None:
                    auto[k] = v
            merged_count += 1

        # 写 .label 文件
        label_path = os.path.join(LABEL_DIR, f'{date}.label')
        label_entry = {
            'date': date,
            'source': 'merged' if date in user_labels else 'auto_labeled',
            'label': auto,
            'confidence': 0.7 if date in user_labels else 0.4,
            'generated_at': datetime.now().isoformat(),
            'source_file': af,
        }

        with open(label_path, 'w', encoding='utf-8') as f:
            json.dump(label_entry, f, ensure_ascii=False, indent=2)
        auto_count += 1

    # 写汇总
    summary = {
        'generated_at': datetime.now().isoformat(),
        'total_recorded': len(audio_files),
        'labeled': auto_count,
        'merged_with_feedback': merged_count,
        'skipped': len(skipped),
        'label_dir': LABEL_DIR,
        'durations_sec': (datetime.now() - start).total_seconds(),
    }
    if skipped:
        summary['skipped_reasons'] = skipped[:5]

    summary_path = os.path.join(LABEL_DIR, 'labeling_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f'[Labeler] 完成: {auto_count} 条标注, {merged_count} 条含用户反馈, {len(skipped)} 条跳过')
    print(f'[Labeler] 汇总: {summary_path}')
    return summary


def format_for_training():
    """输出可用于训练的 label 表格 (CSV格式)"""
    if not os.path.exists(LABEL_DIR):
        print('[Labeler] 标注目录不存在')
        return

    labels = []
    for f in sorted(os.listdir(LABEL_DIR)):
        if not f.endswith('.label'):
            continue
        try:
            with open(os.path.join(LABEL_DIR, f), 'r', encoding='utf-8') as lf:
                data = json.load(lf)
            labels.append(data)
        except:
            pass

    if not labels:
        print('[Labeler] 无标签文件')
        return

    # 打印表格
    print(f' 日期      | 评分   | 质量   | 情绪标签          | 置信度 | 来源')
    print(f'----------|--------|--------|-------------------|--------|------')
    for l in labels:
        lbl = l.get('label', {})
        eff = lbl.get('subjective_eff', '-')
        if eff is not None:
            eff = f'{eff:.1f}'
        else:
            eff = '-'
        quality = lbl.get('sleep_quality_bin', '-')
        moods = ','.join(lbl.get('mood_tags', [])) or '-'
        conf = l.get('confidence', 0)
        source = l.get('source', '?')
        date = l.get('date', '??????')
        print(f' {date} | {str(eff):>6s} | {str(quality):>6s} | {str(moods):17s} | {conf:.1f}  | {source}')


if __name__ == '__main__':
    process()
    print()
    format_for_training()
