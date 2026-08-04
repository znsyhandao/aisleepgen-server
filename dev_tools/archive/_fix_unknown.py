import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = """            sleep_data = latest.get('sleep_data', {}) or latest
            if sleep_data:
                lines.append(f"睡眠习惯: 上床{sleep_data.get('bedtime','?')} 起床{sleep_data.get('wake_time','?')} 入睡{sleep_data.get('sleep_latency','?')}分 醒来{sleep_data.get('awake_times','?')}次 总时长{sleep_data.get('total_duration','?')}分")"""

new = """            sleep_data = latest.get('sleep_data', {}) or latest
            if sleep_data:
                parts = []
                bt = sleep_data.get('bedtime','')
                wt = sleep_data.get('wake_time','')
                sl = sleep_data.get('sleep_latency','')
                aw = sleep_data.get('awake_times','')
                td = sleep_data.get('total_duration','')
                if bt and bt != '未知': parts.append(f'上床{bt}')
                if wt and wt != '未知': parts.append(f'起床{wt}')
                if sl and sl != '未知': parts.append(f'入睡{sl}分')
                if aw and aw != '未知': parts.append(f'醒来{aw}次')
                if td and td != '未知': parts.append(f'总时长{td}分')
                if parts:
                    lines.append(f"睡眠习惯: {' '.join(parts)}")"""

count = content.count(old)
print(f'匹配 {count} 处')
if count >= 1:
    content = content.replace(old, new, 1)
    with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('已修复')
else:
    print('未匹配')
