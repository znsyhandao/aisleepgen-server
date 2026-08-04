import json
from collections import Counter
with open('user_profile.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('Total users:', len(data))

real_users = []
for uid, p in data.items():
    if not uid.startswith('test_') and not uid.startswith('t_') and 'dev_' not in uid and 'nonexistent' not in uid:
        real_users.append(uid)
        latest = p.get('latest', {})
        sleep_data = latest.get('sleep_data', {}) if isinstance(latest, dict) else {}
        has_sleep = bool(sleep_data.get('bedtime'))
        history_count = len(p.get('history', []))
        score = latest.get('score', '?') if isinstance(latest, dict) else '?'
        print(f'  {uid}: has_sleep={has_sleep} history={history_count} score={score}')

print(f'\nReal users: {len(real_users)}')

today_counts = Counter()
for uid, p in data.items():
    for h in p.get('history', []):
        today_counts[h.get('date', '?')] += 1

import datetime
today = datetime.date.today().isoformat()
print(f'Today dialogues: {today_counts.get(today, 0)}')
print(f'Top dates: {today_counts.most_common(5)}')

scores = []
for uid, p in data.items():
    latest = p.get('latest', {})
    if isinstance(latest, dict) and 'score' in latest:
        scores.append(latest['score'])
print(f'Scored users: {len(scores)}. Avg: {sum(scores)/len(scores):.1f}' if scores else 'No scored users')
