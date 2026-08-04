import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = """    # 更新最新画像--如果是纠正，数据来源标注为"用户修正"
    _old_sleep_data = profile.get('latest', {}).get('sleep_data', {})
    profile['latest'] = {
        'date': today,
        'score': wm_result.get('total_score', 0) if wm_result else 0,
        'quality': wm_result.get('quality', '') if wm_result else '',
        'pain': extracted_data.get('pain', False) if extracted_data else False,
        'pain_area': extracted_data.get('pain_area', '') if extracted_data else '',
        'environment_cold': extracted_data.get('environment_cold', False) if extracted_data else False,
        'environment_hot': extracted_data.get('environment_hot', False) if extracted_data else False,
        'snore_related': extracted_data.get('snore_related', False) if extracted_data else False,
        'awake_times': extracted_data.get('awake_times', 0) if extracted_data else 0,
        'stress': extracted_data.get('stress_level', 0) if extracted_data else 0,
        'feeling': extracted_data.get('feeling', '') if extracted_data else '',
        'confirmed': not is_correction,  # 纠正后标记为未确认
        # 保留从问卷或历史数据继承的 sleep_data（不丢失入睡/起床时间）
        'sleep_data': _old_sleep_data,
    }"""

new = """    # 更新最新画像--如果是纠正，数据来源标注为"用户修正"
    _old_latest = profile.get('latest', {})
    _old_sleep_data = _old_latest.get('sleep_data', {}) or _old_latest
    profile['latest'] = {
        'date': today,
        'score': wm_result.get('total_score', 0) if wm_result else 0,
        'quality': wm_result.get('quality', '') if wm_result else '',
        'pain': extracted_data.get('pain', False) if extracted_data else False,
        'pain_area': extracted_data.get('pain_area', '') if extracted_data else '',
        'environment_cold': extracted_data.get('environment_cold', False) if extracted_data else False,
        'environment_hot': extracted_data.get('environment_hot', False) if extracted_data else False,
        'snore_related': extracted_data.get('snore_related', False) if extracted_data else False,
        'awake_times': extracted_data.get('awake_times', 0) if extracted_data else 0,
        'stress': extracted_data.get('stress_level', 0) if extracted_data else 0,
        'feeling': extracted_data.get('feeling', '') if extracted_data else '',
        'confirmed': not is_correction,  # 纠正后标记为未确认
        # 保留睡眠基础数据（不丢失入睡/起床/总时长等关键字段）
        'sleep_data': {
            'bedtime': _old_sleep_data.get('bedtime', '') or _old_latest.get('bedtime', ''),
            'wake_time': _old_sleep_data.get('wake_time', '') or _old_latest.get('wake_time', ''),
            'sleep_latency': _old_sleep_data.get('sleep_latency', '') or _old_latest.get('sleep_latency', ''),
            'awake_times': _old_sleep_data.get('awake_times', '') or _old_latest.get('awake_times', ''),
            'total_duration': _old_sleep_data.get('total_duration', '') or _old_latest.get('total_duration', ''),
        },
    }"""

content = content.replace(old, new, 1)
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed')
