# -*- coding: utf-8 -*-
"""
seed_test_user.py — 注入7天合成数据到test_user
通过 SQLite 存储层写入，确保 dp_router 能读取。

用法: python seed_test_user.py
"""

import sys; sys.stdout.reconfigure(encoding='utf-8')
import json, os, time, random
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OPENID = 'test_user'  # 微信开发者工具默认openid

random.seed(42)

# 通过 SQLite 写入（因为 profile_storage 已迁移到 db_sqlite）
from db_sqlite import SQLiteDB
_db = SQLiteDB(os.path.join(DATA_DIR, 'sleep.db'))

def ensure(filepath, default=None):
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f: return json.load(f)
    except Exception as e:
        print('  ! Failed to read %s: %s' % (filepath, e))
    return default if default is not None else {}

def save(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ===== 1. 创建7天的评分数据 =====
print('[Seeding] Step 1/5: Generating 7-day sleep scores...')
today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
scores = [
    ('2026-04-30', 72, 420, '7h 0m', '尚可', '23:45', 2, 26, 48, 26),
    ('2026-05-01', 65, 390, '6h 30m', '一般', '00:15', 3, 22, 52, 26),
    ('2026-05-02', 58, 360, '6h 0m', '较差', '01:00', 4, 18, 55, 27),
    ('2026-05-03', 78, 450, '7h 30m', '良好', '23:00', 1, 28, 45, 27),
    ('2026-05-04', 82, 480, '8h 0m', '很好', '22:30', 1, 30, 42, 28),
    ('2026-05-05', 74, 420, '7h 0m', '较好', '23:20', 2, 25, 47, 28),
    ('2026-05-06', 70, 0, '--', '--', '--', 0, 0, 0, 0),
]

working_mem = {'events': [], 'state': {}}
for i, (date, score, dur_min, dur_str, qual, bed, awake, deep, light, rem) in enumerate(scores):
    ts = datetime.strptime(date + 'T08:30:00', '%Y-%m-%dT%H:%M:%S').isoformat()
    working_mem['events'].append({
        'timestamp': ts,
        'type': 'survey',
        'content': '做完问卷了',
        'score': score,
    })
    working_mem['events'].append({
        'timestamp': ts,
        'type': 'prediction',
        'content': '[预测引擎] 评分%s; 时长%s; 质%s; 睡前%s; 清醒%s次' % (score, dur_str, qual, bed, awake),
        'score': score,
    })
    # 音频传感器数据（后5天）
    if i >= 2:
        snore = random.randint(30, 95)
        movement = random.randint(20, 120)
        stab = round(random.uniform(30, 80), 1)
        working_mem['events'].append({
            'timestamp': ts,
            'type': 'audio_sensor',
            'content': '[音频传感器] 时长%dmin; 效率100%%; 稳定性%.1f/100; 鼾声%d%%; 体动%d分钟' % (
                dur_min, stab, snore, movement),
            'score': score,
        })
    # 前几天
    if i <= 4:
        working_mem['events'].append({
            'timestamp': ts,
            'type': 'chat',
            'content': '昨晚睡%s，感觉%s' % (dur_str, qual),
            'score': score,
        })

working_mem['state']['last_activity'] = scores[-1][0] + 'T08:30:00'
working_mem['state']['total_events'] = len(working_mem['events'])
save(os.path.join(DATA_DIR, 'working_memory_%s.json' % OPENID), working_mem)
print('  -> %d events written to working_memory_%s.json' % (len(working_mem['events']), OPENID))

# ===== 2. 创建用户简要档案（通过 SQLite） =====
print('[Seeding] Step 2/5: User profile (SQLite)...')

# ===== 修复known bug: default用户的last_active未设置导致scheduler疯狂刷推送 =====
try:
    default_prof = _db.load_user_profile('default')
    default_prof['last_active'] = (datetime.now() - timedelta(hours=1)).isoformat()
    _db.save_user_profile(default_prof, 'default')
    print('  -> Fixed default user last_active (prevent scheduler spam)')
except Exception as e:
    print('  -> Could not fix default user: %s' % e)

# 清理push_queue（防止scheduler堆积）
try:
    qpath = os.path.join(DATA_DIR, 'push_queue.json')
    if os.path.exists(qpath):
        with open(qpath, 'r', encoding='utf-8') as f:
            q = json.load(f)
        # 保留test_user的，清掉default和其他的
        q = [item for item in q if item.get('openid') == OPENID]
        with open(qpath, 'w', encoding='utf-8') as f:
            json.dump(q, f, ensure_ascii=False)
        print('  -> Cleaned push_queue (kept only %s items for test_user)' % len(q))
except Exception as e:
    print('  -> Could not clean push_queue: %s' % e)

# 清理delayed_pushes
for dpfile in ['delayed_pushes.json', 'delayed_pushes_%s.json' % OPENID]:
    dppath = os.path.join(DATA_DIR, dpfile)
    if os.path.exists(dppath):
        try:
            with open(dppath, 'r', encoding='utf-8') as f:
                dp = json.load(f)
            dp = [item for item in dp if isinstance(item, dict) and item.get('openid') == OPENID]
            with open(dppath, 'w', encoding='utf-8') as f:
                json.dump(dp, f, ensure_ascii=False)
            print('  -> Cleaned %s (%d items)' % (dpfile, len(dp)))
        except: pass

# 现在创建test_user profile
# 先读现有的 SQLite 配置
existing = _db.load_user_profile(OPENID)
# 获取默认profile结构
profile = _db.get_default_profile()
profile.update({
    'nickname': '小明',
    'last_active': scores[-1][0] + 'T08:30:00',
    'created_at': '2026-04-28T10:00:00',
    'score': scores[-2][1],  # 昨天评分
    'username': '测试用户',
    'avatar': '',
    'settings': {
        'push_morning': True,
        'push_evening': True,
        'dark_mode': True,
    },
    # history — dashboard的数据源，SQLite默认有[]
    'history': [],
})

# 灌入history
history_records = []
for rec in scores:
    date_str = rec[0]
    if date_str == '2026-05-06':
        continue  # 今天还没有完整数据
    score, dur_min, dur_str, qual, bed, awake, deep, light, rem = rec[1:]
    deep = int(deep)
    light = int(light)
    rem = int(rem)
    history_records.append({
        'date': date_str,
        'total_duration': dur_min,
        'duration_str': dur_str,
        'wm_score': score,
        'deep_pct': deep,
        'light_pct': light,
        'rem_pct': rem,
        'awake_times': awake,
        'awake_pct': round(100 - deep - light - rem, 1),
        'bedtime': bed,
        'quality': qual,
    })
profile['history'] = history_records
_db.save_user_profile(profile, OPENID)
profile_size = len(json.dumps(profile))
print('  -> SQLite: openid=%s, history=%d records, ~%d bytes' % (OPENID, len(history_records), profile_size))

# ===== 3. 创建手环数据(ring_ocr输出) =====
print('[Seeding] Step 3/5: Ring OCR data (3 days)...')
ring_data = []
for i in [4, 5, 6]:  # 5月4日、5日、6日
    date = scores[i][0]
    ts = date + 'T23:30:00'
    hr = random.randint(58, 72)
    spo2 = random.randint(94, 98)
    movement = random.randint(15, 45)
    ring_data.append({
        'date': date,
        'timestamp': ts,
        'heart_rate': hr,
        'spo2': spo2,
        'body_movement': movement,
        'source': 'Ring',
        'confidence': round(random.uniform(0.7, 0.95), 2),
    })
save(os.path.join(DATA_DIR, 'ring_data_%s.json' % OPENID), ring_data)
print('  -> %d days written to ring_data_%s.json' % (len(ring_data), OPENID))

# ===== 4. 创建自动日记 =====
print('[Seeding] Step 4/5: Auto diaries (last 3 days)...')
diaries_dir = os.path.join(DATA_DIR, 'diaries')
os.makedirs(diaries_dir, exist_ok=True)
for i in [4, 5]:  # 5月4日、5日
    date = scores[i][0]
    day_score = scores[i][1]
    diary = {
        'date': date,
        'composite_score': day_score,
        'completeness': round(random.uniform(60, 95), 1),
        'diary_text': '%s的睡眠质量良好，评分%s分。睡眠时长%s，入睡时间%s，夜间清醒%s次。' % (
            date, day_score, scores[i][3], scores[i][5], scores[i][6]),
        'short_text': '评分%s ● 时长%s ● 睡前%s' % (day_score, scores[i][3], scores[i][5]),
        'band_summary': {'heart_rate_avg': random.randint(60, 72), 'movement': random.randint(20, 50)},
        'audio_summary': {'snore_level': random.choice(['轻度', '中度', '无']), 'stability': round(random.uniform(50, 80), 1)},
        'sparkline': '▅▆▇▇▆▅▄ %d-' % day_score,
        'generated_at': datetime.now().isoformat(),
    }
    save(os.path.join(diaries_dir, '%s_%s.json' % (OPENID, date)), diary)
    print('  -> diary for %s (score=%d)' % (date, day_score))

# ===== 5. 创建chart数据(直接灌入chart_data输出格式) =====
print('[Seeding] Step 5/5: Chart data...')

# 计算最新6天
last_6 = [s for s in scores if s[0] != '2026-05-06']
trend_data = {
    'labels': [s[0] for s in last_6],
    'values': [s[1] for s in last_6],
    'avg': round(sum(s[1] for s in last_6) / len(last_6), 1),
    'trend': 'neutral',
}
stage_data = {
    'data': [
        {'name': '深睡', 'value': 28, 'color': '#4A90E2'},
        {'name': '浅睡', 'value': 45, 'color': '#6FCF97'},
        {'name': 'REM', 'value': 22, 'color': '#9B59B6'},
        {'name': '清醒', 'value': 5, 'color': '#F2994A'},
    ]
}
radar_data = {
    'data': [
        {'label': '规律性', 'value': 82},
        {'label': '深度', 'value': 68},
        {'label': '效率', 'value': 75},
        {'label': '稳定性', 'value': 58},
        {'label': '恢复性', 'value': 70},
        {'label': '主观', 'value': 74},
    ]
}
weekly_compare = {
    'this_week_avg': round(sum(s[1] for s in last_6) / len(last_6), 1),
    'last_week_avg': round(sum(s[1] for s in last_6) / len(last_6) - random.uniform(3, 8), 1),
    'change': round(random.uniform(-3, 8), 1),
}
heatmap = {
    'data': [[random.randint(40, 90) for _ in range(7)] for _ in range(4)],
}

full_chart = {
    'trend_line': trend_data,
    'stage_pie': stage_data,
    'radar': radar_data,
    'weekly_compare': weekly_compare,
    'heatmap': heatmap,
    'summary': {
        'avg_score': trend_data['avg'],
        'best_score': max(trend_data['values']),
        'worst_score': min(trend_data['values']),
        'total_days': len(trend_data['values']),
    },
}

save(os.path.join(DATA_DIR, 'chart_data_%s.json' % OPENID), full_chart)
print('  -> chart data: avg=%s, trend=%d days, radar=%d dims' % (
    trend_data['avg'], len(trend_data['values']), len(radar_data['data'])))

# ===== 总结 =====
print()
print('=' * 50)
print('[Seeding] ✅ All data injected for test_user')
print('[Seeding] Data directory: %s' % DATA_DIR)
print('[Seeding]')
print('[Seeding] 下一步: 微信开发者工具 → 清除缓存 → 编译')
print('[Seeding] 首页应该显示:')
print('[Seeding]   ✅ 评分环 (74分 昨日vs周均)')
print('[Seeding]   ✅ 趋势柱状图 (6天历史)')
print('[Seeding]   ✅ 诊断书卡片')
print('[Seeding]   ✅ 睡前预判卡片')
print('[Seeding]   ✅ 自动日记卡片 x2')
print('[Seeding]   ✅ 阶段饼图 + 六维雷达')
print('[Seeding]   ✅ AI记忆摘要')
print('[Seeding] =' * 6)
