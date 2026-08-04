import sys
sys.stdout.reconfigure(encoding='utf-8')
with open(r'D:\AISleepGen_Optimized\deepseek_proxy.py','r',encoding='utf-8') as f:
    content = f.read()
count = content.count("summaries = profile.get('conversation_summaries'")
print(f'summaries = profile.get(...) appears {count} times')
