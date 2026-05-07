# auto_diary_scheduler.py v1.0 — 自动日记定时触发
# 挂载到 scheduler_daemon，每天早晨7点自动运行
# 为所有活跃用户生成睡眠日记

import json, os
from datetime import datetime, timedelta

PROJECT_ROOT = r'D:\AISleepGen_Optimized'


def get_active_users(days=3) -> list:
    """获取近期活跃用户列表"""
    users = []
    data_dir = os.path.join(PROJECT_ROOT, 'data')
    if not os.path.exists(data_dir):
        return users
    
    profile_file = os.path.join(data_dir, 'user_profile.json')
    if os.path.exists(profile_file):
        try:
            with open(profile_file, 'r', encoding='utf-8') as f:
                profiles = json.load(f)
            for uid, p in profiles.items():
                last_active = p.get('last_active', '')
                if last_active:
                    try:
                        dt = datetime.fromisoformat(last_active)
                        if (datetime.now() - dt).days <= days:
                            users.append(uid)
                    except Exception:
                        pass
        except Exception:
            pass
    return users


def run_daily_diary():
    """执行每日日记生成（供scheduler_daemon调用）"""
    from auto_diary import AutoDiary, format_diary_short

    users = get_active_users()
    if not users:
        print(f'[AutoDiaryScheduler] No active users found')
        return {'status': 'skipped', 'reason': 'no active users'}

    ad = AutoDiary()
    results = []
    for uid in users:
        try:
            diary = ad.generate_diary(uid)
            short = format_diary_short(diary)
            
            # 保存到文件
            diary_dir = os.path.join(PROJECT_ROOT, 'data', 'diaries')
            os.makedirs(diary_dir, exist_ok=True)
            date_str = datetime.now().strftime('%Y-%m-%d')
            diary_path = os.path.join(diary_dir, f'{uid}_{date_str}.json')
            with open(diary_path, 'w', encoding='utf-8') as f:
                json.dump(diary, f, ensure_ascii=False, indent=2)
            
            results.append({
                'openid': uid,
                'score': diary.get('composite_score'),
                'completeness': diary.get('completeness'),
                'saved': diary_path,
            })
            print(f'[AutoDiaryScheduler] Generated diary for {uid}: score={diary.get("composite_score")}')
        except Exception as e:
            print(f'[AutoDiaryScheduler] Failed for {uid}: {e}')
            results.append({'openid': uid, 'error': str(e)})

    summary = {
        'status': 'done',
        'timestamp': datetime.now().isoformat(),
        'total_users': len(users),
        'successful': sum(1 for r in results if 'score' in r),
        'failed': sum(1 for r in results if 'error' in r),
        'results': results,
    }
    print(f'[AutoDiaryScheduler] Summary: {summary["successful"]}/{summary["total_users"]} OK')
    return summary


if __name__ == '__main__':
    run_daily_diary()
