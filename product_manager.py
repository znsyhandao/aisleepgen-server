# -*- coding: utf-8 -*-
"""
产品经理 v1 — 战略方向建议 + 优先级决策

安全原则(突变动力学)：
  1. 只读：不修改任何现有数据文件
  2. 轻量：subprocess调用，不阻塞主流程
  3. 无依赖：纯Python标准库

产出：
  - strategic_direction.json — 当前策略建议
  - 每日/每周建议
"""

import os, json
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SLEEP_SKIN = os.path.join(BASE, 'sleep-skin features')
STRATEGY_LOG = os.path.join(SLEEP_SKIN, 'strategic_direction.json')

def _safe_read_json(path, default=None):
    if default is None:
        default = {}
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return default

def analyze_backlog():
    """
    分析expert_board阻塞状态，产出"当前最应该解封谁"
    只读分析，不修改任何文件
    """
    board = _safe_read_json(os.path.join(BASE, 'expert_board.json'), {})
    if not board:
        return []

    results = []
    for name, info in board.items():
        if not isinstance(info, dict):
            continue
        status = info.get('status', '?')
        if status == 'blocked':
            reason = info.get('blocking_reason', info.get('needs_input_from', '未知原因'))
            results.append({
                'name': name,
                'status': 'blocked',
                'blocking_reason': str(reason)[:100],
            })
        elif status == 'ready':
            results.append({
                'name': name,
                'status': 'ready',
                'suggestion': '建议激活',
            })

    return results

def analyze_data_growth():
    """数据分析管线进度报告"""
    stats = {}

    # 录音数量
    analyzed_dir = os.path.join(BASE, 'sleep_record', 'analyzed')
    if os.path.exists(analyzed_dir):
        files = [f for f in os.listdir(analyzed_dir) if f.endswith('.json')]
        stats['sleep_records'] = len(files)

    # 面部照片
    face_csv = os.path.join(SLEEP_SKIN, 'facial_features_v9.csv')
    if os.path.exists(face_csv):
        with open(face_csv, 'r', encoding='utf-8') as f:
            lines = [l for l in f if l.strip()]
        stats['face_samples'] = max(0, len(lines) - 1) if lines else 0
        stats['face_days'] = 0
        if len(lines) > 1:
            # 统计有多少天
            header = lines[0].strip().split(',')
            if 'date' in header:
                dates = set()
                for line in lines[1:]:
                    parts = line.strip().split(',')
                    if len(parts) > header.index('date'):
                        dates.add(parts[header.index('date')])
                stats['face_days'] = len(dates)

    # 对齐数据
    aligned_csv = os.path.join(SLEEP_SKIN, 'aligned_features_v1.csv')
    if os.path.exists(aligned_csv):
        with open(aligned_csv, 'r', encoding='utf-8') as f:
            lines = [l for l in f if l.strip()]
        stats['aligned_days'] = max(0, len(lines) - 1) if lines else 0

    # 安全日志
    security_log = os.path.join(SLEEP_SKIN, 'security_audit_log.json')
    if os.path.exists(security_log):
        try:
            with open(security_log, 'r', encoding='utf-8') as f:
                log = json.load(f)
            stats['security_events'] = len(log)
        except:
            stats['security_events'] = 0

    # SRE看护日志
    sre_log = os.path.join(SLEEP_SKIN, 'sre_watchdog_log.json')
    if os.path.exists(sre_log):
        try:
            with open(sre_log, 'r', encoding='utf-8') as f:
                log = json.load(f)
            stats['sre_restarts'] = len(log.get('restarts', []))
            stats['sre_failures'] = len(log.get('failures', []))
        except:
            pass

    # 用户反馈
    feedback_path = os.path.join(BASE, 'data', 'feedback.json')
    if os.path.exists(feedback_path):
        try:
            fb = json.load(open(feedback_path, 'r', encoding='utf-8'))
            if isinstance(fb, list):
                stats['feedback_count'] = len(fb)
            elif isinstance(fb, dict):
                stats['feedback_count'] = len(fb.keys())
        except:
            stats['feedback_count'] = 0

    return stats


def generate_strategy():
    """生成一份策略建议"""
    backlog = analyze_backlog()
    stats = analyze_data_growth()
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    # 优先级建议
    recommendations = []

    # 数据量判断和建议
    face_count = stats.get('face_samples', 0)
    sleep_count = stats.get('sleep_records', 0)

    if face_count > 500 and sleep_count > 80:
        recommendations.append({
            'priority': 'HIGH',
            'action': '数据量充足，建议投入标注团队，提升模型精度',
            'condition': f'面部{face_count}张，录音{sleep_count}条',
            'impact': 'LightGBM MAE有望从2.92%降至1.5%以下',
        })
    elif face_count > 200:
        recommendations.append({
            'priority': 'MEDIUM',
            'action': '面部分析数据增长中，继续累积可训练更稳定模型',
            'condition': f'面部{face_count}张',
            'impact': '当前LightGBM MAE=2.92%，更多数据将改善跨天泛化',
        })

    # 阻塞专家建议
    blocked = [b for b in backlog if b['status'] == 'blocked']
    if blocked:
        suggestions = []
        for b in blocked:
            name = b['name']
            reason = b['blocking_reason']
            suggestions.append(f'{name}(阻塞原因:{reason})')
        recommendations.append({
            'priority': 'MEDIUM',
            'action': f'{len(blocked)}名专家被阻塞',
            'detail': '; '.join(suggestions[:5]),
            'impact': '考虑能否解除阻塞条件',
        })

    # 安全建议
    security_events = stats.get('security_events', 0)
    if security_events > 0:
        recommendations.append({
            'priority': 'INFO',
            'action': f'安全系统记录{security_events}次事件',
            'detail': '可以在/usr/security/logs查看详情',
        })

    # SRE建议
    restarts = stats.get('sre_restarts', 0)
    if restarts > 0:
        recommendations.append({
            'priority': 'INFO',
            'action': f'SRE已自动重启{restarts}次服务器',
            'detail': '建议检查服务器稳定性',
        })

    strategy = {
        'timestamp': now,
        'data_stats': stats,
        'blocked_experts': blocked,
        'recommendations': recommendations,
        'suggested_focus': recommendations[0]['action'] if recommendations else '持续积累数据',
    }

    # 只写输出，不影响任何管线数据
    os.makedirs(os.path.dirname(STRATEGY_LOG), exist_ok=True)
    with open(STRATEGY_LOG, 'w', encoding='utf-8') as f:
        json.dump(strategy, f, ensure_ascii=False, indent=2)

    return strategy


def print_report():
    """打印可读报告"""
    s = generate_strategy()
    print('Product Manager 战略报告')
    print(f'  Time: {s["timestamp"]}')
    print(f'  Focus: {s["suggested_focus"]}')
    print()
    print('  Data Stats:')
    for k, v in s.get('data_stats', {}).items():
        print(f'    {k}: {v}')
    print()
    print('  Recommendations:')
    for rec in s.get('recommendations', []):
        print(f'    [{rec["priority"]}] {rec["action"]}')
    print()
    print('  (只读分析，未修改任何管线数据)')


if __name__ == '__main__':
    print_report()
