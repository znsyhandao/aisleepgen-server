import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 去掉尾部重复的 {history_context}\n\n{wm_context} 部分但要有细节
# 找到尾部最后一段 {history_context}\n\n{wm_context} 
# 实际上不是后面跟{wm_context}，是"{history_context}\n\n{wm_context}{evidence_context}{scene_context}"
# 让我看看

idx = content.find('{history_context}\n\n{wm_context}{evidence_context}{scene_context}')
if idx >= 0:
    # 看看前面是什么
    start = max(0, idx - 300)
    end = min(len(content), idx + 200)
    print('Context around duplicate:')
    print(content[start:end])
    print(f'\nPosition: {idx}')
