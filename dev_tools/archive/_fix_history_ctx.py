import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复 _build_history_context 中对 latest 的读取
# 让它在有 sleep_data 嵌套时也能正确提取字段
old = """    latest_sleep = profile.get('latest', {})
    sleep_data = latest_sleep.get('sleep_data', {}) or latest_sleep
    if sleep_data:
        bd = sleep_data.get('bedtime','?')
        wt = sleep_data.get('wake_time','?')
        sl = sleep_data.get('sleep_latency','?')
        aw = sleep_data.get('awake_times','?')
        td = sleep_data.get('total_duration','?')
        lines.append(f"【用户基线】上床{bd} 起床{wt} 入睡{sl}分 醒{aw}次 总时长{td}分")"""

new = """    latest_sleep = profile.get('latest', {})
    sleep_data = latest_sleep.get('sleep_data', {}) or latest_sleep
    if sleep_data:
        bd = sleep_data.get('bedtime','') or ''
        wt = sleep_data.get('wake_time','') or ''
        sl = sleep_data.get('sleep_latency','') or ''
        aw = sleep_data.get('awake_times','') or ''
        td = sleep_data.get('total_duration','') or ''
        parts = []
        if bd and bd != '未知': parts.append(f'上床{bd}')
        if wt and wt != '未知': parts.append(f'起床{wt}')
        if sl and sl != '未知': parts.append(f'入睡{sl}分')
        if aw and aw != '未知': parts.append(f'醒{aw}次')
        if td and td != '未知': parts.append(f'总时长{td}分')
        if parts:
            lines.append(f"【用户基线】{' '.join(parts)}")"""

count = content.count(old)
print(f'匹配 {count} 处')
if count >= 1:
    content = content.replace(old, new, 1)
    with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('已修复 _build_history_context')
else:
    print('未匹配，检查代码格式')
